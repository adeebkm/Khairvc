// Global state
let currentEmail = null;
let currentReply = null;
let allEmails = [];
let filteredEmails = []; // Currently displayed/filtered emails
let currentTab = 'all';
let searchQuery = ''; // Current search query

// Pagination state
let currentPage = 1;
const EMAILS_PER_PAGE = 20;
let paginatedEmails = []; // Emails for current page

// Track if we're currently fetching to prevent multiple simultaneous requests
let isFetching = false;
// Cache for emails - persists across tab switches and page refreshes
let emailCache = {
    data: [],
    timestamp: null,
    maxAge: 5 * 60 * 1000 // 5 minutes cache
};

// Get cache key for current user (to isolate cache per user)
// CRITICAL: Must use user_id to prevent cross-user data leakage
function getCacheKey() {
    // Get user_id from body data attribute (most reliable)
    const body = document.body;
    if (body && body.dataset && body.dataset.userId) {
        const userId = body.dataset.userId;
        return `emailCache_user_${userId}`;
    }
    
    // Fallback: Try to get from username attribute
    if (body && body.dataset && body.dataset.username) {
        const username = body.dataset.username;
        return `emailCache_user_${username}`;
    }
    
    // SECURITY: If we can't identify the user, clear all caches and use session-based key
    // This prevents cross-user data leakage
    console.warn('⚠️  Cannot identify user for cache key - clearing all email caches');
    try {
        // Clear all emailCache_* keys from localStorage
        const keysToRemove = [];
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key && key.startsWith('emailCache_')) {
                keysToRemove.push(key);
            }
        }
        keysToRemove.forEach(key => localStorage.removeItem(key));
        console.log(`🗑️  Cleared ${keysToRemove.length} email cache entries`);
    } catch (error) {
        console.error('Error clearing cache:', error);
    }
    
    // Use session-based key (unique per browser session)
    const sessionKey = `emailCache_session_${Date.now()}_${Math.random()}`;
    console.warn(`⚠️  Using temporary session-based cache key: ${sessionKey}`);
    return sessionKey;
}

// Load email cache from localStorage on initialization
function loadEmailCacheFromStorage() {
    try {
        const cacheKey = getCacheKey();
        const cached = localStorage.getItem(cacheKey);
        if (cached) {
            const parsed = JSON.parse(cached);
            if (parsed.data && parsed.timestamp) {
                emailCache.data = parsed.data;
                emailCache.timestamp = parsed.timestamp;
                console.log(`📦 Loaded ${emailCache.data.length} emails from localStorage cache`);
            }
        }
    } catch (error) {
        console.error('Error loading email cache from localStorage:', error);
    }
}

// Save email cache to localStorage
function saveEmailCacheToStorage() {
    try {
        const cacheKey = getCacheKey();
        localStorage.setItem(cacheKey, JSON.stringify({
            data: emailCache.data,
            timestamp: emailCache.timestamp
        }));
    } catch (error) {
        console.error('Error saving email cache to localStorage:', error);
    }
}

// Clear email cache (useful when database is reset)
function clearEmailCache() {
    try {
        const cacheKey = getCacheKey();
        localStorage.removeItem(cacheKey);
        emailCache.data = [];
        emailCache.timestamp = null;
        console.log('🗑️  Cleared email cache');
    } catch (error) {
        console.error('Error clearing email cache:', error);
    }
}

// ==================== SENT EMAILS INDEXEDDB CACHE ====================
const SENT_CACHE_DB = 'gmail_sent_emails';
const SENT_CACHE_STORE = 'sent';
const SENT_CACHE_VERSION = 1;
const SENT_CACHE_MAX_AGE = 3600000; // 1 hour in milliseconds

let sentEmailsCacheDB = null;

async function initSentEmailsCache() {
    return new Promise((resolve, reject) => {
        try {
            const request = indexedDB.open(SENT_CACHE_DB, SENT_CACHE_VERSION);
            
            request.onerror = () => {
                console.error('Error opening sent emails cache:', request.error);
                reject(request.error);
            };
            
            request.onsuccess = () => {
                sentEmailsCacheDB = request.result;
                console.log('✅ Sent emails cache initialized');
                resolve();
            };
            
            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                if (!db.objectStoreNames.contains(SENT_CACHE_STORE)) {
                    const store = db.createObjectStore(SENT_CACHE_STORE, { keyPath: 'user_id' });
                    store.createIndex('timestamp', 'timestamp', { unique: false });
                    console.log('✅ Created sent emails cache store');
                }
            };
        } catch (error) {
            console.error('Error initializing sent emails cache:', error);
            reject(error);
        }
    });
}

async function getCachedSentEmails(userId) {
    if (!sentEmailsCacheDB) {
        console.warn('Sent emails cache DB not initialized');
        return null;
    }
    
    return new Promise((resolve) => {
        try {
            const tx = sentEmailsCacheDB.transaction(SENT_CACHE_STORE, 'readonly');
            const store = tx.objectStore(SENT_CACHE_STORE);
            const request = store.get(userId);
            
            request.onsuccess = () => {
                const data = request.result;
                if (data && Date.now() - data.timestamp < SENT_CACHE_MAX_AGE) {
                    console.log(`📧 Loaded ${data.emails.length} sent emails from IndexedDB cache`);
                    resolve(data.emails);
                } else {
                    if (data) {
                        console.log('📧 Sent emails cache expired, will fetch fresh data');
                    }
                    resolve(null);
                }
            };
            
            request.onerror = () => {
                console.warn('Error reading sent emails from cache:', request.error);
                resolve(null);
            };
        } catch (error) {
            console.error('Error getting cached sent emails:', error);
            resolve(null);
        }
    });
}

async function cacheSentEmails(userId, emails) {
    if (!sentEmailsCacheDB) {
        console.warn('Sent emails cache DB not initialized, skipping cache');
        return;
    }
    
    try {
        const tx = sentEmailsCacheDB.transaction(SENT_CACHE_STORE, 'readwrite');
        const store = tx.objectStore(SENT_CACHE_STORE);
        store.put({ 
            user_id: userId, 
            emails, 
            timestamp: Date.now() 
        });
        console.log(`✅ Cached ${emails.length} sent emails in IndexedDB`);
    } catch (error) {
        console.error('Error caching sent emails:', error);
    }
}

async function clearSentEmailsCache() {
    if (!sentEmailsCacheDB) return;
    
    try {
        const tx = sentEmailsCacheDB.transaction(SENT_CACHE_STORE, 'readwrite');
        const store = tx.objectStore(SENT_CACHE_STORE);
        store.clear();
        console.log('✅ Cleared sent emails cache');
    } catch (error) {
        console.error('Error clearing sent emails cache:', error);
    }
}
// Auto-fetch polling
let autoFetchInterval = null;
let autoFetchEnabled = false;
const AUTO_FETCH_INTERVAL = 5 * 60 * 1000; // Check every 5 minutes
let autoFetchPausedUntil = null; // Timestamp when auto-fetch should resume after rate limit

// Sent emails fetch protection
let isFetchingSentEmails = false;
let sentEmailsFetchPausedUntil = null; // Timestamp when sent fetch should resume after rate limit
let sentEmailsIntervalId = null; // Track the interval so we can clear it

// Auto-fetch function (only fetches new emails using incremental sync)
async function autoFetchNewEmails() {
    // Don't auto-fetch if already fetching or if user is viewing an email
    if (isFetching || document.getElementById('emailModal')?.style.display === 'flex') {
        return;
    }
    
    // Don't auto-fetch if user is on sent/drafts/starred tabs (only fetch for inbox)
    if (currentTab !== 'all' && currentTab !== 'deal-flow') {
        return;
    }
    
    // Check if auto-fetch is paused due to rate limit
    if (autoFetchPausedUntil && Date.now() < autoFetchPausedUntil) {
        const minutesLeft = Math.ceil((autoFetchPausedUntil - Date.now()) / 60000);
        console.log(`⏸️  Auto-fetch paused due to rate limit. Resuming in ${minutesLeft} minute${minutesLeft !== 1 ? 's' : ''}`);
        return;
    }
    
    // Clear pause if time has passed
    if (autoFetchPausedUntil && Date.now() >= autoFetchPausedUntil) {
        autoFetchPausedUntil = null;
    }
    
    try {
        // Poll database for new emails (Pub/Sub syncs to DB, we just need to check DB)
        // Use db_only=true to avoid triggering Gmail API calls (Pub/Sub handles that)
        const response = await fetch(`/api/emails?max=200&show_spam=true&db_only=true`);
        const data = await response.json();
        
        // Handle rate limit errors
        if (response.status === 429 || data.rate_limit) {
            // Pause auto-fetch for 10 minutes after rate limit
            autoFetchPausedUntil = Date.now() + (10 * 60 * 1000);
            console.log(`⚠️  Auto-fetch paused due to rate limit. Will resume in 10 minutes.`);
            return;
        }
        
        if (data.success) {
            // Handle deletions from Gmail
            if (data.deleted_message_ids && data.deleted_message_ids.length > 0) {
                await handleEmailDeletions(data.deleted_message_ids);
            }
            
            // Handle new emails
            if (data.emails && data.emails.length > 0) {
                // Check if these are actually new emails by comparing message_id (not thread_id)
                // This catches replies on existing threads as new emails
                const existingMessageIds = new Set(emailCache.data.map(e => e.id || e.message_id));
                const uniqueNewEmails = data.emails.filter(e => {
                    const msgId = e.id || e.message_id;
                    return msgId && !existingMessageIds.has(msgId);
                });
                
                if (uniqueNewEmails.length > 0) {
                    console.log(`📧 Auto-fetch: Found ${uniqueNewEmails.length} new email(s) in database`);
                    
                    // Merge new emails with existing (replace duplicates, add new ones)
                    const existingMap = new Map(emailCache.data.map(e => [e.id || e.message_id, e]));
                    uniqueNewEmails.forEach(email => {
                        const msgId = email.id || email.message_id;
                        if (msgId) {
                            existingMap.set(msgId, email);
                        }
                    });
                    
                    // Update cache with merged emails (sorted by date, newest first)
                    emailCache.data = Array.from(existingMap.values()).sort((a, b) => {
                        const dateA = parseInt(a.date) || 0;
                        const dateB = parseInt(b.date) || 0;
                        return dateB - dateA; // Newest first
                    });
                    emailCache.timestamp = Date.now();
                    saveEmailCacheToStorage(); // Save to localStorage
                    
                    // Only update allEmails and applyFilters if we're on the inbox tab
                    // Don't interfere with sent/drafts/starred tabs
                    if (currentTab === 'all' || currentTab === 'deal-flow') {
                    allEmails = emailCache.data;
                    
                    // Apply filters and update display
                    applyFilters();
                    
                    // Show notification
                    showAlert('success', `📧 ${uniqueNewEmails.length} new email${uniqueNewEmails.length !== 1 ? 's' : ''} detected!`);
                    
                    console.log(`✅ Auto-fetch: Updated UI with ${uniqueNewEmails.length} new email(s), total: ${allEmails.length}`);
                    } else {
                        // Just update the cache, don't change the display
                        console.log(`ℹ️  Auto-fetch: Found ${uniqueNewEmails.length} new email(s), but on ${currentTab} tab - not updating display`);
                    }
                } else {
                    console.log(`ℹ️  Auto-fetch: No new emails detected (${data.emails.length} total in database)`);
                }
            } else {
                console.log(`ℹ️  Auto-fetch: No emails in database yet`);
            }
        }
    } catch (error) {
        console.error('Error in auto-fetch:', error);
        // Silently fail - don't spam user with errors for background polling
    }
}

// Handle email deletions from Gmail
async function handleEmailDeletions(deletedIds) {
    if (!deletedIds || deletedIds.length === 0) {
        return;
    }
    
    console.log(`🗑️  Processing ${deletedIds.length} deleted email(s) from Gmail`);
    
    // Remove from email list cache
    emailCache.data = emailCache.data.filter(e => !deletedIds.includes(e.id));
    
    // Remove from allEmails
    allEmails = allEmails.filter(e => !deletedIds.includes(e.id));
    
    // Invalidate thread caches for deleted emails
    const threadsToInvalidate = new Set();
    for (const messageId of deletedIds) {
        // Find the thread_id before removal
        const email = emailCache.data.find(e => e.id === messageId) || allEmails.find(e => e.id === messageId);
        if (email && email.thread_id) {
            threadsToInvalidate.add(email.thread_id);
        }
    }
    
    // Invalidate thread caches
    for (const threadId of threadsToInvalidate) {
        await invalidateThreadCache(threadId);
    }
    
    // Update UI
    applyFilters();
    saveEmailCacheToStorage();
    
    if (deletedIds.length > 0) {
        showAlert('info', `${deletedIds.length} email${deletedIds.length !== 1 ? 's' : ''} deleted from Gmail`);
    }
}

// Delete email from UI and Gmail
async function deleteEmail(messageId, emailIndexOrThreadId) {
    if (!confirm('Are you sure you want to delete this email?')) {
        return;
    }
    
    try {
        // Get thread_id if emailIndexOrThreadId is an index, otherwise use it as thread_id
        let threadId = null;
        if (typeof emailIndexOrThreadId === 'number') {
            // It's an index - get the email to find thread_id
            const email = filteredEmails[emailIndexOrThreadId] || allEmails[emailIndexOrThreadId];
            threadId = email?.thread_id;
        } else {
            // It's already a thread_id
            threadId = emailIndexOrThreadId;
        }
        
        // Optimistic UI update - remove from display immediately
        const emailIndex = allEmails.findIndex(e => e.id === messageId);
        let removedEmail = null;
        if (emailIndex >= 0) {
            removedEmail = allEmails[emailIndex];
            allEmails.splice(emailIndex, 1);
            applyFilters();
        }
        
        // Call backend to delete from Gmail
        const response = await fetch(`/api/email/${messageId}/delete`, {
            method: 'POST'
        });
        
        if (response.ok) {
            const data = await response.json();
            
            if (data.success) {
            // Invalidate thread cache
            if (threadId) {
                await invalidateThreadCache(threadId);
            }
            
            // Remove from email list cache
            emailCache.data = emailCache.data.filter(e => e.id !== messageId);
            saveEmailCacheToStorage();
                
                // Remove from filtered emails
                filteredEmails = filteredEmails.filter(e => e.id !== messageId);
                updatePagination(); // Use updatePagination to preserve pagination
            
            // Close modal if open
            const modal = document.getElementById('emailModal');
            if (modal && modal.style.display === 'flex') {
                closeModal();
            }
            
                showToast('Email deleted successfully', 'success');
        } else {
                // Restore email if deletion failed
                if (removedEmail && emailIndex >= 0) {
                allEmails.splice(emailIndex, 0, removedEmail);
                applyFilters();
            }
                showToast(data.error || 'Failed to delete email', 'error');
            }
        } else {
            // Restore email if deletion failed
            if (removedEmail && emailIndex >= 0) {
                allEmails.splice(emailIndex, 0, removedEmail);
                applyFilters();
            }
            showToast('Failed to delete email', 'error');
        }
    } catch (error) {
        console.error('Error deleting email:', error);
        showToast('Error deleting email', 'error');
    }
}

// Start/stop auto-fetch polling
function toggleAutoFetch(enabled) {
    // Clear existing intervals first
    if (autoFetchInterval) {
        clearInterval(autoFetchInterval);
        autoFetchInterval = null;
    }
    if (sentEmailsIntervalId) {
        clearInterval(sentEmailsIntervalId);
        sentEmailsIntervalId = null;
    }
    
    // Set the flag properly based on the parameter
    autoFetchEnabled = enabled !== false; // Default to true if not explicitly false
    
    if (!autoFetchEnabled) {
        console.log('⏸️ Auto-fetch disabled');
        return;
    }
    
    // Auto-fetch enabled - polls database for new emails synced by Pub/Sub
    // Pub/Sub syncs emails to database, but frontend needs to poll to update UI
    
    // Poll immediately, then every 30 seconds
    autoFetchNewEmails();
    autoFetchInterval = setInterval(autoFetchNewEmails, 30 * 1000); // 30 seconds
    
    // Auto-fetch sent emails in background (every 5 minutes instead of 2)
    // IMPORTANT: Delay the first fetch to ensure IndexedDB is initialized
    console.log('⏳ Sent emails fetch will start in 5 seconds (waiting for IndexedDB)...');
    setTimeout(() => {
        fetchSentEmails(); // Fetch after delay
    }, 5000); // 5 second delay for IndexedDB initialization
    
    sentEmailsIntervalId = setInterval(() => {
        // Only auto-fetch if not currently on sent tab and not already fetching
        if (currentTab !== 'sent' && !isFetchingSentEmails) {
            fetchSentEmails();
        }
    }, 5 * 60 * 1000); // 5 minutes (increased from 2 to reduce API calls)
    
    console.log('✅ Auto-fetch enabled - polling database every 30 seconds for new emails synced by Pub/Sub');
    console.log('✅ Auto-fetch sent emails enabled - fetching every 5 minutes');
}

// Toggle Gmail dropdown
function toggleGmailDropdown(event) {
    event.stopPropagation();
    const menu = document.getElementById('gmailDropdownMenu');
    if (menu) {
        const isVisible = menu.style.display !== 'none';
        menu.style.display = isVisible ? 'none' : 'block';
        
        // Close dropdown when clicking outside
        if (!isVisible) {
            setTimeout(() => {
                document.addEventListener('click', function closeDropdown(e) {
                    if (!menu.contains(e.target) && e.target.id !== 'gmailDropdownBtn') {
                        menu.style.display = 'none';
                        document.removeEventListener('click', closeDropdown);
                    }
                });
            }, 0);
        }
    }
}

// ==================== SETUP SCREEN ====================
let finalizeSetupPromise = null;
let setupProgressPoller = null;
let setupTimerInterval = null;

async function startSetup() {
    console.log('🚀 === SETUP STARTED ===');
    console.log('🚀 Timestamp:', new Date().toISOString());
    console.log('🚀 User ID:', document.body.dataset.userId);
    console.log('🚀 Username:', document.body.dataset.username);
    
    const setupScreen = document.getElementById('setupScreen');
    const progressBar = document.getElementById('setupProgressBar');
    const progressText = document.getElementById('setupProgressText');
    const timerMinutes = document.getElementById('timerMinutes');
    const timerSeconds = document.getElementById('timerSeconds');
    const motivationalQuote = document.getElementById('motivationalQuote');
    
    console.log('🚀 Setup elements:', {
        setupScreen: setupScreen ? 'FOUND' : 'NOT FOUND',
        progressBar: progressBar ? 'FOUND' : 'NOT FOUND',
        progressText: progressText ? 'FOUND' : 'NOT FOUND',
        timerMinutes: timerMinutes ? 'FOUND' : 'NOT FOUND',
        timerSeconds: timerSeconds ? 'FOUND' : 'NOT FOUND',
        motivationalQuote: motivationalQuote ? 'FOUND' : 'NOT FOUND'
    });
    
    if (!setupScreen) {
        console.error('❌ Setup screen element not found - cannot continue');
        return;
    }
    
    console.log('✅ All setup elements found, proceeding...');
    
    try {
        // STEP 1: Check inbox size first
        console.log('📊 STEP 1: Checking inbox size...');
        progressText.textContent = 'Analyzing your inbox...';
        progressBar.style.width = '5%';
        
        console.log('📊 Calling /api/setup/check-inbox-size...');
        const sizeResponse = await fetch('/api/setup/check-inbox-size');
        console.log('📊 Response status:', sizeResponse.status);
        console.log('📊 Response ok:', sizeResponse.ok);
        
        const sizeData = await sizeResponse.json();
        console.log('📊 Size data:', sizeData);
        
        if (!sizeData.success) {
            console.error('❌ Failed to check inbox size:', sizeData);
            throw new Error('Failed to check inbox size');
        }
        
        const totalEmails = sizeData.total_emails;
        const emailsToFetch = sizeData.emails_to_fetch;
        const estimatedSeconds = sizeData.estimated_seconds;
        
        console.log('📊 ✅ Inbox analysis complete:');
        console.log(`   - Total emails in inbox: ${totalEmails}`);
        console.log(`   - Emails to fetch: ${emailsToFetch}`);
        console.log(`   - Estimated time: ${Math.floor(estimatedSeconds/60)} minutes (${estimatedSeconds} seconds)`);
        
        // STEP 2: Start fetching emails
        console.log('📧 STEP 2: Starting email fetch...');
        progressText.textContent = `Fetching ${emailsToFetch} emails from your inbox...`;
        progressBar.style.width = '10%';
        
        console.log('📧 Calling /api/setup/fetch-initial...');
        const fetchResponse = await fetch('/api/setup/fetch-initial', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        console.log('📧 Fetch response status:', fetchResponse.status);
        
        const fetchData = await fetchResponse.json();
        console.log('📧 Fetch data:', fetchData);
        
        if (fetchData.already_complete) {
            // Setup already done
            console.log('✅ Setup already complete, showing inbox immediately');
            await completeSetupImmediately(setupScreen, progressBar, progressText);
            return;
        }
        
        console.log('✅ Email fetch initiated successfully');
        
        // STEP 3: Start adaptive countdown timer
        console.log('⏱️  STEP 3: Starting adaptive timer...');
        startAdaptiveTimer(estimatedSeconds, emailsToFetch, setupScreen, progressBar, progressText, timerMinutes, timerSeconds, motivationalQuote);
        
        // STEP 4: Start real-time progress polling
        console.log('🔄 STEP 4: Starting progress polling...');
        startProgressPolling(progressBar, progressText, emailsToFetch);
        
        console.log('🚀 === SETUP INITIALIZATION COMPLETE ===');
        
    } catch (error) {
        console.error('❌ === SETUP ERROR ===');
        console.error('❌ Error type:', error.name);
        console.error('❌ Error message:', error.message);
        console.error('❌ Error stack:', error.stack);
        progressText.textContent = `Error: ${error.message}. Retrying...`;
        // Retry after 3 seconds
        console.log('⏳ Retrying setup in 3 seconds...');
        setTimeout(() => startSetup(), 3000);
    }
}

async function pollSetupProgress(taskId, progressBar, progressText) {
    return new Promise((resolve, reject) => {
        let pollCount = 0;
        const MAX_POLLS = 60; // 60 seconds timeout (60 polls * 1 second)
        let pendingTime = 0;
        
        const interval = setInterval(async () => {
            pollCount++;
            try {
                const response = await fetch(`/api/emails/sync/status/${taskId}`);
                const data = await response.json();
                
                if (data.status === 'PENDING') {
                    pendingTime++;
                    // If task stays PENDING for 30 seconds, assume no worker is processing it
                    if (pendingTime >= 30) {
                        console.warn('⚠️  Task stuck in PENDING for 30+ seconds, falling back to streaming');
                        clearInterval(interval);
                        reject(new Error('Task not being processed, using streaming fallback'));
                    } else if (progressText) {
                        progressText.textContent = `Waiting for worker... (${pendingTime}s)`;
                    }
                } else if (data.status === 'PROGRESS') {
                    pendingTime = 0; // Reset pending time
                    const progress = data.progress || 0;
                    const total = data.total || 60;
                    const percent = Math.min((progress / total) * 100, 90);
                    if (progressBar) progressBar.style.width = `${percent}%`;
                    if (progressText) progressText.textContent = `Processing ${progress} of ${total} emails...`;
                } else if (data.status === 'SUCCESS') {
                    clearInterval(interval);
                    if (progressBar) progressBar.style.width = '100%';
                    if (progressText) progressText.textContent = 'Setup complete!';
                    setTimeout(resolve, 1000);
                } else if (data.status === 'FAILURE' || data.status === 'error') {
                    clearInterval(interval);
                    const errorMsg = data.error || data.message || 'Setup failed';
                    console.error('❌ Setup task failed:', errorMsg);
                    // If it's an API key error, provide helpful message
                    if (errorMsg.includes('API key') || errorMsg.includes('MOONSHOT') || errorMsg.includes('OPENAI')) {
                        reject(new Error('Worker configuration error: API key not set. Please check Railway worker environment variables.'));
                    } else {
                        reject(new Error(errorMsg));
                    }
                }
                
                // Timeout after MAX_POLLS
                if (pollCount >= MAX_POLLS) {
                    clearInterval(interval);
                    reject(new Error('Setup timeout - task took too long'));
                }
            } catch (error) {
                clearInterval(interval);
                reject(error);
            }
        }, 1000);
    });
}

/**
 * Hardcoded timer approach: Random 7-10 minutes, then show inbox with whatever emails are available
 * Shows approximate time remaining in minutes, then seconds (with random intervals) when < 1 minute
 * Timer persists across page refreshes using localStorage
 */
/**
 * Start adaptive timer based on actual inbox size
 */
function startAdaptiveTimer(totalSeconds, emailCount, setupScreen, progressBar, progressText, timerMinutes, timerSeconds, motivationalQuote) {
    let remainingSeconds = totalSeconds;
    
    console.log(`⏱️ Starting ${Math.floor(totalSeconds/60)} minute timer for ${emailCount} emails`);
    
    // Show initial time
    updateTimerDisplay(remainingSeconds, timerMinutes, timerSeconds);
    
    // Update motivational quote based on time
    updateMotivationalQuote(Math.floor(totalSeconds/60), motivationalQuote);
    
    // Start countdown
    setupTimerInterval = setInterval(async () => {
        remainingSeconds--;
        updateTimerDisplay(remainingSeconds, timerMinutes, timerSeconds);
        
        // Update motivational quotes at key milestones
        if (remainingSeconds === Math.floor(totalSeconds * 0.66)) {
            motivationalQuote.textContent = "Almost halfway there...";
        } else if (remainingSeconds === Math.floor(totalSeconds * 0.33)) {
            motivationalQuote.textContent = "Final stretch! 🎯";
        } else if (remainingSeconds === 30) {
            motivationalQuote.textContent = "Just a few more seconds...";
        }
        
        // When timer completes
        if (remainingSeconds <= 0) {
            clearInterval(setupTimerInterval);
            clearInterval(setupProgressPoller);
            await completeSetupAfterTimer(setupScreen, progressBar, progressText);
        }
    }, 1000);
}

/**
 * Update timer display
 */
function updateTimerDisplay(seconds, timerMinutes, timerSeconds) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    if (timerMinutes) timerMinutes.textContent = mins;
    if (timerSeconds) timerSeconds.textContent = secs.toString().padStart(2, '0');
}

/**
 * Update motivational quote based on estimated time
 */
function updateMotivationalQuote(minutes, motivationalQuote) {
    const quotes = {
        4: "Quick setup for your inbox... ⚡",
        5: "Setting up your email command center... 🚀",
        7: "Great things take a bit longer... ⏳",
        10: "Building something amazing for you... ✨"
    };
    if (motivationalQuote) {
        motivationalQuote.textContent = quotes[minutes] || "Good things take time...";
    }
}

/**
 * Start polling for real-time progress updates
 */
function startProgressPolling(progressBar, progressText, totalToFetch) {
    let lastClassifiedCount = 0;
    
    setupProgressPoller = setInterval(async () => {
        try {
            const response = await fetch('/api/setup/progress');
            const data = await response.json();
            
            if (data.success) {
                const { fetched, classified, total, progress_percent } = data;
                
                // Update progress bar (10% base + 80% for classification progress)
                const displayProgress = 10 + (progress_percent * 0.8);
                progressBar.style.width = `${Math.min(90, displayProgress)}%`;
                
                // Update status text
                if (classified > lastClassifiedCount) {
                    progressText.textContent = `Classified ${classified}/${totalToFetch} emails...`;
                    lastClassifiedCount = classified;
                }
                
                // If all emails are classified before timer ends, complete early
                if (classified >= totalToFetch && classified > 0) {
                    console.log('✅ All emails classified early!');
                    clearInterval(setupTimerInterval);
                    clearInterval(setupProgressPoller);
                    const setupScreen = document.getElementById('setupScreen');
                    await completeSetupAfterTimer(setupScreen, progressBar, progressText);
                }
            }
        } catch (error) {
            console.warn('Progress polling error:', error);
        }
    }, 2000); // Poll every 2 seconds
}

/**
 * Complete setup immediately (when already done)
 */
async function completeSetupImmediately(setupScreen, progressBar, progressText) {
    progressText.textContent = 'Setup complete! Loading inbox...';
    progressBar.style.width = '100%';
    
    await loadEmailsFromDatabase();
    
    // Smooth fade out
    setupScreen.style.transition = 'opacity 1s ease-out';
    setupScreen.style.opacity = '0';
    
    setTimeout(() => {
        setupScreen.style.display = 'none';
        const compactHeader = document.querySelector('.main-content > .compact-header');
        if (compactHeader) compactHeader.style.display = 'block';
        
        // CRITICAL: contentArea uses display: flex in CSS, don't change to block!
        const contentArea = document.getElementById('contentArea');
        if (contentArea) {
            contentArea.style.opacity = '1';  // Just set opacity, display is already flex from CSS
        }
        
        // Fade in email list
        const emailList = document.getElementById('emailList');
        if (emailList) {
            emailList.style.transition = 'opacity 1s ease-in';
            emailList.style.opacity = '1';
        }
        
        if (allEmails.length > 0) {
            applyFilters();
            updatePagination();
        }
    }, 1000);
}

/**
 * Complete setup after timer (IMPROVED with smooth transition)
 */
async function completeSetupAfterTimer(setupScreen, progressBar, progressText) {
    console.log('⏱️ Timer complete, finalizing setup...');
    
    if (progressText) progressText.textContent = 'Loading your inbox...';
    if (progressBar) progressBar.style.width = '95%';
    
    try {
        // Load emails from database
        await loadEmailsFromDatabase();
        console.log(`📧 Loaded ${allEmails.length} emails`);
        
        // Mark setup as complete on server
        await fetch('/api/setup/complete', { method: 'POST' });
        
        // Show completion
        if (progressText) progressText.textContent = `Setup complete! ${allEmails.length} emails loaded.`;
        if (progressBar) progressBar.style.width = '100%';
        
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        // SMOOTH TRANSITION: Fade out overlay, fade in emails
        if (setupScreen) {
            setupScreen.style.transition = 'opacity 1s ease-out';
            setupScreen.style.opacity = '0';
        }
        
        setTimeout(() => {
            if (setupScreen) setupScreen.style.display = 'none';
            
            // Show UI elements
            const compactHeader = document.querySelector('.main-content > .compact-header');
            if (compactHeader) compactHeader.style.display = 'block';
            
            // CRITICAL: contentArea uses display: flex in CSS, don't change it!
            // Just set opacity to make it visible
            const contentArea = document.getElementById('contentArea');
            if (contentArea) {
                contentArea.style.transition = 'opacity 1s ease-in';
                contentArea.style.opacity = '1';
            }
            
            // Also ensure emailList is visible
            const emailList = document.getElementById('emailList');
            if (emailList) {
                emailList.style.transition = 'opacity 0.5s ease-in';
                emailList.style.opacity = '1';
            }
            
            // Display emails
            if (allEmails.length > 0) {
                applyFilters();
                updatePagination();
            }
            
            console.log('✅ Setup complete! Inbox displayed.');
        }, 1000);
        
    } catch (error) {
        console.error('❌ Error completing setup:', error);
        if (progressText) progressText.textContent = 'Error loading emails. Refreshing...';
        setTimeout(() => window.location.reload(), 2000);
    }
}

async function finalizeSetupStatus() {
    if (finalizeSetupPromise) {
        return finalizeSetupPromise;
    }
    
    finalizeSetupPromise = (async () => {
        try {
            const response = await fetch('/api/setup/complete', { method: 'POST' });
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(errorText || response.statusText || 'Failed to mark setup complete');
            }
            console.log('✅ Setup marked complete on server');
        } catch (error) {
            console.warn('⚠️  Could not mark setup as complete:', error);
        }
        
        try {
            const pubsubResponse = await fetch('/api/setup-pubsub', { method: 'POST' });
            const contentType = pubsubResponse.headers.get('content-type') || '';
            let pubsubData = {};
            if (contentType.includes('application/json')) {
                pubsubData = await pubsubResponse.json();
            }
            
            if (pubsubResponse.ok && pubsubData.success) {
                console.log('✅ Pub/Sub watch configured automatically');
            } else if (pubsubResponse.status === 400 && pubsubData.error?.includes('not enabled')) {
                console.log('ℹ️  Pub/Sub not enabled (production environment)');
            } else if (pubsubData.error) {
                console.warn('⚠️  Pub/Sub setup failed (non-critical):', pubsubData.error);
            }
        } catch (error) {
            console.warn('⚠️  Pub/Sub setup error (non-critical):', error);
        }
    })();
    
    return finalizeSetupPromise;
}

async function fetchInitialEmailsStreaming(progressBar, progressText) {
    // Use streaming endpoint for initial fetch
    if (progressText) progressText.textContent = 'Connecting to server...';
    
    const response = await fetch('/api/emails/stream?max=200&force_full_sync=true');
    
    if (!response.ok) {
        throw new Error(`Streaming failed: ${response.status} ${response.statusText}`);
    }
    
    if (!response.body) {
        throw new Error('Streaming not supported by browser');
    }
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let processed = 0;
    const total = 200;
    
    try {
        while (true) {
            const {done, value} = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, {stream: true});
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            
            for (const line of lines) {
                if (line.trim() === '') continue;
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.email) {
                            processed++;
                            const percent = Math.min((processed / total) * 100, 90);
                            if (progressBar) progressBar.style.width = `${percent}%`;
                            if (progressText) progressText.textContent = `Processing ${processed} of ${total} emails...`;
                        } else if (data.status === 'complete') {
                            if (progressBar) progressBar.style.width = '100%';
                            if (progressText) progressText.textContent = 'Setup complete!';
                        } else if (data.error) {
                            throw new Error(data.error);
                        }
                    } catch (parseError) {
                        console.warn('Error parsing streaming data:', parseError, 'Line:', line);
                    }
                }
            }
        }
    } catch (streamError) {
        console.error('Streaming error:', streamError);
        throw streamError;
    } finally {
        reader.releaseLock();
    }
}

// ==================== PAGINATION ====================
function updatePagination() {
    const emailList = document.getElementById('emailList');
    if (!emailList) return;
    
    // Safety check: ensure filteredEmails is set
    // If filteredEmails is empty but allEmails has data, try applying filters again
    if (!filteredEmails || filteredEmails.length === 0) {
        if (allEmails.length > 0) {
            console.warn('⚠️ updatePagination: filteredEmails is empty but allEmails has data, applying filters...');
            applyFilters();
            // If still empty after applying filters, use allEmails
            if (!filteredEmails || filteredEmails.length === 0) {
                console.warn('⚠️ updatePagination: filteredEmails still empty, using allEmails');
                filteredEmails = allEmails;
            }
        } else {
            console.warn('⚠️ updatePagination: filteredEmails is empty, displaying empty state');
            displayEmails([]);
            return;
        }
    }
    
    // Remove existing pagination
    const existingPagination = emailList.querySelector('.pagination');
    if (existingPagination) {
        existingPagination.remove();
    }
    
    // Calculate pagination
    const totalEmails = filteredEmails.length;
    const totalPages = Math.ceil(totalEmails / EMAILS_PER_PAGE);
    
    // Get emails for current page
    const startIndex = (currentPage - 1) * EMAILS_PER_PAGE;
    const endIndex = startIndex + EMAILS_PER_PAGE;
    paginatedEmails = filteredEmails.slice(startIndex, endIndex);
    
    // Display current page emails (always display, even if only 1 page)
    displayEmails(paginatedEmails);
    
    // Only show pagination controls if more than 1 page
    if (totalPages <= 1) return;
    
    // Create pagination container
    const pagination = document.createElement('div');
    pagination.className = 'pagination';
    
    // Create main controls wrapper (horizontal)
    const paginationControls = document.createElement('div');
    paginationControls.className = 'pagination-controls';
    
    // Page info (left side)
    const pageInfo = document.createElement('div');
    pageInfo.className = 'pagination-info';
    const startEmail = startIndex + 1;
    const endEmail = Math.min(endIndex, totalEmails);
    pageInfo.innerHTML = `<span class="pagination-text">Showing <strong>${startEmail}-${endEmail}</strong> of <strong>${totalEmails}</strong></span>`;
    paginationControls.appendChild(pageInfo);
    
    // Navigation buttons container
    const navContainer = document.createElement('div');
    navContainer.className = 'pagination-nav';
    
    // Previous button
    const prevBtn = document.createElement('button');
    prevBtn.className = 'pagination-btn pagination-btn-nav';
    prevBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M10 12L6 8L10 4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    prevBtn.disabled = currentPage === 1;
    prevBtn.setAttribute('aria-label', 'Previous page');
    prevBtn.onclick = () => {
        if (currentPage > 1) {
            currentPage--;
            updatePagination();
        }
    };
    navContainer.appendChild(prevBtn);
    
    // Page number buttons
    const pageNumbers = document.createElement('div');
    pageNumbers.className = 'pagination-numbers';
    
    // Calculate which page numbers to show (max 5 pages visible for cleaner look)
    let startPage = Math.max(1, currentPage - 2);
    let endPage = Math.min(totalPages, currentPage + 2);
    
    // Adjust if we're near the start or end
    if (endPage - startPage < 4) {
        if (startPage === 1) {
            endPage = Math.min(5, totalPages);
        } else if (endPage === totalPages) {
            startPage = Math.max(1, totalPages - 4);
        }
    }
    
    // First page button (if not in range)
    if (startPage > 1) {
        const firstBtn = document.createElement('button');
        firstBtn.className = 'pagination-btn pagination-btn-number';
        firstBtn.textContent = '1';
        firstBtn.onclick = () => {
            currentPage = 1;
            updatePagination();
        };
        pageNumbers.appendChild(firstBtn);
        
        if (startPage > 2) {
            const ellipsis = document.createElement('span');
            ellipsis.className = 'pagination-ellipsis';
            ellipsis.textContent = '⋯';
            ellipsis.setAttribute('aria-hidden', 'true');
            pageNumbers.appendChild(ellipsis);
        }
    }
    
    // Page number buttons
    for (let i = startPage; i <= endPage; i++) {
        const pageBtn = document.createElement('button');
        pageBtn.className = 'pagination-btn pagination-btn-number';
        if (i === currentPage) {
            pageBtn.classList.add('active');
            pageBtn.setAttribute('aria-current', 'page');
        }
        pageBtn.textContent = i.toString();
        pageBtn.setAttribute('aria-label', `Go to page ${i}`);
        pageBtn.onclick = () => {
            currentPage = i;
            updatePagination();
        };
        pageNumbers.appendChild(pageBtn);
    }
    
    // Last page button (if not in range)
    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            const ellipsis = document.createElement('span');
            ellipsis.className = 'pagination-ellipsis';
            ellipsis.textContent = '⋯';
            ellipsis.setAttribute('aria-hidden', 'true');
            pageNumbers.appendChild(ellipsis);
        }
        
        const lastBtn = document.createElement('button');
        lastBtn.className = 'pagination-btn pagination-btn-number';
        lastBtn.textContent = totalPages.toString();
        lastBtn.setAttribute('aria-label', `Go to page ${totalPages}`);
        lastBtn.onclick = () => {
            currentPage = totalPages;
            updatePagination();
        };
        pageNumbers.appendChild(lastBtn);
    }
    
    navContainer.appendChild(pageNumbers);
    
    // Next button
    const nextBtn = document.createElement('button');
    nextBtn.className = 'pagination-btn pagination-btn-nav';
    nextBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M6 4L10 8L6 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    nextBtn.disabled = currentPage === totalPages;
    nextBtn.setAttribute('aria-label', 'Next page');
    nextBtn.onclick = () => {
        if (currentPage < totalPages) {
            currentPage++;
            updatePagination();
        }
    };
    navContainer.appendChild(nextBtn);
    
    paginationControls.appendChild(navContainer);
    pagination.appendChild(paginationControls);
    
    // Insert pagination after email list
    emailList.appendChild(pagination);
    
    // Pre-fetch threads for visible emails on this page (instant cache access)
    prefetchVisibleThreads();
}

// ==================== BACKGROUND FETCHING ====================
let backgroundFetchInterval = null;
let backgroundFetchActive = false;

async function startBackgroundFetching() {
    if (backgroundFetchActive) return;
    
    backgroundFetchActive = true;
    
    // Start immediately, then check every 3 minutes (more conservative to avoid rate limits)
    const triggerBackgroundFetch = async () => {
        try {
            const response = await fetch('/api/emails/background-fetch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            const data = await response.json();
            
            if (data.success && data.task_id) {
                console.log(`🔄 Silent background fetch: ${data.fetching} emails (${data.current_count}/${data.target_total})`);
                
                // Poll for completion (silently)
                pollBackgroundTask(data.task_id);
            } else if (data.message === 'Already have enough emails') {
                console.log('✅ Background fetch complete: 150 emails loaded');
                stopBackgroundFetching();
            }
        } catch (error) {
            console.error('Background fetch error:', error);
        }
    };
    
    // Start immediately
    await triggerBackgroundFetch();
    
    // Then check every 3 minutes (more conservative to avoid rate limits)
    backgroundFetchInterval = setInterval(triggerBackgroundFetch, 3 * 60 * 1000);
}

async function pollBackgroundTask(taskId) {
    // Silently poll and reload emails when done
    const interval = setInterval(async () => {
        try {
            const response = await fetch(`/api/emails/sync/status/${taskId}`);
            const data = await response.json();
            
            if (data.status === 'SUCCESS') {
                clearInterval(interval);
                console.log('✅ Background fetch complete');
                // Silently reload emails
                await loadEmailsFromDatabase();
            } else if (data.status === 'FAILURE') {
                clearInterval(interval);
                console.error('Background fetch failed:', data.error);
            }
        } catch (error) {
            clearInterval(interval);
            console.error('Background fetch poll error:', error);
        }
    }, 5000); // Poll every 5 seconds
}

function stopBackgroundFetching() {
    if (backgroundFetchInterval) {
        clearInterval(backgroundFetchInterval);
        backgroundFetchInterval = null;
    }
    backgroundFetchActive = false;
}

// Load config on page load
// Pre-fetching with IntersectionObserver
let threadPrefetchObserver = null;
const prefetchedThreads = new Set();

function initThreadPrefetching() {
    if (!('IntersectionObserver' in window)) {
        console.log('IntersectionObserver not supported - pre-fetching disabled');
        return;
    }
    
    // Create observer with 200px margin (prefetch when email is 200px from viewport)
    threadPrefetchObserver = new IntersectionObserver(
        (entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const threadId = entry.target.dataset.threadId;
                    if (threadId && !prefetchedThreads.has(threadId)) {
                        prefetchedThreads.add(threadId);
                        prefetchThread(threadId);
                    }
                }
            });
        },
        {
            root: null,
            rootMargin: '200px',
            threshold: 0
        }
    );
    
    console.log('✅ Thread pre-fetching initialized');
}

function observeEmailsForPrefetch() {
    if (!threadPrefetchObserver) return;
    
    // Observe all visible email items
    const emailItems = document.querySelectorAll('.email-item[data-thread-id]');
    emailItems.forEach(item => {
        threadPrefetchObserver.observe(item);
    });
}

function stopObservingEmails() {
    if (!threadPrefetchObserver) return;
    threadPrefetchObserver.disconnect();
}

document.addEventListener('DOMContentLoaded', async function() {
    // SECURITY: Clear any old generic cache keys that could cause cross-user data leakage
    try {
        const currentUserId = document.body?.dataset?.userId;
        if (currentUserId) {
            // Clear any cache keys that don't match current user
            const keysToRemove = [];
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                if (key && key.startsWith('emailCache_')) {
                    // Keep only the current user's cache
                    if (!key.includes(`user_${currentUserId}`) && key !== `emailCache_user_${currentUserId}`) {
                        keysToRemove.push(key);
                    }
                }
            }
            if (keysToRemove.length > 0) {
                keysToRemove.forEach(key => localStorage.removeItem(key));
                console.log(`🔒 Security: Cleared ${keysToRemove.length} cache entries from other users`);
            }
        } else {
            // If we can't identify user, clear all email caches as a safety measure
            const keysToRemove = [];
            for (let i = 0; i < localStorage.length; i++) {
                const key = localStorage.key(i);
                if (key && key.startsWith('emailCache_')) {
                    keysToRemove.push(key);
                }
            }
            if (keysToRemove.length > 0) {
                keysToRemove.forEach(key => localStorage.removeItem(key));
                console.warn(`⚠️  Security: Cleared all email caches (user ID not available)`);
            }
        }
    } catch (error) {
        console.error('Error clearing cross-user cache:', error);
    }
    
    // Initialize IndexedDB thread cache and pre-fetching
    try {
        await initThreadCache();
        await initSentEmailsCache();  // Initialize sent emails cache
        await cleanupOldThreads();
        initThreadPrefetching();
    } catch (error) {
        console.error('Error initializing caches:', error);
    }
    
    // Initialize sidebar state
    initSidebar();
    loadConfig();
    
    // Initialize autosave listeners for composer
    initAutosaveListeners();
    
    // Pre-load signature for instant access when composing/replying
    preloadSignature();
    
    // Start polling for Gmail label changes (real-time bidirectional sync)
    startLabelChangePolling();
    
    // Check if setup is needed and auto-start
    const setupScreen = document.getElementById('setupScreen');
    const urlParams = new URLSearchParams(window.location.search);
    const autoSetup = urlParams.get('auto_setup') === 'true';
    
    // Better setup screen detection - check computed style, not just inline style
    const isSetupScreenVisible = setupScreen && (
        setupScreen.style.display !== 'none' &&
        window.getComputedStyle(setupScreen).display !== 'none'
    );
    
    console.log('🔍 Setup screen check:', {
        setupScreenExists: !!setupScreen,
        inlineStyle: setupScreen?.style?.display,
        computedDisplay: setupScreen ? window.getComputedStyle(setupScreen).display : 'N/A',
        isVisible: isSetupScreenVisible,
        autoSetup: autoSetup
    });
    
    if (isSetupScreenVisible) {
        // Setup screen is visible - auto-start setup
        console.log('📋 Setup screen detected and VISIBLE - auto-starting setup');
        // Always auto-start for setup screen (no need for button click)
        setTimeout(() => startSetup(), 500);
        return;
    }
    
    // Setup screen not visible - check if setup is still needed via API
    try {
        const statusResponse = await fetch('/api/setup/status');
        const statusData = await statusResponse.json();
        console.log('📊 Setup status from API:', statusData);
        
        if (statusData.success && !statusData.setup_completed && statusData.has_gmail) {
            // Setup is needed but screen isn't visible - this shouldn't happen
            // Force reload to get setup screen
            console.warn('⚠️ Setup needed but screen not visible - reloading page');
            window.location.href = '/dashboard?auto_setup=true';
            return;
        }
    } catch (error) {
        console.error('Error checking setup status:', error);
    }
    
    // Enable auto-fetch for users with completed setup
    toggleAutoFetch(true);
    
    // Start background fetching if setup is complete
    try {
        const setupResponse = await fetch('/api/setup/status');
        const setupData = await setupResponse.json();
        if (setupData.success && setupData.setup_completed) {
            // Load emails first and wait for classification to complete
            console.log('📧 Setup complete, loading emails...');
            await loadEmailsFromDatabase();
            
            // Wait a bit for any background classification to complete
            if (allEmails.length > 0 && allEmails.length < 200) {
                console.log(`⏳ Found ${allEmails.length} emails, waiting for more to classify...`);
                let retryCount = 0;
                const maxRetries = 20; // Increased for 200 emails
                while (retryCount < maxRetries && allEmails.length < 200) {
                    await new Promise(resolve => setTimeout(resolve, 1000));
                    await loadEmailsFromDatabase();
                    if (allEmails.length >= 200) break;
                    retryCount++;
                }
                console.log(`✅ Loaded ${allEmails.length} emails after waiting`);
            }
            
            // Display emails if we have any
            if (allEmails.length > 0) {
                applyFilters();
                updatePagination();
            }
            
            startBackgroundFetching();
            // No need to fetch older emails separately - all 200 are fetched upfront
        }
    } catch (error) {
        console.error('Error checking setup status:', error);
    }
    
    // Check if we have cached emails and display them
    const justConnected = urlParams.get('connected') === 'true';
    
    // ALWAYS verify database first before using cache
    // This ensures cache is cleared if database was reset
    try {
        // Load emails and wait for classification to complete
        await loadEmailsFromDatabase();
        
        // If we have some emails but not many, wait a bit for classification to complete
        if (allEmails.length > 0 && allEmails.length < 200) {
            console.log(`⏳ Found ${allEmails.length} emails, waiting for more to classify...`);
            let retryCount = 0;
            const maxRetries = 20; // Increased for 200 emails
            const initialCount = allEmails.length;
            
            while (retryCount < maxRetries && allEmails.length < 200) {
                await new Promise(resolve => setTimeout(resolve, 1000));
                await loadEmailsFromDatabase();
                
                // If we got more emails, continue waiting
                if (allEmails.length > initialCount) {
                    console.log(`📧 Now have ${allEmails.length} emails...`);
                    retryCount = 0; // Reset retry count if we're making progress
                } else {
                    retryCount++;
                }
                
                // If we have 200+ emails, we're done
                if (allEmails.length >= 200) break;
            }
            console.log(`✅ Loaded ${allEmails.length} emails after waiting`);
        }
        
        if (allEmails.length > 0) {
            // Database has emails - use them (they're fresh from database)
            emailCache.data = allEmails;
            emailCache.timestamp = Date.now();
            saveEmailCacheToStorage();
            
            applyFilters();
            
            // Hide loading indicator since emails are loaded
            const loadingEl = document.getElementById('loading');
            if (loadingEl) {
                loadingEl.style.display = 'none';
            }
            const emptyStateInitial = document.getElementById('emptyStateInitial');
            if (emptyStateInitial) {
                emptyStateInitial.style.display = 'none';
            }
            
            const emailCountEl = document.getElementById('emailCount');
            if (emailCountEl) {
                emailCountEl.textContent = `${allEmails.length} email${allEmails.length !== 1 ? 's' : ''}`;
            }
            console.log(`✅ Loaded ${allEmails.length} emails from database`);
        } else {
            // Database is empty - clear any stale cache
            console.log('⚠️  Database is empty. Clearing any stale cache...');
            clearEmailCache();
            allEmails = [];
            applyFilters();
            
            // Show loading indicator instead of "Click Fetch" message
            const loadingEl = document.getElementById('loading');
            if (loadingEl) {
                loadingEl.style.display = 'flex';
            }
            const emailCountEl = document.getElementById('emailCount');
            if (emailCountEl) {
                emailCountEl.textContent = 'Loading emails...';
            }
        }
    } catch (error) {
        console.error('Error loading emails from database:', error);
        // On error, try loading cache as fallback
        loadEmailCacheFromStorage();
        loadStarredCacheFromStorage(); // Load starred emails cache
        loadSentCacheFromStorage(); // Load sent emails cache
        loadDraftsCacheFromStorage(); // Load drafts cache
        loadDealsCacheFromStorage(); // Load deals cache
        if (emailCache.data.length > 0 && emailCache.timestamp) {
            const cacheAge = Date.now() - emailCache.timestamp;
            const isFresh = cacheAge < emailCache.maxAge;
            console.log(`Using cached emails (${emailCache.data.length} emails, cached ${Math.round(cacheAge / 1000)}s ago, ${isFresh ? 'fresh' : 'stale'})`);
            allEmails = emailCache.data;
            applyFilters();
            const emailCountEl = document.getElementById('emailCount');
            if (emailCountEl) {
                // Hide loading indicator if emails are loaded
                const loadingEl2 = document.getElementById('loading');
                if (loadingEl2) {
                    loadingEl2.style.display = 'none';
                }
                emailCountEl.textContent = `${allEmails.length} email${allEmails.length !== 1 ? 's' : ''}${isFresh ? '' : ' (cached)'}`;
            }
        } else {
            const emailCountEl = document.getElementById('emailCount');
            if (emailCountEl) {
                // Show loading indicator
                const loadingEl3 = document.getElementById('loading');
                if (loadingEl3) {
                    loadingEl3.style.display = 'flex';
                }
                emailCountEl.textContent = 'Loading emails...';
            }
        }
    }
    
    // Skip auto-load if just connected
    if (justConnected) {
        console.log('Gmail just connected. Loading emails...');
        const emailCountEl = document.getElementById('emailCount');
        if (emailCountEl) {
            emailCountEl.textContent = 'Click "Fetch" to load emails';
        }
    }
});

// Toggle sidebar collapse
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (sidebar) {
        sidebar.classList.toggle('collapsed');
        // Save state to localStorage
        localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
    }
}

// Initialize sidebar state from localStorage
function initSidebar() {
    const sidebar = document.getElementById('sidebar');
    const savedState = localStorage.getItem('sidebarCollapsed');
    if (sidebar && savedState === 'true') {
        sidebar.classList.add('collapsed');
    }
}

// Toggle star for an email
async function toggleStar(emailId, currentlyStarred, emailIndex) {
    try {
        const star = !currentlyStarred; // Toggle: if currently starred, unstar it
        
        const response = await fetch('/api/toggle-star', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                email_id: emailId,
                star: star
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Update the email in allEmails array
            const email = allEmails.find(e => e.id === emailId);
            if (email) {
                email.is_starred = star;
                if (!email.label_ids) email.label_ids = [];
                if (star && !email.label_ids.includes('STARRED')) {
                    email.label_ids.push('STARRED');
                } else if (!star && email.label_ids.includes('STARRED')) {
                    email.label_ids = email.label_ids.filter(id => id !== 'STARRED');
                }
            }
            
            // Update the email in filteredEmails array
            const filteredEmail = filteredEmails.find(e => e.id === emailId);
            if (filteredEmail) {
                filteredEmail.is_starred = star;
                if (!filteredEmail.label_ids) filteredEmail.label_ids = [];
                if (star && !filteredEmail.label_ids.includes('STARRED')) {
                    filteredEmail.label_ids.push('STARRED');
                } else if (!star && filteredEmail.label_ids.includes('STARRED')) {
                    filteredEmail.label_ids = filteredEmail.label_ids.filter(id => id !== 'STARRED');
                }
            }
            
            // Update cache
            saveEmailCacheToStorage();
            
            // Update starred cache if applicable
            if (star) {
                // Add to starred cache if not already there
                const email = allEmails.find(e => e.id === emailId);
                if (email && !starredEmailsCache.find(e => e.id === emailId)) {
                    starredEmailsCache.push({...email, is_starred: true, classification: { category: 'STARRED' }});
                    saveStarredCacheToStorage(); // Persist to localStorage
                }
            } else {
                // Remove from starred cache
                starredEmailsCache = starredEmailsCache.filter(e => e.id !== emailId);
                saveStarredCacheToStorage(); // Persist to localStorage
            }
            
            // Re-render the email list to show updated star status
            updatePagination(); // Use updatePagination to preserve pagination
            
            // If we're on the starred tab and unstarred, remove from view
            if (currentTab === 'starred' && !star) {
                // Remove from current view
                filteredEmails = filteredEmails.filter(e => e.id !== emailId);
                allEmails = allEmails.filter(e => e.id !== emailId);
                emailCache.data = emailCache.data.filter(e => e.id !== emailId);
                saveEmailCacheToStorage();
                updatePagination(); // Use updatePagination to preserve pagination
            } else if (currentTab === 'starred' && star) {
                // If we starred an email while on starred tab, update cache and refresh view
                if (starredEmailsCache.length > 0) {
                    allEmails = starredEmailsCache;
                    applyFilters();
                } else {
                    // No cache yet, fetch fresh data
                    fetchStarredEmails();
                }
            }
        } else {
            showAlert('error', data.error || 'Failed to toggle star');
        }
    } catch (error) {
        console.error('Error toggling star:', error);
        showAlert('error', 'Failed to toggle star');
    }
}

// Cache for sent, starred, drafts, and deals
let sentEmailsCache = [];
let starredEmailsCache = [];
let draftsCache = [];
let dealsCache = [];

// In-memory thread cache for instant access (populated from IndexedDB)
let threadCacheMemory = new Map();

// Pre-fetch threads for visible emails
async function prefetchVisibleThreads() {
    const visibleEmails = filteredEmails.slice((currentPage - 1) * EMAILS_PER_PAGE, currentPage * EMAILS_PER_PAGE);
    
    // Pre-fetch threads for all visible emails in parallel
    const prefetchPromises = visibleEmails.map(async (email) => {
        if (!email.thread_id) return;
        
        // Check memory cache first
        if (threadCacheMemory.has(email.thread_id)) {
            return; // Already in memory
        }
        
        // Check IndexedDB cache
        try {
            const cached = await getCachedThread(email.thread_id);
            if (cached && cached.emails && cached.emails.length > 0) {
                // Store in memory for instant access
                threadCacheMemory.set(email.thread_id, cached);
            } else {
                // Pre-fetch from API in background
                fetch(`/api/thread/${email.thread_id}`)
                    .then(res => res.json())
                    .then(data => {
                        if (data.success && data.emails) {
                            cacheThread(email.thread_id, data);
                            threadCacheMemory.set(email.thread_id, data);
                        }
                    })
                    .catch(err => console.warn('Prefetch error:', err));
            }
        } catch (err) {
            console.warn('Cache check error:', err);
        }
    });
    
    // Don't await - let it run in background
    Promise.all(prefetchPromises).catch(() => {});
}

// Load starred emails cache from localStorage on init
function loadStarredCacheFromStorage() {
    try {
        const cacheKey = 'starredEmailsCache';
        const cached = localStorage.getItem(cacheKey);
        if (cached) {
            const parsed = JSON.parse(cached);
            if (parsed.data && Array.isArray(parsed.data)) {
                starredEmailsCache = parsed.data;
                console.log(`📦 Loaded ${starredEmailsCache.length} starred emails from localStorage cache`);
            }
        }
    } catch (e) {
        console.warn('Failed to load starred cache from localStorage:', e);
    }
}

// Save starred emails cache to localStorage
function saveStarredCacheToStorage() {
    try {
        const cacheKey = 'starredEmailsCache';
        localStorage.setItem(cacheKey, JSON.stringify({
            data: starredEmailsCache,
            timestamp: Date.now()
        }));
    } catch (e) {
        console.warn('Failed to save starred cache to localStorage:', e);
    }
}

// Switch between tabs
function switchTab(tabName) {
    currentTab = tabName;
    
    // Update tab buttons (both old and compact versions, and sidebar items)
    document.querySelectorAll('.tab-btn, .tab-btn-compact, .sidebar-item').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.tab === tabName) {
            btn.classList.add('active');
        }
    });
    
    // Show/hide appropriate views
    const emailList = document.getElementById('emailList');
    const dealFlowTable = document.getElementById('dealFlowTable');
    
    if (tabName === 'deal-flow') {
        emailList.style.display = 'none';
        dealFlowTable.style.display = 'block';
        
        // Show cached deals immediately if available (instant load - 0ms)
        if (dealsCache.length > 0) {
            console.log(`⚡ [DEALS] Showing ${dealsCache.length} deals from cache (instant)`);
            displayDeals(dealsCache);
        } else {
            // Show loading state immediately
            const tbody = document.getElementById('dealFlowBody');
            if (tbody) {
                tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Loading deals...</td></tr>';
            }
            console.log('📊 [DEALS] No cache available, will fetch from API');
        }
        
        // Fetch fresh data in background (non-blocking)
        loadDeals();
    } else if (tabName === 'scheduled') {
        emailList.style.display = 'block';
        dealFlowTable.style.display = 'none';
        
        // Show loading state
        const emailListEl = document.getElementById('emailList');
        if (emailListEl) {
            emailListEl.innerHTML = '<div class="empty-state"><div class="spinner"></div><p>Loading scheduled emails...</p></div>';
        }
        
        // Fetch scheduled emails
        fetchScheduledEmails();
    } else if (tabName === 'sent') {
        emailList.style.display = 'block';
        dealFlowTable.style.display = 'none';
        
        // CRITICAL: Don't set allEmails for sent tab - use sentEmailsCache directly
        // Show cached data immediately if available (instant load)
        if (sentEmailsCache.length > 0) {
            console.log(`⚡ Showing ${sentEmailsCache.length} sent emails from cache (instant)`);
            // Don't set allEmails - applyFilters will use sentEmailsCache directly
            applyFilters();
            const emailCountEl = document.getElementById('emailCount');
            if (emailCountEl) {
                const searchText = searchQuery ? ` (${filteredEmails.length} found)` : '';
                emailCountEl.textContent = `${sentEmailsCache.length} sent email${sentEmailsCache.length !== 1 ? 's' : ''}${searchText}`;
            }
        } else {
            // Show loading indicator with nice message
            const emailList = document.getElementById('emailList');
            if (emailList) {
                emailList.innerHTML = `
                    <div class="empty-state" style="text-align: center; padding: 60px 20px;">
                        <div class="spinner" style="width: 40px; height: 40px; margin: 0 auto 20px; border: 3px solid rgba(99, 102, 241, 0.1); border-top-color: #6366f1; border-radius: 50%; animation: spin 1s linear infinite;"></div>
                        <p style="font-size: 16px; color: var(--text-primary); margin-bottom: 8px; font-weight: 500;">Loading your sent emails...</p>
                        <p style="font-size: 14px; color: var(--text-secondary);">Just a moment, we're gathering them for you ✨</p>
                    </div>
                `;
            }
            const emailCountEl = document.getElementById('emailCount');
            if (emailCountEl) {
                emailCountEl.textContent = 'Loading...';
            }
        }
        
        // Fetch fresh data in background (non-blocking)
        fetchSentEmails();
    } else if (tabName === 'starred') {
        emailList.style.display = 'block';
        dealFlowTable.style.display = 'none';
        
        // INSTANT: Filter starred emails from local email cache (no API call needed)
        const starredFromCache = (emailCache.data || allEmails || []).filter(email => {
            return email.is_starred === true || 
                   email.starred === true || 
                   (email.label_ids && email.label_ids.includes('STARRED'));
        });
        
        if (starredFromCache.length > 0) {
            console.log(`⚡ Showing ${starredFromCache.length} starred emails from local cache (instant)`);
            allEmails = starredFromCache;
            starredEmailsCache = starredFromCache; // Update in-memory cache
            applyFilters();
            const emailCountEl = document.getElementById('emailCount');
            if (emailCountEl) {
                const searchText = searchQuery ? ` (${filteredEmails.length} found)` : '';
                emailCountEl.textContent = `${starredFromCache.length} starred email${starredFromCache.length !== 1 ? 's' : ''} (local)${searchText}`;
            }
        } else if (starredEmailsCache.length > 0) {
            // Fallback to in-memory cache if available
            allEmails = starredEmailsCache;
            applyFilters();
            const emailCountEl = document.getElementById('emailCount');
            if (emailCountEl) {
                const searchText = searchQuery ? ` (${filteredEmails.length} found)` : '';
                emailCountEl.textContent = `${starredEmailsCache.length} starred email${starredEmailsCache.length !== 1 ? 's' : ''} (cached)${searchText}`;
            }
        } else {
            // Show loading indicator with nice message
            const emailList = document.getElementById('emailList');
            if (emailList) {
                emailList.innerHTML = `
                    <div class="empty-state" style="text-align: center; padding: 60px 20px;">
                        <div class="spinner" style="width: 40px; height: 40px; margin: 0 auto 20px; border: 3px solid rgba(99, 102, 241, 0.1); border-top-color: #6366f1; border-radius: 50%; animation: spin 1s linear infinite;"></div>
                        <p style="font-size: 16px; color: var(--text-primary); margin-bottom: 8px; font-weight: 500;">Loading your starred emails...</p>
                        <p style="font-size: 14px; color: var(--text-secondary);">Just a moment, we're gathering them for you ✨</p>
                    </div>
                `;
            }
            const emailCountEl = document.getElementById('emailCount');
            if (emailCountEl) {
                emailCountEl.textContent = 'Loading starred emails...';
            }
        }
        
        // Fetch fresh data in background (non-blocking)
        fetchStarredEmails();
    } else if (tabName === 'drafts') {
        emailList.style.display = 'block';
        dealFlowTable.style.display = 'none';
        
        // Show cached data immediately if available (instant load)
        if (draftsCache.length > 0) {
            console.log(`⚡ Showing ${draftsCache.length} drafts from cache (instant)`);
            allEmails = draftsCache;
            applyFilters();
            const emailCountEl = document.getElementById('emailCount');
            if (emailCountEl) {
                const searchText = searchQuery ? ` (${filteredEmails.length} found)` : '';
                emailCountEl.textContent = `${draftsCache.length} draft${draftsCache.length !== 1 ? 's' : ''}${searchText}`;
            }
        } else {
            // Show loading indicator with nice message
            const emailList = document.getElementById('emailList');
            if (emailList) {
                emailList.innerHTML = `
                    <div class="empty-state" style="text-align: center; padding: 60px 20px;">
                        <div class="spinner" style="width: 40px; height: 40px; margin: 0 auto 20px; border: 3px solid rgba(99, 102, 241, 0.1); border-top-color: #6366f1; border-radius: 50%; animation: spin 1s linear infinite;"></div>
                        <p style="font-size: 16px; color: var(--text-primary); margin-bottom: 8px; font-weight: 500;">Loading your drafts...</p>
                        <p style="font-size: 14px; color: var(--text-secondary);">Just a moment, we're gathering them for you ✨</p>
                    </div>
                `;
            }
            const emailCountEl = document.getElementById('emailCount');
            if (emailCountEl) {
                emailCountEl.textContent = 'Loading drafts...';
            }
        }
        
        // Fetch fresh data in background (non-blocking)
        fetchDrafts();
    } else {
        emailList.style.display = 'block';
        dealFlowTable.style.display = 'none';
        
        // Use cached emails if available, otherwise show empty state
        if (emailCache.data.length > 0) {
            allEmails = emailCache.data;
            applyFilters(); // Use applyFilters to include search query
            const emailCountEl = document.getElementById('emailCount');
            if (emailCountEl) {
                const searchText = searchQuery ? ` (${filteredEmails.length} found)` : '';
                emailCountEl.textContent = `${allEmails.length} email${allEmails.length !== 1 ? 's' : ''} (cached)${searchText}`;
            }
        } else {
            // No cache - just filter (will show empty state)
            applyFilters(); // Use applyFilters to include search query
        }
    }
}

// Fetch scheduled emails
async function fetchScheduledEmails() {
    try {
        const response = await fetch('/api/scheduled-emails');
        if (!response.ok) {
            const errorText = await response.text();
            console.error(`❌ [FRONTEND] HTTP ${response.status} error:`, errorText);
            // Check if the response is HTML (e.g., Flask error page)
            if (errorText.startsWith('<')) {
                throw new Error(`Server returned text/html instead of JSON. Status: ${response.status}`);
            }
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        const contentType = response.headers.get("content-type");
        if (!contentType || !contentType.includes("application/json")) {
            const errorText = await response.text();
            console.error(`❌ [FRONTEND] Expected JSON, but received:`, contentType, errorText);
            throw new Error(`Server returned ${contentType || 'unknown content type'} instead of JSON.`);
        }
        const data = await response.json();
        
        if (data.success) {
            displayScheduledEmails(data.scheduled_emails || []);
        } else {
            console.error('Error fetching scheduled emails:', data.error);
            const emailList = document.getElementById('emailList');
            if (emailList) {
                emailList.innerHTML = `<div class="empty-state"><p>Error loading scheduled emails: ${data.error || 'Unknown error'}</p></div>`;
            }
        }
    } catch (error) {
        console.error('Error fetching scheduled emails:', error);
        const emailList = document.getElementById('emailList');
        if (emailList) {
            emailList.innerHTML = `<div class="empty-state"><p>Error loading scheduled emails. Please try again.</p></div>`;
        }
    }
}

// Display scheduled emails
function displayScheduledEmails(scheduledEmails) {
    const emailList = document.getElementById('emailList');
    if (!emailList) return;
    
    if (scheduledEmails.length === 0) {
        emailList.innerHTML = '<div class="empty-state"><p>No scheduled emails</p></div>';
        const emailCountEl = document.getElementById('emailCount');
        if (emailCountEl) {
            emailCountEl.textContent = '0 scheduled emails';
        }
        return;
    }
    
    // Update email count
    const emailCountEl = document.getElementById('emailCount');
    if (emailCountEl) {
        emailCountEl.textContent = `${scheduledEmails.length} scheduled email${scheduledEmails.length !== 1 ? 's' : ''}`;
    }
    
    // Format scheduled emails to look like regular emails for display
    const formattedEmails = scheduledEmails.map((scheduled, index) => {
        const scheduledDate = new Date(scheduled.scheduled_at);
        const now = new Date();
        const timeUntil = scheduledDate - now;
        const hoursUntil = Math.floor(timeUntil / (1000 * 60 * 60));
        const minutesUntil = Math.floor((timeUntil % (1000 * 60 * 60)) / (1000 * 60));
        
        let timeText = '';
        if (timeUntil <= 0) {
            timeText = 'Due now';
        } else if (hoursUntil > 0) {
            timeText = `In ${hoursUntil}h ${minutesUntil}m`;
        } else {
            timeText = `In ${minutesUntil}m`;
        }
        
        return {
            id: `scheduled-${scheduled.id}`,
            scheduled_id: scheduled.id,
            thread_id: scheduled.thread_id,
            subject: scheduled.subject,
            from: scheduled.to,
            to: scheduled.to,
            snippet: scheduled.body.replace(/<[^>]*>/g, '').substring(0, 100) + '...',
            date: scheduled.scheduled_at,
            scheduled_at: scheduled.scheduled_at,
            time_until: timeText,
            founder_name: scheduled.founder_name,
            deal_subject: scheduled.deal_subject,
            is_scheduled: true
        };
    });
    
    // Display emails
    emailList.innerHTML = formattedEmails.map((email, index) => {
        const date = new Date(email.scheduled_at);
        const dateStr = date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        
        return `
            <div class="email-card" onclick="openScheduledEmail(${email.scheduled_id})" style="cursor: pointer;">
                <div class="email-header">
                    <div class="email-sender">
                        <strong>${escapeHtml(email.to || 'Unknown')}</strong>
                        ${email.founder_name ? `<span class="email-meta"> - ${escapeHtml(email.founder_name)}</span>` : ''}
                    </div>
                    <div class="email-date">${dateStr}</div>
                </div>
                <div class="email-subject">${escapeHtml(email.subject || 'No Subject')}</div>
                <div class="email-snippet">${escapeHtml(email.snippet || '')}</div>
                <div class="email-meta" style="margin-top: 8px; color: var(--primary-color); font-weight: 500;">
                    ⏰ Scheduled: ${email.time_until}
                </div>
                <div style="margin-top: 8px;">
                    <button class="btn btn-small btn-secondary" onclick="event.stopPropagation(); cancelScheduledEmail(${email.scheduled_id})" style="margin-right: 8px;">
                        Cancel
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

// Open scheduled email in modal
async function openScheduledEmail(scheduledId) {
    try {
        const response = await fetch(`/api/scheduled-email/${scheduledId}`);
        if (!response.ok) {
            const errorText = await response.text();
            console.error(`❌ [FRONTEND] HTTP ${response.status} error:`, errorText);
            if (errorText.startsWith('<')) {
                throw new Error(`Server returned text/html instead of JSON. Status: ${response.status}`);
            }
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        const contentType = response.headers.get("content-type");
        if (!contentType || !contentType.includes("application/json")) {
            const errorText = await response.text();
            console.error(`❌ [FRONTEND] Expected JSON, but received:`, contentType, errorText);
            throw new Error(`Server returned ${contentType || 'unknown content type'} instead of JSON.`);
        }
        const data = await response.json();
        
        if (data.success && data.scheduled_email) {
            const email = data.scheduled_email;
            
            // Create a mock email object for the modal
            currentEmail = {
                id: `scheduled-${email.id}`,
                scheduled_id: email.id,
                thread_id: email.thread_id,
                subject: email.subject,
                from: email.to,
                to: email.to,
                body: email.body,
                scheduled_at: email.scheduled_at,
                founder_name: email.founder_name,
                deal_subject: email.deal_subject,
                is_scheduled: true
            };
            
            // Open email modal
            const emailModal = document.getElementById('emailModal');
            if (emailModal) {
                emailModal.style.display = 'flex';
            }
            
            // Populate modal with scheduled email data
            const modalSubject = document.getElementById('modalSubject');
            const modalSender = document.getElementById('modalSender');
            const modalDate = document.getElementById('modalDate');
            const threadContainer = document.getElementById('threadContainer');
            
            if (modalSubject) modalSubject.textContent = email.subject || 'No Subject';
            if (modalSender) modalSender.textContent = email.to || 'Unknown';
            if (modalDate) {
                const date = new Date(email.scheduled_at);
                modalDate.textContent = `Scheduled: ${date.toLocaleString()}`;
            }
            
            // Hide reply section for scheduled emails (can't reply to unsent emails)
            const replySection = document.getElementById('replySection');
            if (replySection) {
                replySection.style.display = 'none';
            }
            
            // Hide single email section, show thread container
            const singleEmailSection = document.getElementById('singleEmailSection');
            if (singleEmailSection) {
                singleEmailSection.style.display = 'none';
            }
            
            if (threadContainer) {
                threadContainer.innerHTML = `
                    <div class="email-body" style="padding: 20px; background: white; border-radius: 8px; margin-bottom: 16px;">
                        <div style="margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px solid var(--border-color);">
                            <div style="color: var(--primary-color); font-weight: 600; margin-bottom: 8px;">📅 Scheduled Email</div>
                            <div style="color: var(--text-secondary); font-size: 14px;">
                                This email will be sent automatically if no reply is sent before the scheduled time.
                            </div>
                        </div>
                        <div style="white-space: pre-wrap; line-height: 1.6;">${email.body}</div>
                    </div>
                `;
            }
        } else {
            showToast('Error loading scheduled email', 'error');
        }
    } catch (error) {
        console.error('Error opening scheduled email:', error);
        showToast('Error loading scheduled email', 'error');
    }
}

// Cancel scheduled email
async function cancelScheduledEmail(scheduledId) {
    if (!confirm('Are you sure you want to cancel this scheduled email?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/scheduled-email/${scheduledId}/cancel`, {
            method: 'POST'
        });
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error(`❌ [FRONTEND] HTTP ${response.status} error:`, errorText);
            if (errorText.startsWith('<')) {
                throw new Error(`Server returned text/html instead of JSON. Status: ${response.status}`);
            }
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        const contentType = response.headers.get("content-type");
        if (!contentType || !contentType.includes("application/json")) {
            const errorText = await response.text();
            console.error(`❌ [FRONTEND] Expected JSON, but received:`, contentType, errorText);
            throw new Error(`Server returned ${contentType || 'unknown content type'} instead of JSON.`);
        }
        const data = await response.json();
        
        if (data.success) {
            showToast('Scheduled email cancelled', 'success');
            // Refresh scheduled emails list
            if (currentTab === 'scheduled') {
                fetchScheduledEmails();
            }
        } else {
            showToast(data.error || 'Failed to cancel scheduled email', 'error');
        }
    } catch (error) {
        console.error('Error cancelling scheduled email:', error);
        showToast('Error cancelling scheduled email', 'error');
    }
}

// Fetch starred emails
async function fetchStarredEmails() {
    try {
        const response = await fetch(`/api/starred-emails?max=100`);
        const data = await response.json();
        
        if (data.success) {
            // Format starred emails similar to received emails
            const starredEmails = data.emails.map(email => {
                const labelIds = email.label_ids || [];
                if (!labelIds.includes('STARRED')) {
                    labelIds.push('STARRED');
                }
                return {
                    ...email,
                    classification: { category: 'STARRED' },
                    is_starred: true,
                    starred: true, // Also set starred property for filter compatibility
                    label_ids: labelIds
                };
            });
            
            // Update cache (both in-memory and localStorage)
            starredEmailsCache = starredEmails;
            saveStarredCacheToStorage(); // Persist to localStorage
            
            // Only update UI if we're still on the starred tab
            if (currentTab === 'starred') {
                allEmails = starredEmails;
                applyFilters(); // Apply filters including search
                
                const emailCountEl = document.getElementById('emailCount');
                if (emailCountEl) {
                    const searchText = searchQuery ? ` (${filteredEmails.length} found)` : '';
                    emailCountEl.textContent = `${starredEmails.length} starred email${starredEmails.length !== 1 ? 's' : ''}${searchText}`;
                }
                
                // Only display if we have starred emails - don't show "no emails" if we actually have them
                if (starredEmails.length > 0) {
                    // Force display - use filteredEmails if available, otherwise use starredEmails
                    const emailsToDisplay = filteredEmails.length > 0 ? filteredEmails : starredEmails;
                    console.log(`⭐ [FRONTEND] Displaying ${emailsToDisplay.length} starred emails`);
                    displayEmails(emailsToDisplay);
                } else {
                    // Only show "no emails" if we actually have no starred emails
                    console.log(`⭐ [FRONTEND] No starred emails found, showing empty state`);
                    displayEmails([]);
                }
            }
        } else {
            console.error('Error fetching starred emails:', data.error);
            if (currentTab === 'starred') {
                // Only show error if we don't have cached starred emails
                if (starredEmailsCache.length === 0) {
                displayEmails([]);
                }
            }
        }
    } catch (error) {
        console.error('Error fetching starred emails:', error);
        if (currentTab === 'starred') {
            // Only show error if we don't have cached starred emails
            if (starredEmailsCache.length === 0) {
            displayEmails([]);
            }
        }
    }
}

// Fetch sent emails
async function fetchSentEmails() {
    // Prevent concurrent fetches
    if (isFetchingSentEmails) {
        console.log('⏳ [SENT] Already fetching sent emails, skipping...');
        return;
    }
    
    // Check if paused due to rate limit
    if (sentEmailsFetchPausedUntil && Date.now() < sentEmailsFetchPausedUntil) {
        const minutesLeft = Math.ceil((sentEmailsFetchPausedUntil - Date.now()) / 60000);
        console.log(`⏸️ [SENT] Sent email fetch paused due to rate limit. Resuming in ${minutesLeft} minute${minutesLeft !== 1 ? 's' : ''}`);
        return;
    }
    
    // Clear pause if time has passed
    if (sentEmailsFetchPausedUntil && Date.now() >= sentEmailsFetchPausedUntil) {
        sentEmailsFetchPausedUntil = null;
        console.log('✅ [SENT] Rate limit pause expired, resuming sent email fetches');
    }
    
    try {
        isFetchingSentEmails = true;
        console.log('📤 [FRONTEND] Fetching sent emails...');
        
        // Get user ID for cache
        const userId = document.body.dataset.userId;
        
        // Check IndexedDB cache first (with better error handling)
        if (userId && sentEmailsCacheDB) {
            try {
                const cached = await getCachedSentEmails(userId);
                if (cached && cached.length > 0) {
                    console.log(`📧 [SENT] Loaded ${cached.length} sent emails from IndexedDB cache (SKIPPING API CALL)`);
                    sentEmailsCache = cached;
                    
                    // Update UI if on sent tab
                    if (currentTab === 'sent') {
                        applyFilters();
                        const emailCountEl = document.getElementById('emailCount');
                        if (emailCountEl) {
                            const searchText = searchQuery ? ` (${filteredEmails.length} found)` : '';
                            emailCountEl.textContent = `${cached.length} sent email${cached.length !== 1 ? 's' : ''}${searchText}`;
                        }
                        if (cached.length > 0) {
                            displayEmails(filteredEmails.length > 0 ? filteredEmails : cached);
                        }
                    }
                    isFetchingSentEmails = false;
                    return; // Exit early - no API call needed
                }
            } catch (cacheError) {
                console.warn('⚠️ [SENT] Cache check failed:', cacheError);
                // Continue to API call
            }
        } else if (!sentEmailsCacheDB) {
            console.warn('⚠️ [SENT] IndexedDB cache not initialized, will fetch from API');
        }
        
        console.log('📤 [FRONTEND] No cache found or cache expired, calling /api/sent-emails?max=100');
        
        const response = await fetch(`/api/sent-emails?max=100`);
        
        console.log(`📤 [FRONTEND] Response status: ${response.status}`);
        
        // Handle rate limit (429) - pause for 15 minutes
        if (response.status === 429) {
            sentEmailsFetchPausedUntil = Date.now() + (15 * 60 * 1000); // 15 minutes
            console.warn('⚠️ [SENT] Rate limit hit! Pausing sent email fetches for 15 minutes');
            showToast('Gmail rate limit reached. Sent emails will refresh in 15 minutes.', 'warning');
            isFetchingSentEmails = false;
            return;
        }
        
        // Check if response is JSON before parsing
        const contentType = response.headers.get('content-type') || '';
        if (!contentType.includes('application/json')) {
            const errorText = await response.text();
            // Check for rate limit in text response
            if (errorText.includes('rate') || errorText.includes('429') || errorText.includes('limit')) {
                sentEmailsFetchPausedUntil = Date.now() + (15 * 60 * 1000);
                console.warn('⚠️ [SENT] Rate limit detected in response. Pausing for 15 minutes');
                isFetchingSentEmails = false;
                return;
            }
            console.error(`❌ [FRONTEND] Expected JSON but got ${contentType}. Response:`, errorText.substring(0, 500));
            throw new Error(`Server returned ${contentType} instead of JSON. Status: ${response.status}`);
        }
        
        if (!response.ok) {
            const errorText = await response.text();
            console.error(`❌ [FRONTEND] HTTP ${response.status} error:`, errorText);
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log(`📤 [FRONTEND] Response data:`, data);
        console.log(`📤 [FRONTEND] Success: ${data.success}, Count: ${data.count || 0}`);
        
        if (data.success) {
            // Format sent emails similar to received emails
            const sentEmails = (data.emails || []).map(email => ({
                ...email,
                classification: { category: 'SENT' },
                is_sent: true
            }));
            
            console.log(`✅ [FRONTEND] Fetched ${sentEmails.length} sent emails`);
            // Debug: Log first sent email to check if subjects are present
            if (sentEmails.length > 0) {
                console.log(`📤 [DEBUG] First sent email:`, {
                    id: sentEmails[0].id,
                    subject: sentEmails[0].subject,
                    to: sentEmails[0].to,
                    from: sentEmails[0].from
                });
            }
            
            // Update cache (memory, localStorage, and IndexedDB)
            sentEmailsCache = sentEmails;
            saveSentCacheToStorage();
            
            // Cache in IndexedDB
            if (userId) {
                await cacheSentEmails(userId, sentEmails);
            }
            
            // Only update UI if we're still on the sent tab
            if (currentTab === 'sent') {
                console.log(`📤 [FRONTEND] Updating UI with ${sentEmails.length} sent emails`);
                // CRITICAL: Don't set allEmails - applyFilters will use sentEmailsCache directly
                // This prevents inbox emails from overwriting sent emails
                applyFilters(); // Apply filters including search (uses sentEmailsCache, not allEmails)
                
                console.log(`📤 [FRONTEND] After applyFilters: ${filteredEmails.length} filtered emails`);
                console.log(`📤 [FRONTEND] Sample email:`, sentEmails[0]);
                
                const emailCountEl = document.getElementById('emailCount');
                if (emailCountEl) {
                    const searchText = searchQuery ? ` (${filteredEmails.length} found)` : '';
                    emailCountEl.textContent = `${sentEmails.length} sent email${sentEmails.length !== 1 ? 's' : ''}${searchText}`;
                }
                
                // Only display if we have emails - don't show "no emails" if we actually have them
                if (sentEmails.length > 0) {
                    // Force display - use filteredEmails if available, otherwise use sentEmails
                    const emailsToDisplay = filteredEmails.length > 0 ? filteredEmails : sentEmails;
                    console.log(`📤 [FRONTEND] Displaying ${emailsToDisplay.length} emails`);
                    displayEmails(emailsToDisplay);
                } else {
                    // Only show "no emails" if we actually have no emails
                    console.log(`📤 [FRONTEND] No sent emails found, showing empty state`);
                    displayEmails([]);
            }
        } else {
                console.log(`📤 [FRONTEND] Not on sent tab (currentTab=${currentTab}), skipping UI update`);
            }
        } else {
            console.error('❌ [FRONTEND] Error fetching sent emails:', data.error);
            if (currentTab === 'sent') {
                const emailList = document.getElementById('emailList');
                if (emailList) {
                    emailList.innerHTML = `
                        <div class="empty-state" style="text-align: center; padding: 60px 20px;">
                            <p style="font-size: 16px; color: var(--text-primary); margin-bottom: 8px; font-weight: 500;">Unable to load sent emails</p>
                            <p style="font-size: 14px; color: var(--text-secondary);">${data.error || 'Please try refreshing the page'}</p>
                        </div>
                    `;
                }
                showToast(`Failed to load sent emails: ${data.error || 'Unknown error'}`, 'error');
            }
        }
    } catch (error) {
        console.error('❌ [FRONTEND] Exception fetching sent emails:', error);
        console.error('❌ [FRONTEND] Error stack:', error.stack);
        
        // Check if it's a rate limit error in the exception
        const errorMsg = error.message || '';
        if (errorMsg.includes('429') || errorMsg.includes('rate') || errorMsg.includes('limit')) {
            sentEmailsFetchPausedUntil = Date.now() + (15 * 60 * 1000);
            console.warn('⚠️ [SENT] Rate limit detected in exception. Pausing for 15 minutes');
        }
        
        if (currentTab === 'sent') {
            const emailList = document.getElementById('emailList');
            if (emailList) {
                emailList.innerHTML = `
                    <div class="empty-state" style="text-align: center; padding: 60px 20px;">
                        <p style="font-size: 16px; color: var(--text-primary); margin-bottom: 8px; font-weight: 500;">Unable to load sent emails</p>
                        <p style="font-size: 14px; color: var(--text-secondary);">Please try refreshing the page</p>
                    </div>
                `;
            }
            showToast(`Failed to load sent emails: ${error.message}`, 'error');
        }
    } finally {
        // Always reset the flag
        isFetchingSentEmails = false;
    }
}

function saveSentCacheToStorage() {
    try {
        localStorage.setItem('sentEmailsCache', JSON.stringify(sentEmailsCache));
        console.log(`💾 Saved ${sentEmailsCache.length} sent emails to localStorage`);
    } catch (error) {
        console.error('Error saving sent cache:', error);
    }
}

function loadSentCacheFromStorage() {
    try {
        const cached = localStorage.getItem('sentEmailsCache');
        if (cached) {
            sentEmailsCache = JSON.parse(cached);
            console.log(`⚡ Loaded ${sentEmailsCache.length} sent emails from localStorage`);
        }
    } catch (error) {
        console.error('Error loading sent cache:', error);
        sentEmailsCache = [];
    }
}

// Fetch drafts
async function fetchDrafts() {
    try {
        const response = await fetch(`/api/drafts?max=100`);
        const data = await response.json();
        
        if (data.success) {
            // Format drafts similar to received emails
            const drafts = data.emails.map(email => ({
                ...email,
                classification: { category: 'DRAFT' },
                is_draft: true
            }));
            
            // Update cache (both memory and localStorage)
            draftsCache = drafts;
            saveDraftsCacheToStorage();
            
            // Only update UI if we're still on the drafts tab
            if (currentTab === 'drafts') {
                allEmails = drafts;
                applyFilters(); // Apply filters including search
                
                const emailCountEl = document.getElementById('emailCount');
                if (emailCountEl) {
                    const searchText = searchQuery ? ` (${filteredEmails.length} found)` : '';
                    emailCountEl.textContent = `${drafts.length} draft${drafts.length !== 1 ? 's' : ''}${searchText}`;
                }
                
                // Only display if we have drafts - don't show "no emails" if we actually have them
                if (drafts.length > 0) {
                    // Force display - use filteredEmails if available, otherwise use drafts
                    const emailsToDisplay = filteredEmails.length > 0 ? filteredEmails : drafts;
                    console.log(`📝 [FRONTEND] Displaying ${emailsToDisplay.length} drafts`);
                    displayEmails(emailsToDisplay);
                } else {
                    // Only show "no emails" if we actually have no drafts
                    console.log(`📝 [FRONTEND] No drafts found, showing empty state`);
                    displayEmails([]);
                }
            }
        } else {
            console.error('Error fetching drafts:', data.error);
            if (currentTab === 'drafts') {
                // Only show error if we don't have cached drafts
                if (draftsCache.length === 0) {
                displayEmails([]);
                }
            }
        }
    } catch (error) {
        console.error('Error fetching drafts:', error);
        if (currentTab === 'drafts') {
            // Only show error if we don't have cached drafts
            if (draftsCache.length === 0) {
            displayEmails([]);
            }
        }
    }
}

function saveDraftsCacheToStorage() {
    try {
        localStorage.setItem('draftsCache', JSON.stringify(draftsCache));
        console.log(`💾 Saved ${draftsCache.length} drafts to localStorage`);
    } catch (error) {
        console.error('Error saving drafts cache:', error);
    }
}

function loadDraftsCacheFromStorage() {
    try {
        const cached = localStorage.getItem('draftsCache');
        if (cached) {
            draftsCache = JSON.parse(cached);
            console.log(`⚡ Loaded ${draftsCache.length} drafts from localStorage`);
        }
    } catch (error) {
        console.error('Error loading drafts cache:', error);
        draftsCache = [];
    }
}

function saveDealsCacheToStorage() {
    try {
        localStorage.setItem('dealsCache', JSON.stringify(dealsCache));
        console.log(`💾 Saved ${dealsCache.length} deals to localStorage`);
    } catch (error) {
        console.error('Error saving deals cache:', error);
    }
}

function loadDealsCacheFromStorage() {
    try {
        const cached = localStorage.getItem('dealsCache');
        if (cached) {
            dealsCache = JSON.parse(cached);
            console.log(`⚡ Loaded ${dealsCache.length} deals from localStorage`);
        }
    } catch (error) {
        console.error('Error loading deals cache:', error);
        dealsCache = [];
    }
}

// Search functionality
function handleSearchInput(value) {
    searchQuery = value.trim().toLowerCase();
    const clearBtn = document.getElementById('searchClear');
    if (clearBtn) {
        clearBtn.style.display = searchQuery ? 'flex' : 'none';
    }
    applyFilters();
}

function handleSearch(event) {
    if (event.key === 'Enter') {
        event.preventDefault();
        applyFilters();
    }
}

function clearSearch() {
    const searchInput = document.getElementById('emailSearch');
    if (searchInput) {
        searchInput.value = '';
        searchQuery = '';
        const clearBtn = document.getElementById('searchClear');
        if (clearBtn) {
            clearBtn.style.display = 'none';
        }
        applyFilters();
    }
}

// Apply both category and search filters
function applyFilters() {
    // Reset to first page when filters change
    currentPage = 1;
    
    // Ensure allEmails is an array
    if (!Array.isArray(allEmails)) {
        console.warn('⚠️ allEmails is not an array, resetting to empty array');
        allEmails = [];
    }
    
    // CRITICAL: For sent/drafts/starred tabs, use their dedicated caches, NOT allEmails
    // allEmails is for inbox emails only - don't mix them!
    let filtered;
    
    if (currentTab === 'sent') {
        // Use sentEmailsCache directly - never use allEmails for sent emails
        filtered = sentEmailsCache || [];
        console.log(`🔍 [FILTER] Sent tab: Using ${filtered.length} emails from sentEmailsCache (NOT allEmails)`);
    } else if (currentTab === 'drafts') {
        // Use draftsCache directly
        filtered = draftsCache || [];
        console.log(`🔍 [FILTER] Drafts tab: Using ${filtered.length} emails from draftsCache (NOT allEmails)`);
    } else if (currentTab === 'starred') {
        // Use starredEmailsCache directly
        filtered = starredEmailsCache || [];
        console.log(`🔍 [FILTER] Starred tab: Using ${filtered.length} emails from starredEmailsCache (NOT allEmails)`);
    } else {
        // For inbox and category tabs, use allEmails
        filtered = allEmails;
    }
    
    // Apply category filter - check both email.category and email.classification?.category
    if (currentTab === 'networking') {
        filtered = allEmails.filter(e => {
            const cat = e.category || e.classification?.category || '';
            return cat.toLowerCase() === 'networking';
        });
    } else if (currentTab === 'hiring') {
        filtered = allEmails.filter(e => {
            const cat = e.category || e.classification?.category || '';
            return cat.toLowerCase() === 'hiring';
        });
    } else if (currentTab === 'general') {
        filtered = allEmails.filter(e => {
            const cat = e.category || e.classification?.category || '';
            return cat.toLowerCase() === 'general';
        });
    } else if (currentTab === 'spam') {
        filtered = allEmails.filter(e => {
            const cat = e.category || e.classification?.category || '';
            return cat.toLowerCase() === 'spam';
        });
    } else if (currentTab === 'dealflow' || currentTab === 'deal-flow') {
        filtered = allEmails.filter(e => {
            const cat = e.category || e.classification?.category || '';
            return cat.toLowerCase() === 'dealflow' || cat.toLowerCase() === 'deal_flow';
        });
    } else if (currentTab === 'starred') {
        filtered = allEmails.filter(e => {
            // Check multiple ways an email can be starred
            return e.is_starred === true || 
                   e.starred === true || 
                   (e.label_ids && e.label_ids.includes('STARRED'));
        });
    }
    // 'all' shows everything
    
    // Apply search filter if query exists
    if (searchQuery) {
        filtered = filtered.filter(email => {
            const subject = (email.subject || '').toLowerCase();
            const from = (email.from || '').toLowerCase();
            const snippet = (email.snippet || '').toLowerCase();
            const body = (email.body || email.combined_text || '').toLowerCase();
            
            return subject.includes(searchQuery) ||
                   from.includes(searchQuery) ||
                   snippet.includes(searchQuery) ||
                   body.includes(searchQuery);
        });
    }
    
    // Sort filtered emails by date (newest first) before storing and displaying
    const sortedFiltered = [...filtered].sort((a, b) => {
        const dateA = a.date || 0;
        const dateB = b.date || 0;
        return dateB - dateA; // Descending order (newest first)
    });
    
    filteredEmails = sortedFiltered; // Store sorted filtered emails for openEmail
    
    console.log(`🔍 applyFilters: allEmails=${allEmails.length}, filtered=${filtered.length}, sortedFiltered=${sortedFiltered.length}, currentTab=${currentTab}`);
    
    // Check if emailList element exists before trying to display
    const emailListEl = document.getElementById('emailList');
    if (!emailListEl) {
        console.log('ℹ️  applyFilters: emailList element not available yet, skipping display');
        return; // Just filter the data, don't try to display yet
    }
    
    // Always display emails, regardless of count
    if (sortedFiltered.length === 0) {
        // No emails match the filter - show empty state
        console.warn(`⚠️ No emails match filter (tab: ${currentTab})`);
        displayEmails([]);
    } else if (sortedFiltered.length > EMAILS_PER_PAGE) {
        // More than one page - use pagination
        updatePagination();
    } else {
        // One page or less - display directly
        displayEmails(sortedFiltered);
    }
    
    // Update email count
    const emailCountEl = document.getElementById('emailCount');
    if (emailCountEl) {
        const searchText = searchQuery ? ` (${filtered.length} found)` : '';
        emailCountEl.textContent = `${filtered.length} email${filtered.length !== 1 ? 's' : ''}${searchText}`;
    }
}

// Filter emails by category (now uses applyFilters)
function filterEmailsByCategory(category) {
    applyFilters();
}

// Load Deal Flow deals
// Force re-score all deals
async function rescoreAllDeals() {
    if (!confirm('Re-score all deals? This will analyze all deals again and update their scores. This may take a few minutes.')) {
        return;
    }
    
    showAlert('info', 'Re-scoring all deals... This may take a few minutes.');
    
    try {
        const response = await fetch('/api/rescore-all-deals', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            showAlert('success', `Re-scored ${data.count} deal(s). Refreshing...`);
            // Reload deals after a short delay
            setTimeout(() => {
                loadDeals();
            }, 1000);
        } else {
            showAlert('error', data.error || 'Failed to re-score deals');
        }
    } catch (error) {
        console.error('Error re-scoring deals:', error);
        showAlert('error', 'Error: ' + error.message);
    }
}

async function loadDeals() {
    // Don't show cached deals here - switchTab already does that for instant display
    // Just fetch fresh data in background
    
    try {
        console.log('📊 [DEALS] Fetching fresh deals from API...');
        const response = await fetch('/api/deals');
        const data = await response.json();
        
        if (data.success) {
            console.log(`📊 [DEALS] Received ${data.deals.length} deals from API`);
            dealsCache = data.deals;
            saveDealsCacheToStorage();
            
            // Only update UI if we're still on the deal-flow tab
            if (currentTab === 'deal-flow') {
            displayDeals(data.deals);
            }
        } else {
            console.error('❌ [DEALS] Error loading deals:', data.error);
        }
    } catch (error) {
        console.error('❌ [DEALS] Exception loading deals:', error);
    }
}

// Display Deal Flow deals in table
function displayDeals(deals) {
    const tbody = document.getElementById('dealFlowBody');
    
    if (!tbody) {
        console.warn('⚠️ [DEALS] dealFlowBody element not found, cannot display deals');
        return;
    }
    
    if (deals.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state">No deals found</td></tr>';
        return;
    }
    
    tbody.innerHTML = deals.map(deal => {
        const basics = [
            deal.has_deck ? '✓ Deck' : '✗ Deck',
            deal.has_team_info ? '✓ Team' : '✗ Team',
            deal.has_traction ? '✓ Traction' : '✗ Traction',
            deal.has_round_info ? '✓ Round' : '✗ Round'
        ].join(' ');
        
        const stateBadge = getStateBadge(deal.state);
        // Check if deck_link is a PDF attachment reference or a URL
        let deckLink = 'No deck';
        if (deal.deck_link) {
            if (deal.deck_link.startsWith('[PDF Attachment:')) {
                // Extract filename from [PDF Attachment: filename.pdf]
                const filenameMatch = deal.deck_link.match(/\[PDF Attachment:\s*(.+?)\]/);
                const filename = filenameMatch ? filenameMatch[1] : 'deck.pdf';
                // Make PDF attachment clickable to download
                deckLink = `<a href="/api/attachment/${escapeHtml(deal.thread_id)}" target="_blank" class="deck-link" title="${escapeHtml(filename)}">📎 ${escapeHtml(filename)}</a>`;
            } else if (deal.deck_link.startsWith('http')) {
                // URL link - make it clickable
                deckLink = `<a href="${escapeHtml(deal.deck_link)}" target="_blank" class="deck-link">📎 View Deck</a>`;
            } else {
                // Other format - show as text
                deckLink = `<span class="deck-link">📎 ${escapeHtml(deal.deck_link)}</span>`;
            }
        }
        
        // NEW: Tracxn-based portfolio overlaps (from team background matching)
        let overlapText = 'None';
        if (deal.portfolio_overlaps) {
            try {
                const overlaps = typeof deal.portfolio_overlaps === 'string' ? JSON.parse(deal.portfolio_overlaps) : deal.portfolio_overlaps;
                if (Array.isArray(overlaps) && overlaps.length > 0) {
                    overlapText = `🏢 ${overlaps.length} portfolio match${overlaps.length > 1 ? 'es' : ''}`;
                } else if (overlaps && Object.keys(overlaps).length > 0) {
                    // Legacy format
                    const overlapInfo = [];
                    if (overlaps.worked_at_portfolio_companies && overlaps.worked_at_portfolio_companies.length > 0) {
                        overlapInfo.push(`🏢 Portfolio: ${overlaps.worked_at_portfolio_companies.length}`);
                    }
                    if (overlaps.same_school_as_portfolio_founders && overlaps.same_school_as_portfolio_founders.length > 0) {
                        overlapInfo.push(`🎓 School: ${overlaps.same_school_as_portfolio_founders.length}`);
                    }
                    if (overlaps.same_school_as_firm_team && overlaps.same_school_as_firm_team.length > 0) {
                        overlapInfo.push(`👥 Team: ${overlaps.same_school_as_firm_team.length}`);
                    }
                    overlapText = overlapInfo.length > 0 ? overlapInfo.join(', ') : 'None';
                }
            } catch (e) {
                overlapText = 'None';
            }
        }
        
        return `
            <tr>
                <td>
                    <div class="founder-name">${escapeHtml(deal.founder_name || 'Unknown')}</div>
                    <div class="founder-email">${escapeHtml(deal.founder_email)}</div>
                    ${deal.founder_school ? `<div class="founder-school">🎓 ${escapeHtml(deal.founder_school)}</div>` : ''}
                    ${deal.founder_linkedin ? `<div><a href="${escapeHtml(deal.founder_linkedin)}" target="_blank" class="linkedin-link">LinkedIn</a></div>` : ''}
                </td>
                <td>${escapeHtml(decodeHtmlEntities(deal.subject || 'No Subject'))}</td>
                <td>${deckLink}</td>
                <td>${new Date(deal.created_at).toLocaleDateString()}</td>
                <td>
                    <button class="btn btn-small btn-primary" onclick="openDealThread('${deal.thread_id}')">
                        Open Thread
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

// Get state badge HTML
function getStateBadge(state) {
    const badges = {
        'New': '<span class="badge badge-new">New</span>',
        'Ask-More': '<span class="badge badge-ask-more">Ask More</span>',
        'Routed': '<span class="badge badge-routed">Routed</span>'
    };
    return badges[state] || state;
}

// Open deal thread (find email and open modal)
async function openDealThread(threadId) {
    // Find email with this thread_id in cached emails
    let email = allEmails.find(e => e.thread_id === threadId);
    
    if (email) {
        // Email is in cache, pass it directly to openEmail
        openEmail(email);
    } else {
        // Email not in cache - fetch thread directly
        showAlert('info', 'Fetching email details...');
        
        try {
            // Fetch thread using the thread API
            const response = await fetch(`/api/thread/${threadId}`);
            const data = await response.json();
            
            if (data.success && data.emails && data.emails.length > 0) {
                // Use the first email as the base for the modal
                const firstEmail = data.emails[0];
                
                // Create a mock email object with all required fields
                email = {
                    id: firstEmail.id,
                    thread_id: threadId,
                    subject: firstEmail.subject || 'No Subject',
                    from: firstEmail.from || '',
                    body: firstEmail.body || '',
                    combined_text: firstEmail.combined_text || firstEmail.body || '',
                    snippet: firstEmail.snippet || '',
                    date: firstEmail.date,
                    attachments: firstEmail.attachments || [],
                    headers: firstEmail.headers || {},
                    classification: {} // Will be fetched from thread or deal
                };
                
                // Add to allEmails cache so it can be found later
                allEmails.push(email);
                
                // Now open the email modal (pass email object directly)
                openEmail(email);
            } else {
                showAlert('error', 'Could not load email thread');
            }
        } catch (error) {
            console.error('Error fetching thread:', error);
            showAlert('error', 'Error loading email thread: ' + error.message);
        }
    }
}

// Load configuration
// Config bar removed - no longer needed
async function loadConfig() {
    // Config bar removed - function kept for compatibility but does nothing
}

// Fetch emails from Gmail
// Show cache refresh indicator
function showCacheRefreshIndicator() {
    const indicator = document.createElement('div');
    indicator.id = 'cacheRefreshIndicator';
    indicator.style.cssText = `
        position: fixed;
        top: 70px;
        right: 20px;
        background: var(--bg-primary);
        border: 1px solid var(--border-color);
        border-radius: 8px;
        padding: 8px 16px;
        box-shadow: var(--shadow-md);
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 13px;
        color: var(--text-secondary);
        z-index: 9999;
    `;
    indicator.innerHTML = '<div class="spinner-small" style="width: 14px; height: 14px;"></div>Refreshing...';
    document.body.appendChild(indicator);
}

// Hide cache refresh indicator
function hideCacheRefreshIndicator() {
    const indicator = document.getElementById('cacheRefreshIndicator');
    if (indicator) {
        indicator.remove();
    }
}

// Refresh emails manually (cache-first for instant feedback)
async function refreshEmails() {
    console.log('🔄 Manual refresh triggered');
    
    // Don't refresh inbox if on sent/drafts/starred tabs - refresh the current tab instead
    if (currentTab === 'sent') {
        console.log('📤 Refreshing sent emails instead of inbox');
        fetchSentEmails();
        return;
    } else if (currentTab === 'drafts') {
        console.log('📝 Refreshing drafts instead of inbox');
        fetchDrafts();
        return;
    } else if (currentTab === 'starred') {
        console.log('⭐ Refreshing starred emails instead of inbox');
        fetchStarredEmails();
        return;
    }
    
    // Add spinning animation to refresh button
    const refreshBtn = document.getElementById('refreshEmailsBtn');
    if (refreshBtn) {
        refreshBtn.classList.add('refreshing');
        refreshBtn.disabled = true;
    }
    
    try {
        // Show cached emails immediately for instant feedback
        if (emailCache.data && emailCache.data.length > 0) {
            console.log(`⚡ Displaying ${emailCache.data.length} cached emails immediately`);
            allEmails = [...emailCache.data];
            applyFilters();
            updatePagination();
        }
        
        // Fetch fresh data in background
        console.log('🔄 Fetching fresh emails from server...');
        const response = await fetch(`/api/emails?max=200&show_spam=true`);
        const data = await response.json();
        
        if (data.success && data.emails) {
            const oldCount = emailCache.data.length;
            const newCount = data.emails.length;
            
            // Update cache
            emailCache.data = data.emails;
            emailCache.timestamp = Date.now();
            saveEmailCacheToStorage();
            
            // Update display
            allEmails = data.emails;
            applyFilters();
            updatePagination();
            
            // Show diff
            const diff = newCount - oldCount;
            if (diff > 0) {
                showAlert('success', `📧 ${diff} new email${diff !== 1 ? 's' : ''} loaded`);
            } else if (diff < 0) {
                showAlert('info', `${Math.abs(diff)} email${Math.abs(diff) !== 1 ? 's' : ''} removed`);
            } else {
                showAlert('info', 'Inbox up to date');
            }
            
            console.log(`✅ Refreshed: ${newCount} emails (${diff > 0 ? '+' : ''}${diff})`);
        }
    } catch (error) {
        console.error('Error refreshing emails:', error);
        showAlert('error', 'Failed to refresh emails');
    } finally {
        // Remove spinning animation
        if (refreshBtn) {
            refreshBtn.classList.remove('refreshing');
            refreshBtn.disabled = false;
        }
    }
}

async function fetchEmails() {
    // Prevent multiple simultaneous fetches
    if (isFetching) {
        console.log('Already fetching emails, please wait...');
        return;
    }
    
    isFetching = true;
    const loading = document.getElementById('loading');
    const emailList = document.getElementById('emailList');
    const fetchBtn = document.getElementById('refreshEmailsBtn');
    
    // Show loading state
    loading.style.display = 'block';
    loading.innerHTML = '<div class="loading-spinner"></div><p>Starting email sync...</p><p class="loading-progress">Initializing...</p>';
    emailList.innerHTML = '';
    fetchBtn.disabled = true;
    
    try {
        const forceFullSync = false; // Removed force full sync option
        const maxEmails = 200; // Fixed to 200 emails
        
        // PHASE 1: Try background task first (if available)
        try {
            const syncResponse = await fetch('/api/emails/sync', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    max: maxEmails,
                    force_full_sync: forceFullSync
                })
            });
            
            const syncData = await syncResponse.json();
            
            if (syncData.success && syncData.task_id) {
                // Background task started - poll for status
                console.log('✅ Background task started:', syncData.task_id);
                try {
                    await pollTaskStatus(syncData.task_id, loading, emailList, fetchBtn);
                    return; // Success - exit function
                } catch (pollError) {
                    console.warn('⚠️  Background task polling failed, falling back to streaming:', pollError.message);
                    // Don't show error alert - just fall through to streaming endpoint
                    // This happens when worker isn't running, which is expected in some deployments
                }
            } else if (syncResponse.status === 503) {
                // Celery not available - fall back to streaming
                console.log('⚠️  Background tasks not available, using streaming endpoint');
            } else {
                throw new Error(syncData.error || 'Failed to start sync');
            }
        } catch (error) {
            console.log('⚠️  Background task failed, falling back to streaming:', error);
            // Fall through to streaming endpoint
        }
        
        // FALLBACK: Use streaming endpoint (original implementation)
        let url = `/api/emails/stream?max=200&`;
        if (forceFullSync) url += 'force_full_sync=true&';
        
        const response = await fetch(url);
        
        // Check if streaming is supported
        if (!response.body) {
            console.warn('Streaming not supported, falling back to regular fetch');
            // Fallback to regular endpoint
            url = `/api/emails?max=200&`;
            if (categoryParam) url += `category=${categoryParam}&`;
            if (forceFullSync) url += 'force_full_sync=true&';
            url += 'show_spam=true';
            
            const fallbackResponse = await fetch(url);
            const data = await fallbackResponse.json();
            
            // Process fallback response normally
            if (data.success) {
                const newEmails = data.emails || [];
                
                // If force_full_sync is enabled, replace cache instead of merging
                if (forceFullSync) {
                    console.log(`🔄 Force full sync: Replacing cache with ${newEmails.length} emails`);
                    emailCache.data = newEmails;
                    emailCache.timestamp = Date.now();
                    saveEmailCacheToStorage(); // Save to localStorage
                    allEmails = newEmails;
                } else {
                    // INCREMENTAL SYNC: Merge new emails with existing cache
                    if (newEmails.length > 0) {
                        // Add new emails, avoiding duplicates by thread_id
                        const existingThreadIds = new Set(emailCache.data.map(e => e.thread_id));
                        const uniqueNewEmails = newEmails.filter(e => !existingThreadIds.has(e.thread_id));
                        
                        if (uniqueNewEmails.length > 0) {
                            emailCache.data = [...emailCache.data, ...uniqueNewEmails];
                            emailCache.timestamp = Date.now();
                            saveEmailCacheToStorage(); // Save to localStorage
                            console.log(`✅ Added ${uniqueNewEmails.length} new emails to cache (${newEmails.length} fetched, ${newEmails.length - uniqueNewEmails.length} duplicates skipped)`);
                        } else {
                            console.log(`ℹ️  No new unique emails (${newEmails.length} fetched were already in cache)`);
                        }
                    } else if (emailCache.data.length === 0) {
                        // Empty result and empty cache - truly no emails
                        console.log('ℹ️  No emails found (incremental sync returned empty, cache is empty)');
                    } else {
                        // Empty result but cache exists - no new emails since last sync
                        console.log(`ℹ️  No new emails (incremental sync returned empty, keeping ${emailCache.data.length} cached emails)`);
                    }
                    
                    // Update cache timestamp
                    emailCache.timestamp = Date.now();
                    saveEmailCacheToStorage(); // Save to localStorage
                    allEmails = emailCache.data; // Use merged cache
                }
                
                applyFilters(); // Apply filters including search
                const emailCountEl = document.getElementById('emailCount');
                if (emailCountEl) {
                    const searchText = searchQuery ? ` (${filteredEmails.length} found)` : '';
                    if (newEmails.length > 0) {
                        emailCountEl.textContent = `${allEmails.length} total (${newEmails.length} new)${searchText}`;
                    } else if (allEmails.length > 0) {
                        // Loaded from database/cache - unread filter doesn't apply
                        emailCountEl.textContent = `${allEmails.length} email${allEmails.length !== 1 ? 's' : ''} (no new emails)${searchText}`;
                    } else {
                        emailCountEl.textContent = `0 emails${searchText}`;
                    }
                }
                
                // Reload deals if on Deal Flow tab
                if (currentTab === 'deal-flow') {
                    loadDeals();
                }
            } else {
                // Check for rate limit error
                if (fallbackResponse.status === 429 || data.rate_limit) {
                    const retryAfter = data.retry_after || 'a few minutes';
                    showAlert('warning', `⚠️ Gmail API rate limit exceeded. Please wait until ${retryAfter} before trying again.`);
                    emailList.innerHTML = `<div class="empty-state"><p>⚠️ Rate Limit Exceeded<br><small style="color: var(--text-secondary);">Please wait until ${retryAfter} before fetching emails again</small></p></div>`;
                } else {
                    showAlert('error', data.error || 'Failed to fetch emails');
                    emailList.innerHTML = '<div class="empty-state"><p>Failed to fetch emails. Check console for details.</p></div>';
                }
            }
            return; // Exit after fallback processing
        }
        
        // STREAMING: Process Server-Sent Events for progressive loading
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        const streamedEmails = [];
        
        while (true) {
            const {done, value} = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, {stream: true});
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Keep incomplete line in buffer
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = JSON.parse(line.slice(6));
                    
                    if (data.status === 'fetching') {
                        loading.innerHTML = `<div class="loading-spinner"></div><p>Fetching up to ${data.total} emails from Gmail...</p>`;
                    } else if (data.status === 'classifying') {
                        loading.innerHTML = `<div class="loading-spinner"></div><p>Classifying ${data.total} emails...</p><p class="loading-progress">0 / ${data.total} emails processed</p>`;
                    } else if (data.email) {
                        // New email received - add to list immediately
                        streamedEmails.push(data.email);
                        
                        // Update progress
                        const progressEl = document.querySelector('.loading-progress');
                        if (progressEl) {
                            progressEl.textContent = `${data.progress} / ${data.total} emails processed`;
                        }
                        
                        // Add to cache and display
                        const existingIndex = emailCache.data.findIndex(e => e.thread_id === data.email.thread_id);
                        if (existingIndex >= 0) {
                            emailCache.data[existingIndex] = data.email;
                        } else {
                            emailCache.data.push(data.email);
                        }
                        
                        // Update display in real-time
                        allEmails = [...emailCache.data];
                        applyFilters();
                        
                    } else if (data.status === 'complete') {
                        console.log(`✅ Streaming complete: ${streamedEmails.length} emails processed`);
                        emailCache.timestamp = Date.now();
                        saveEmailCacheToStorage();
                        
                        // Final update
                        allEmails = [...emailCache.data];
                        applyFilters();
                        
                        const emailCountEl = document.getElementById('emailCount');
                        if (emailCountEl) {
                            emailCountEl.textContent = `${allEmails.length} email${allEmails.length !== 1 ? 's' : ''} (${streamedEmails.length} new)`;
                        }
                        
                        // Reload deals if on Deal Flow tab
                        if (currentTab === 'deal-flow') {
                            loadDeals();
                        }
                        
                    } else if (data.error) {
                        showAlert('error', data.error);
                        emailList.innerHTML = `<div class="empty-state"><p>Error: ${data.error}</p></div>`;
                    }
                }
            }
        }
        
    } catch (error) {
        console.error('Error fetching emails:', error);
        showAlert('error', 'Error fetching emails: ' + error.message);
        emailList.innerHTML = '<div class="empty-state"><p>Error fetching emails. Make sure the server is running.</p></div>';
    } finally {
        loading.style.display = 'none';
        fetchBtn.disabled = false;
        isFetching = false; // Reset fetching flag
        
        // Remove spinning animation from refresh button
        const refreshBtn = document.getElementById('refreshEmailsBtn');
        if (refreshBtn) {
            refreshBtn.classList.remove('refreshing');
            refreshBtn.disabled = false;
        }
    }
}

// PHASE 1: Poll background task status
async function pollTaskStatus(taskId, loading, emailList, fetchBtn) {
    const maxAttempts = 300; // 5 minutes max (300 * 1 second)
    const pendingTimeout = 30; // If PENDING for 30 seconds, assume worker isn't running
    let attempts = 0;
    let pendingStartTime = null;
    let pollInterval;
    
    return new Promise((resolve, reject) => {
        pollInterval = setInterval(async () => {
            attempts++;
            
            try {
                const statusResponse = await fetch(`/api/emails/sync/status/${taskId}`);
                const statusData = await statusResponse.json();
                
                if (!statusData.success) {
                    clearInterval(pollInterval);
                    reject(new Error(statusData.error || 'Task failed'));
                    return;
                }
                
                const status = statusData.status;
                
                if (status === 'PENDING') {
                    // Track how long task has been PENDING
                    if (pendingStartTime === null) {
                        pendingStartTime = Date.now();
                    }
                    
                    const pendingDuration = (Date.now() - pendingStartTime) / 1000;
                    
                    // If stuck in PENDING for too long, assume worker isn't running
                    if (pendingDuration > pendingTimeout) {
                        clearInterval(pollInterval);
                        console.warn(`⚠️  Task stuck in PENDING for ${pendingDuration}s - worker may not be running, falling back to streaming`);
                        reject(new Error('Worker not responding - falling back to direct sync'));
                        return;
                    }
                    
                    loading.innerHTML = `<div class="loading-spinner"></div><p>Waiting for worker...</p><p class="loading-progress">Queued (${Math.floor(pendingDuration)}s)</p>`;
                } else if (status === 'PROGRESS') {
                    // Reset pending timer once we see progress
                    pendingStartTime = null;
                    const progress = statusData.progress || 0;
                    const total = statusData.total || 0;
                    const currentEmail = statusData.current_email || '';
                    const message = statusData.message || 'Processing...';
                    
                    loading.innerHTML = `
                        <div class="loading-spinner"></div>
                        <p>${message}</p>
                        <p class="loading-progress">${progress} / ${total} emails processed</p>
                        ${currentEmail ? `<p style="font-size: 0.9em; color: var(--text-secondary); margin-top: 8px;">${escapeHtml(currentEmail)}</p>` : ''}
                    `;
                } else if (status === 'SUCCESS') {
                    clearInterval(pollInterval);
                    
                    // Show completion message
                    const emailsProcessed = statusData.emails_processed || 0;
                    const emailsClassified = statusData.emails_classified || 0;
                    
                    loading.innerHTML = `
                        <div class="loading-spinner"></div>
                        <p>✅ Sync completed!</p>
                        <p class="loading-progress">${emailsClassified} emails classified</p>
                    `;
                    
                    // Wait a moment, then load emails from database
                    setTimeout(async () => {
                        await loadEmailsFromDatabase();
                        loading.style.display = 'none';
                        if (fetchBtn) fetchBtn.disabled = false;
                        isFetching = false;
                        resolve();
                    }, 1000);
                    
                } else if (status === 'FAILURE' || status === 'ERROR') {
                    clearInterval(pollInterval);
                    reject(new Error(statusData.error || 'Task failed'));
                }
                
                // Check timeout
                if (attempts >= maxAttempts) {
                    clearInterval(pollInterval);
                    reject(new Error('Task timeout - taking too long'));
                }
                
            } catch (error) {
                clearInterval(pollInterval);
                reject(error);
            }
        }, 1000); // Poll every 1 second
    });
}

// Load emails from database after background sync completes
async function loadEmailsFromDatabase() {
    try {
        // ALWAYS load ALL emails from database (no category filter)
        // Let applyFilters() handle category filtering on the frontend
        // This ensures allEmails contains all emails, and filtering happens client-side
        // NOTE: Removed db_only=true to allow Gmail API to check for new emails
        // This will trigger incremental sync, and if no new emails found, will trigger background sync as fallback
        let url = `/api/emails?max=200&show_spam=true`;
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.success) {
            const emails = data.emails || [];
            emailCache.data = emails;
            emailCache.timestamp = Date.now();
            saveEmailCacheToStorage();
            // CRITICAL: Set allEmails so applyFilters() can use it
            // allEmails should contain ALL emails, not filtered by category
            allEmails = emails;
            console.log(`✅ Loaded ${emails.length} emails from database`);
            console.log(`📊 Current tab: ${currentTab}, allEmails length: ${allEmails.length}`);
            
            // Ensure we have emails before filtering
            if (allEmails.length === 0) {
                console.warn('⚠️ No emails loaded, displaying empty state');
                // Only display if emailList element exists
                const emailListCheck = document.getElementById('emailList');
                if (emailListCheck) {
                    displayEmails([]);
                }
                return;
            }
            
            // Check if emailList element exists before trying to display
            const emailListCheck = document.getElementById('emailList');
            if (!emailListCheck) {
                console.log('ℹ️  emailList element not available yet, skipping display (will be displayed after setup screen is hidden)');
                // Still set allEmails so it's available when emailList appears
                return; // Just load the data, don't try to display yet
            }
            
            // Ensure all emails have category before filtering
            allEmails.forEach(email => {
                if (!email.category && email.classification?.category) {
                    email.category = email.classification.category.toLowerCase();
                } else if (!email.category) {
                    email.category = 'general';
                }
            });
            
            // applyFilters() will handle category filtering based on currentTab
            applyFilters();
            
            // Force display if filteredEmails is empty but allEmails has data
            if (filteredEmails.length === 0 && allEmails.length > 0) {
                console.warn('⚠️ filteredEmails is empty but allEmails has data, forcing filter application');
                // Reset currentTab to 'all' to show all emails
                const originalTab = currentTab;
                currentTab = 'all';
                applyFilters();
                if (filteredEmails.length === 0) {
                    // Still empty - use allEmails directly
                    console.warn('⚠️ filteredEmails still empty after reset, using allEmails directly');
                    filteredEmails = allEmails;
                } else {
                    currentTab = originalTab; // Restore original tab
                }
            }
            
            // Double-check that emails were displayed
            if (emailListCheck && emailListCheck.children.length === 0 && filteredEmails.length > 0) {
                console.warn('⚠️ Emails loaded but not displayed, forcing display');
                displayEmails(filteredEmails.slice(0, EMAILS_PER_PAGE));
                updatePagination();
            } else if (emailListCheck && emailListCheck.children.length === 0 && allEmails.length > 0) {
                console.warn('⚠️ No emails displayed but allEmails has data, forcing display of allEmails');
                displayEmails(allEmails.slice(0, EMAILS_PER_PAGE));
                updatePagination();
            }
        } else {
            throw new Error(data.error || 'Failed to load emails');
        }
    } catch (error) {
        console.error('Error loading emails from database:', error);
        showAlert('error', `Failed to load emails: ${error.message}`);
    }
}

// Display emails in the list
function displayEmails(emails) {
    const emailList = document.getElementById('emailList');
    
    // Stop observing old emails for pre-fetching
    stopObservingEmails();
    
    // Safety check: ensure email list element exists
    if (!emailList) {
        console.warn('⚠️ displayEmails: emailList element not found, skipping display');
        return;
    }
    
    if (emails.length === 0) {
        // Check if we're on sent tab and might be loading
        if (currentTab === 'sent') {
            // Check if we actually have sent emails in cache or allEmails
            const hasSentEmails = (sentEmailsCache && sentEmailsCache.length > 0) || 
                                  (allEmails && allEmails.some(e => e.is_sent || e.category === 'SENT'));
            
            // Check if loading indicator is showing
            const emailList = document.getElementById('emailList');
            const isShowingLoading = emailList && emailList.innerHTML.includes('Loading your sent emails');
            
            // Don't show "no emails" if we're loading or have emails elsewhere
            if (isShowingLoading || hasSentEmails) {
                return; // Keep showing loading indicator or wait for emails to load
            }
        }
        
        // Check if we're on drafts tab and might be loading
        if (currentTab === 'drafts') {
            // Check if we actually have drafts in cache or allEmails
            const hasDrafts = (draftsCache && draftsCache.length > 0) || 
                             (allEmails && allEmails.some(e => e.is_draft || e.category === 'DRAFT'));
            
            // Check if loading indicator is showing
            const emailList = document.getElementById('emailList');
            const isShowingLoading = emailList && emailList.innerHTML.includes('Loading your drafts');
            
            // Don't show "no emails" if we're loading or have drafts elsewhere
            if (isShowingLoading || hasDrafts) {
                return; // Keep showing loading indicator or wait for drafts to load
            }
        }
        
        // Check if we're on starred tab and might be loading
        if (currentTab === 'starred') {
            // Check if we actually have starred emails in cache or allEmails
            const hasStarredEmails = (starredEmailsCache && starredEmailsCache.length > 0) || 
                                     (allEmails && allEmails.some(e => e.is_starred || e.starred || e.category === 'STARRED'));
            
            // Check if loading indicator is showing
            const emailList = document.getElementById('emailList');
            const isShowingLoading = emailList && emailList.innerHTML.includes('Loading your starred emails');
            
            // Don't show "no emails" if we're loading or have starred emails elsewhere
            if (isShowingLoading || hasStarredEmails) {
                return; // Keep showing loading indicator or wait for starred emails to load
            }
        }
        
        const currentTabName = document.querySelector('.tab-btn.active, .tab-btn-compact.active')?.textContent?.trim() || 'All Emails';
        let message = '📭 No emails found';
        
        if (currentTab !== 'all') {
            message += `<br><small style="color: var(--text-secondary);">No ${currentTabName.toLowerCase()} emails. Try switching to "All Emails" tab</small>`;
        } else {
            // Check if Gmail is connected
            const gmailStatus = document.getElementById('gmailStatus');
            const isConnected = gmailStatus && gmailStatus.textContent.includes('Connected');
            
            if (!isConnected) {
                message += '<br><small style="color: var(--text-secondary);">⚠️ Gmail not connected. <a href="/connect-gmail" style="color: var(--primary-color);">Connect Gmail</a> first</small>';
            } else {
                message += '<br><small style="color: var(--text-secondary);">Emails are loading in the background...</small>';
            }
        }
        
        emailList.innerHTML = `<div class="empty-state"><p>${message}</p></div>`;
        return;
    }
    
    // Emails are already sorted when passed to displayEmails
    // Calculate the start index for the current page to get correct global index
    const startIndex = (currentPage - 1) * EMAILS_PER_PAGE;
    emailList.innerHTML = emails.map((email, localIndex) => {
        // Calculate global index in filteredEmails array
        const globalIndex = startIndex + localIndex;
        const classification = email.classification || {};
        const category = classification.category || 'UNKNOWN';
        const tags = classification.tags || [];
        const categoryBadge = getCategoryBadge(category);
        // Only show tags if they provide additional info beyond the category (e.g., "DF/AskMore")
        // Filter out redundant tags that just repeat the category
        const redundantTags = ['DF/Deal', 'HR/Hiring', 'NW/Networking', 'SPAM/Skip', 'GEN/General'];
        const usefulTags = tags.filter(tag => !redundantTags.includes(tag));
        const tagsHtml = usefulTags.length > 0 ? usefulTags.map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join('') : '';
        
        // Parse sender/recipient name and email
        // For sent emails, show "To:" instead of "From:"
        const isSent = email.is_sent || email.classification?.category === 'SENT';
        const field = isSent ? (email.to || email.from || '') : (email.from || '');
        let displayName = '';
        if (field.includes('<') && field.includes('>')) {
            const match = field.match(/^(.+?)\s*<(.+?)>$/);
            if (match) {
                displayName = match[1].trim();
            } else {
                displayName = field.split('<')[0].trim();
            }
        } else {
            displayName = field.split('@')[0];
        }
        if (!displayName) displayName = field || 'Unknown';
        
        // Format date with actual time and relative time in brackets
        let dateText = '';
        if (email.date) {
            const timestamp = typeof email.date === 'string' ? parseInt(email.date) : email.date;
            const date = new Date(timestamp);
            const now = new Date();
            const diffMs = now - date;
            const diffMins = Math.floor(diffMs / 60000);
            const diffHours = Math.floor(diffMs / 3600000);
            const diffDays = Math.floor(diffMs / 86400000);
            const diffWeeks = Math.floor(diffDays / 7);
            const diffMonths = Math.floor(diffDays / 30);
            const diffYears = Math.floor(diffDays / 365);
            
            // Actual time format
            let timeFormat = '';
            const isToday = date.toDateString() === now.toDateString();
            const isYesterday = date.toDateString() === new Date(now.getTime() - 86400000).toDateString();
            const isThisYear = date.getFullYear() === now.getFullYear();
            
            if (isToday) {
                // Show time for today's emails (e.g., "3:45 PM")
                timeFormat = date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
            } else if (isYesterday) {
                // Show "Yesterday" + time
                timeFormat = `Yesterday ${date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })}`;
            } else if (isThisYear) {
                // Show month/day for this year (e.g., "Nov 15")
                timeFormat = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
            } else {
                // Show full date for older emails (e.g., "Nov 15, 2023")
                timeFormat = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
            }
            
            // Relative time in brackets
            let relativeTime = '';
            if (diffMins < 1) {
                relativeTime = 'just now';
            } else if (diffMins < 60) {
                relativeTime = `${diffMins} minute${diffMins !== 1 ? 's' : ''} ago`;
            } else if (diffHours < 24) {
                relativeTime = `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`;
            } else if (diffDays < 7) {
                relativeTime = `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`;
            } else if (diffDays < 30) {
                relativeTime = `${diffWeeks} week${diffWeeks !== 1 ? 's' : ''} ago`;
            } else if (diffDays < 365) {
                relativeTime = `${diffMonths} month${diffMonths !== 1 ? 's' : ''} ago`;
            } else {
                relativeTime = `${diffYears} year${diffYears !== 1 ? 's' : ''} ago`;
            }
            
            dateText = `${timeFormat} (${relativeTime})`;
        }
        
        // Decode HTML entities for subject and snippet
        const decodedSubject = decodeHtmlEntities(email.subject || 'No Subject');
        const decodedSnippet = decodeHtmlEntities(email.snippet || '');
        
        const senderLabel = isSent ? 'To:' : 'From:';
        const isStarred = email.is_starred || email.label_ids?.includes('STARRED') || false;
        const starClass = isStarred ? 'starred' : '';
        const hasAttachments = email.has_attachments || false;
        // Check if email is unread: explicitly false OR has UNREAD label
        const isUnread = (email.is_read === false) || (email.label_ids && email.label_ids.includes('UNREAD'));
        const unreadClass = isUnread ? 'unread' : '';
        const attachmentClass = hasAttachments ? 'has-attachment' : '';
        
        // Check if this is a draft email
        const isDraft = email.is_draft || email.classification?.category === 'DRAFT';
        const onclickHandler = isDraft ? `openDraft(${globalIndex})` : `openEmail(${globalIndex})`;
        
        return `
            <div class="email-card ${unreadClass} ${attachmentClass}" 
                 onclick="${onclickHandler}" 
                 oncontextmenu="event.preventDefault(); showContextMenu(event, ${globalIndex});"
                 data-email-index="${globalIndex}"
                 data-thread-id="${escapeHtml(email.thread_id || '')}">
                <div class="email-row">
                    <div class="email-star" onclick="event.stopPropagation(); toggleStar('${email.id}', ${isStarred}, ${globalIndex})" title="${isStarred ? 'Unstar' : 'Star'}">
                        <span class="star-icon ${starClass}">★</span>
                    </div>
                    <div class="email-sender-name">
                        ${isUnread ? '<span class="unread-dot"></span>' : '<span class="unread-dot-placeholder"></span>'}
                        <span>${escapeHtml(decodeHtmlEntities(displayName))}</span>
                    </div>
                    <div class="email-content">
                        <div class="email-subject">
                            <span>${escapeHtml(decodedSubject)}</span>
                            ${categoryBadge}
                        </div>
                        <div class="email-snippet">${escapeHtml(decodedSnippet)}</div>
                    </div>
                    ${hasAttachments ? '<div class="email-attachment" title="Has attachments">📎</div>' : ''}
                    <div class="email-hover-actions">
                        <button class="email-action-btn" onclick="event.stopPropagation(); archiveEmail('${email.id}', ${globalIndex})" title="Archive">📦</button>
                        <button class="email-action-btn" onclick="event.stopPropagation(); deleteEmail('${email.id}', ${globalIndex})" title="Delete">🗑️</button>
                    </div>
                    ${dateText ? `<div class="email-date">${dateText}</div>` : ''}
                </div>
            </div>
        `;
    }).join('');
    
    // Pre-fetch threads for visible emails immediately (0ms instant access)
    prefetchVisibleThreads();
    
    // Start observing new emails for pre-fetching
    setTimeout(() => observeEmailsForPrefetch(), 100);
    
    // Update unread counts in sidebar
    updateSidebarUnreadCounts();
}

// Update unread count badges in sidebar (Superhuman style)
function updateSidebarUnreadCounts() {
    if (!emailCache || !emailCache.data) return;
    
    // Count unread emails by category
    const counts = {
        'all': 0,
        'deal-flow': 0,
        'networking': 0,
        'hiring': 0,
        'general': 0,
        'spam': 0
    };
    
    emailCache.data.forEach(email => {
        // Check if email is unread: explicitly false OR has UNREAD label
        const isUnread = (email.is_read === false) || (email.label_ids && email.label_ids.includes('UNREAD'));
        
        if (isUnread) {
            counts['all']++;
            
            // Count by category
            const category = email.classification?.category || email.category;
            if (category === 'DEAL_FLOW') {
                counts['deal-flow']++;
            } else if (category === 'NETWORKING') {
                counts['networking']++;
            } else if (category === 'HIRING') {
                counts['hiring']++;
            } else if (category === 'GENERAL') {
                counts['general']++;
            } else if (category === 'SPAM') {
                counts['spam']++;
            }
        }
    });
    
    // Update each badge
    Object.keys(counts).forEach(tab => {
        const badge = document.getElementById(`unread-count-${tab}`);
        if (badge) {
            if (counts[tab] > 0) {
                badge.textContent = counts[tab];
                badge.style.display = 'inline-block';
            } else {
                badge.style.display = 'none';
            }
        }
    });
}

// Get category badge HTML
function getCategoryBadge(category) {
    const badges = {
        'DEAL_FLOW': '<span class="badge badge-deal-flow">Deal Flow</span>',
        'NETWORKING': '<span class="badge badge-networking">Networking</span>',
        'HIRING': '<span class="badge badge-hiring">Hiring</span>',
        'GENERAL': '<span class="badge badge-general">General</span>',
        'SPAM': '<span class="badge badge-spam">Spam</span>',
        'SENT': '<span class="badge badge-sent">Sent</span>',
        'STARRED': '<span class="badge badge-starred">Starred</span>'
    };
    return badges[category] || '';
}

// Clean invisible Unicode characters
function cleanInvisibleChars(text) {
    if (!text) return text;
    // Remove zero-width spaces, zero-width non-joiners, and other invisible characters
    return text.replace(/[\u200B-\u200D\uFEFF\u200E\u200F\u202A-\u202E\u2060-\u206F]/g, '');
}

// Strip CSS from HTML while preserving structure
function stripCSSFromHTML(html) {
    if (!html) return html;
    
    // Remove @font-face declarations
    html = html.replace(/@font-face\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}/gi, '');
    
    // Remove @media queries
    html = html.replace(/@media[^{]*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}/gi, '');
    
    // Remove style tags and their content
    html = html.replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '');
    
    // Remove CSS rules that appear as standalone blocks (selector { property: value; })
    html = html.replace(/^[a-zA-Z0-9\s,.#:*-]+\s*\{[^}]*\}\s*$/gm, '');
    
    // Remove CSS property lines (property: value;)
    html = html.replace(/^\s*[a-zA-Z-]+\s*:\s*[^;]+;\s*$/gm, '');
    
    // Remove closing braces on their own line
    html = html.replace(/^\s*\}\s*$/gm, '');
    
    // Remove mso-* attributes (Microsoft Outlook specific)
    html = html.replace(/\s*mso-[^=]*=["'][^"']*["']/gi, '');
    
    // Remove CSS that's attached to text (e.g., "text{property:value;}")
    html = html.replace(/([a-zA-Z])([a-zA-Z0-9\s,.#:*-]+\s*\{[^}]*\})/g, '$1');
    
    // Remove remaining CSS patterns
    html = html.replace(/\{[^}]*\}/g, '');
    
    // Clean up multiple consecutive newlines/whitespace
    html = html.replace(/\n\s*\n\s*\n+/g, '\n\n');
    
    return html.trim();
}

// Format email body with HTML support
function formatEmailBody(body) {
    if (!body) return '<p style="color: var(--text-secondary); font-style: italic;">No content</p>';
    
    // Clean invisible Unicode characters first
    let decodedBody = cleanInvisibleChars(body);
    
    // Decode HTML entities
    decodedBody = decodeHtmlEntities(decodedBody);
    
    // Check if body contains CSS (even if no HTML tags)
    const hasCSS = decodedBody.includes('@font-face') || 
                   decodedBody.includes('font-family') || 
                   decodedBody.includes('{') ||
                   decodedBody.includes('woff2');
    
    // If there's CSS, extract plain text first to find content
    if (hasCSS) {
        // Create a temporary div to extract text content
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = decodedBody;
        let textContent = tempDiv.textContent || tempDiv.innerText || '';
        textContent = cleanInvisibleChars(textContent);
        
        // Find where actual content starts - look for common email content patterns
        const contentPatterns = [
            /Here is your[\s\S]{0,500}summary for:/i,
            /Here is your summary for:/i,
            /Meeting Summary:/i,
            /Summary/i,
            /Overview/i,
            /Details:/i,
            /Attendees:/i,
            /Confirmed Outcomes/i,
            /Next Steps/i,
            /Supporting Notes/i,
            /Open Questions/i
        ];
        
        let contentStartIndex = -1;
        for (const pattern of contentPatterns) {
            const match = textContent.match(pattern);
            if (match && match.index !== undefined) {
                // Check if there's CSS-like content before this
                const beforeMatch = textContent.substring(0, match.index);
                const hasCSSBefore = beforeMatch.includes('{') || 
                                   beforeMatch.includes('@font-face') || 
                                   beforeMatch.includes('font-family') ||
                                   beforeMatch.includes('woff2') ||
                                   beforeMatch.length > 100; // Long text before content is likely CSS
                
                if (hasCSSBefore) {
                    if (contentStartIndex === -1 || match.index < contentStartIndex) {
                        contentStartIndex = match.index;
                    }
                }
            }
        }
        
        // If we found content start, use text from there
        if (contentStartIndex > 0) {
            textContent = textContent.substring(contentStartIndex);
            // Clean up any remaining CSS artifacts in the text
            textContent = textContent.replace(/\{[^}]*\}/g, '');
            textContent = textContent.replace(/@font-face[^}]*\}/gi, '');
            textContent = textContent.replace(/font-family[^;]*;/gi, '');
            textContent = textContent.replace(/woff2[^'"]*/gi, '');
            textContent = textContent.replace(/strong,\s*b\s*\{[^}]*\}/gi, '');
            
            // Remove lines that are pure CSS
            const lines = textContent.split('\n');
            const cleanedLines = lines.filter(line => {
                const trimmed = line.trim();
                if (!trimmed) return true;
                if (trimmed.includes('@font-face') || 
                    (trimmed.includes('font-family') && trimmed.includes('Inter')) ||
                    trimmed.includes('woff2') ||
                    trimmed.match(/^[a-zA-Z0-9\s,.#:*-]+\s*\{[^}]*\}/) ||
                    trimmed === '* {' ||
                    trimmed === '}') {
                    return false;
                }
                return true;
            });
            textContent = cleanedLines.join('\n').trim();
            
            return formatPlainText(textContent);
        }
    }
    
    // If no CSS or content start not found, try to clean HTML
    const hasHtmlTags = /<[a-z][\s\S]*>/i.test(decodedBody);
    
    if (hasHtmlTags) {
        // Strip CSS from HTML
        decodedBody = stripCSSFromHTML(decodedBody);
        
        // Remove CSS that's attached to text
        decodedBody = decodedBody.replace(/([a-zA-Z])([a-zA-Z0-9\s,.#:*-]+\s*\{[^}]*\})/g, '$1');
        decodedBody = decodedBody.replace(/^[a-zA-Z0-9\s,.#:*-]+\s*\{[^}]*\}\s*$/gm, '');
        decodedBody = decodedBody.replace(/\{[^}]*\}/g, '');
        
        // Sanitize HTML and render
        decodedBody = decodedBody.replace(/<script[\s\S]*?<\/script>/gi, '');
        decodedBody = decodedBody.replace(/on\w+\s*=\s*["'][^"']*["']/gi, '');
        decodedBody = decodedBody.replace(/javascript:/gi, '');
        
        if (decodedBody.trim().match(/<[a-z][\s\S]*>/i)) {
            return `<div style="max-width: 100%; overflow-x: auto; line-height: 1.6; color: var(--text-primary); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">${decodedBody}</div>`;
        }
    }
    
    // Fallback to plain text
    return formatPlainText(decodedBody);
}

// Format plain text email body with smart formatting
function formatPlainText(text) {
    if (!text) return '<p style="color: var(--text-secondary); font-style: italic;">No content</p>';
    
    text = text.trim();
    
    // Fix concatenated words (add spaces where missing)
    // e.g., "CollaborationHere's" -> "Collaboration Here's"
    text = text.replace(/([a-z])([A-Z])/g, '$1 $2');
    // e.g., "meeting.Summary" -> "meeting. Summary"
    text = text.replace(/([.!?])([A-Z])/g, '$1 $2');
    // e.g., "Details:Attendees" -> "Details: Attendees"
    text = text.replace(/(:)([A-Z])/g, '$1 $2');
    
    // Only major section headers (not everything)
    const majorSectionHeaders = [
        'Confirmed Outcomes',
        'Next Steps',
        'Supporting Notes',
        'Open Questions'
    ];
    
    // Add line breaks before major section headers only
    majorSectionHeaders.forEach(header => {
        const escapedHeader = header.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        // Match header that appears after text or punctuation, followed by newline or end
        const regex = new RegExp(`([.!?\\n]|^)\\s*(${escapedHeader})(\\s|$|:)`, 'gi');
        text = text.replace(regex, '$1\n\n$2$3');
    });
    
    // Add line breaks before "Here is your" or "Here's your" only if at start or after punctuation
    text = text.replace(/([.!?\n]|^)\s*(Here is your|Here's your)/gi, '$1\n\n$2');
    
    // Add line breaks after "Details:" and "Attendees:" and "Date:"
    text = text.replace(/(Details:|Attendees:|Date:)\s*([A-Z])/g, '$1\n$2');
    
    // Split by double newlines for paragraphs
    const paragraphs = text.split(/\n\s*\n/).filter(p => p.trim());
    
    const formattedBody = paragraphs.map(para => {
        para = para.trim();
        if (!para) return '';
        
        // Only format as header if it's EXACTLY a major section header (not containing other text)
        const isHeader = majorSectionHeaders.some(header => {
            // Must match exactly at start, optionally followed by colon and whitespace
            const regex = new RegExp(`^${header.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(:)?\\s*$`, 'i');
            return regex.test(para);
        });
        
        if (isHeader) {
            // Format as header
            const headerText = escapeHtml(para.replace(/:\s*$/, ''));
            return `<h3 style="margin: 24px 0 12px 0; font-size: 17px; font-weight: 700; color: var(--text-primary); border-bottom: 2px solid var(--border-color); padding-bottom: 8px;">${headerText}</h3>`;
        }
        
        // Check if it's a list item (starts with bullet, dash, number, or name with colon like "M M:")
        if (/^[-•*]\s/.test(para) || /^\d+\.\s/.test(para) || /^[A-Z][a-z]+\s+[A-Z][a-z]+:\s/.test(para)) {
            // Split by newlines to get individual list items
            const listItems = para.split(/\n/).filter(line => line.trim());
            const formattedList = listItems.map(item => {
                const trimmed = item.trim();
                if (!trimmed) return '';
                // Remove bullet/dash/number prefix
                const cleanItem = trimmed.replace(/^[-•*]\s/, '').replace(/^\d+\.\s/, '');
                return `<li style="margin: 8px 0; line-height: 1.7; color: var(--text-primary); font-weight: 400;">${escapeHtml(cleanItem)}</li>`;
            }).join('');
            return `<ul style="margin: 16px 0; padding-left: 28px; list-style-type: disc;">${formattedList}</ul>`;
        }
        
        // Regular paragraph - split by single newlines and join with spaces
        const lines = para.split('\n').map(line => line.trim()).filter(line => line);
        
        // Join lines with spaces to form proper paragraphs
        const formattedPara = escapeHtml(lines.join(' '));
        
        return `<p style="margin: 0 0 16px 0; line-height: 1.7; color: var(--text-primary); font-weight: 400;">${formattedPara}</p>`;
    }).join('');
    
    // If no paragraphs found, format as single paragraph with line breaks
    if (!formattedBody || formattedBody.trim() === '') {
        const lines = text.split('\n').filter(line => line.trim());
        if (lines.length > 1) {
            return lines.map(line => 
                `<p style="margin: 0 0 16px 0; line-height: 1.7; color: var(--text-primary); font-weight: 400;">${escapeHtml(line.trim())}</p>`
            ).join('');
        } else {
            return `<p style="margin: 0; line-height: 1.7; color: var(--text-primary); font-weight: 400; white-space: pre-wrap;">${escapeHtml(text)}</p>`;
        }
    }
    
    return formattedBody || '<p style="color: var(--text-secondary); font-style: italic;">No content</p>';
}

// Format date for display
function formatDate(timestamp) {
    if (!timestamp) return '';
    const date = new Date(typeof timestamp === 'string' ? parseInt(timestamp) : timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);
    
    if (diffMins < 1) {
        return 'Just now';
    } else if (diffMins < 60) {
        return `${diffMins}m ago`;
    } else if (diffHours < 24) {
        return `${diffHours}h ago`;
    } else if (diffDays < 7) {
        return date.toLocaleDateString('en-US', { weekday: 'short', hour: '2-digit', minute: '2-digit' });
    } else {
        return date.toLocaleDateString('en-US', { 
            month: 'short', 
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    }
}

// Parse sender info from email
function parseSender(fromField) {
    let senderName = '';
    let senderEmail = '';
    
    if (fromField.includes('<') && fromField.includes('>')) {
        const match = fromField.match(/^(.+?)\s*<(.+?)>$/);
        if (match) {
            senderName = decodeHtmlEntities(match[1].trim());
            senderEmail = match[2].trim();
        }
    } else {
        senderEmail = fromField.trim();
        senderName = decodeHtmlEntities(senderEmail.split('@')[0]);
    }
    
    return { senderName, senderEmail };
}

// Render a single email message in thread
function renderThreadMessage(email, isFirst = false) {
    const { senderName, senderEmail } = parseSender(email.from || '');
    const avatarLetter = (senderName || senderEmail).charAt(0).toUpperCase();
    const dateText = formatDate(email.date);
    const hasHtmlBody = !!(email.body_html || email.bodyHtml);
    const plainBodyHtml = formatEmailBody(email.body || email.snippet || '');
    
    // Handle attachments - download on-demand when clicked
    let attachmentsHtml = '';
    const attachments = email.attachments || [];
    if (attachments.length > 0) {
        const attHtml = attachments.map(att => {
            const filename = att.filename || 'attachment';
            const mimeType = att.mime_type || 'application/octet-stream';
            const attachmentId = att.attachment_id || '';
            const messageId = att.message_id || email.id;
            
            // Skip if no attachment_id (shouldn't happen)
            if (!attachmentId) {
                return '';
            }
            
            // Build download URL with query parameters
            const encodedFilename = encodeURIComponent(filename);
            const encodedMimeType = encodeURIComponent(mimeType);
            const url = `/api/attachment/${escapeHtml(messageId)}/${escapeHtml(attachmentId)}?filename=${encodedFilename}&mime_type=${encodedMimeType}`;
            
            // Format file size if available
            const sizeText = att.size ? ` (${formatFileSize(att.size)})` : '';
            
            if (mimeType === 'application/pdf') {
                // PDF - opens in new tab for browser viewing
                return `<a href="${url}" target="_blank" class="attachment-link" style="display: inline-flex; align-items: center; gap: 8px; padding: 8px 12px; background: #FEF3F2; border: 1px solid #FEE4E2; border-radius: 8px; color: #B42318; text-decoration: none; margin-right: 8px; margin-bottom: 8px; font-weight: 500;">
                    📄 ${escapeHtml(filename)}${sizeText}
                </a>`;
            } else if (mimeType.startsWith('image/')) {
                // Image - inline preview with download link (click to view full size)
                return `
                    <div class="image-attachment" style="display: inline-block; margin-right: 12px; margin-bottom: 12px; vertical-align: top;">
                        <a href="${url}" target="_blank" class="attachment-link" style="display: inline-flex; flex-direction: column; align-items: flex-start; gap: 6px; padding: 10px; background: var(--bg-secondary, #f9fafb); border: 1px solid var(--border-color, #e5e7eb); border-radius: 8px; text-decoration: none; transition: all 0.2s ease; cursor: pointer;" onmouseover="this.style.borderColor='var(--primary-color, #6366f1)'; this.style.boxShadow='0 2px 8px rgba(99, 102, 241, 0.1)'" onmouseout="this.style.borderColor='var(--border-color, #e5e7eb)'; this.style.boxShadow='none'">
                            <span style="color: var(--text-secondary, #6b7280); font-size: 12px; font-weight: 500;">📷 ${escapeHtml(filename)}${sizeText}</span>
                            <img src="${url}" alt="${escapeHtml(filename)}" style="max-width: 400px; max-height: 300px; border-radius: 6px; display: block; object-fit: contain; background: #fff; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1); cursor: pointer;" loading="lazy" onclick="event.preventDefault(); window.open('${url}', '_blank');" />
                        </a>
                    </div>
                `;
            } else {
                // Generic attachment - download
                return `<a href="${url}" download="${encodedFilename}" class="attachment-link" style="display: inline-flex; align-items: center; gap: 8px; padding: 8px 12px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 8px; color: var(--text-secondary); text-decoration: none; margin-right: 8px; margin-bottom: 8px;">
                    📎 ${escapeHtml(filename)}${sizeText}
                </a>`;
            }
        }).filter(html => html !== '').join('');
        attachmentsHtml = `<div style="margin-bottom: 16px; margin-top: 12px;"><strong style="color: var(--text-primary); font-size: 13px;">Attachments:</strong><div style="margin-top: 8px; display: flex; flex-wrap: wrap;">${attHtml}</div></div>`;
    }
    
    const bodySection = hasHtmlBody
        ? `
            <div class="thread-message-body html-mode" data-email-id="${escapeHtml(email.id || '')}" style="padding-left: 52px; line-height: 1.6; color: var(--text-primary); margin-bottom: 16px;"></div>
            <div class="thread-message-body plain-fallback" style="display: none; padding-left: 52px; line-height: 1.6; color: var(--text-secondary); font-size: 13px;">
                ${plainBodyHtml}
            </div>`
        : `<div class="thread-message-body" style="padding-left: 52px; line-height: 1.6; color: var(--text-primary);">
                ${plainBodyHtml}
           </div>`;
    
    return `
        <div class="thread-message" style="border-bottom: 1px solid var(--border-color); padding: 20px 0; ${isFirst ? 'padding-top: 0;' : ''}">
            <div style="display: flex; gap: 12px; margin-bottom: 12px;">
                <div class="thread-avatar" style="width: 40px; height: 40px; border-radius: 50%; background: var(--primary-color); color: white; display: flex; align-items: center; justify-content: center; font-weight: 600; font-size: 16px; flex-shrink: 0;">
                    ${avatarLetter}
                </div>
                <div style="flex: 1; min-width: 0;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                        <div>
                            <strong style="color: var(--text-primary); font-size: 14px;">${escapeHtml(senderName)}</strong>
                            <span style="color: var(--text-secondary); font-size: 13px; margin-left: 8px;">${escapeHtml(senderEmail)}</span>
                        </div>
                        <span style="color: var(--text-light); font-size: 12px;">${dateText}</span>
                    </div>
                </div>
            </div>
            ${attachmentsHtml}
            ${bodySection}
        </div>
    `;
}

// Enhance HTML emails by rendering body_html inside sandboxed iframes
function sanitizeEmailHtml(rawHtml) {
    if (!rawHtml) return '';
    try {
        const parser = new DOMParser();
        const doc = parser.parseFromString(rawHtml, 'text/html');
        
        // Remove scripts
        doc.querySelectorAll('script').forEach(el => el.remove());
        
        // Remove inline event handlers (onclick, onload, etc.)
        doc.querySelectorAll('*').forEach(el => {
            [...el.attributes].forEach(attr => {
                if (attr.name.toLowerCase().startsWith('on')) {
                    el.removeAttribute(attr.name);
                }
            });
        });
        
        return doc.documentElement.innerHTML;
    } catch (e) {
        console.error('Error sanitizing email HTML:', e);
        return rawHtml;
    }
}

function enhanceHtmlEmails(emails) {
    try {
        if (!emails || !emails.length) return;
        const threadContainer = document.getElementById('threadContainer');
        if (!threadContainer) return;
        
        emails.forEach(email => {
            const htmlBody = email.body_html || email.bodyHtml;
            if (!htmlBody || !htmlBody.trim()) return;
            if (!email.id) return;
            
            const selector = `.thread-message-body.html-mode[data-email-id="${CSS && CSS.escape ? CSS.escape(email.id) : email.id}"]`;
            const node = threadContainer.querySelector(selector);
            if (!node) return;
            
            node.innerHTML = '';
            const iframe = document.createElement('iframe');
            iframe.className = 'email-html-frame';
            // Security: Block scripts but allow styles and same-origin
            // This causes expected console warnings about blocked scripts - these are SAFE to ignore
            iframe.setAttribute('sandbox', 'allow-same-origin');
            iframe.style.width = '100%';
            iframe.style.border = 'none';
            iframe.style.minHeight = '400px';
            
            node.appendChild(iframe);
            
            // Sanitize HTML to remove any dangerous content before rendering
            const safeHtml = sanitizeEmailHtml(htmlBody);
            iframe.srcdoc = safeHtml;
            
            iframe.addEventListener('load', () => {
                try {
                    const doc = iframe.contentDocument || iframe.contentWindow.document;
                    const height = doc.body ? doc.body.scrollHeight : 0;
                    if (height) {
                        iframe.style.height = height + 'px';
                    }
                } catch (e) {
                    // If iframe fails to load, show plain text fallback
                    const plainFallback = node.parentElement.querySelector('.plain-fallback');
                    if (plainFallback) {
                        plainFallback.style.display = 'block';
                        node.style.display = 'none';
                    }
                }
            });
            
            // If iframe fails to load after timeout, show plain text fallback
            setTimeout(() => {
                if (!iframe.contentDocument || !iframe.contentDocument.body) {
                    const plainFallback = node.parentElement.querySelector('.plain-fallback');
                    if (plainFallback && plainFallback.style.display === 'none') {
                        plainFallback.style.display = 'block';
                        node.style.display = 'none';
                    }
                }
            }, 3000); // 3 second timeout
        });
    } catch (e) {
        console.error('Error enhancing HTML emails:', e);
    }
}

// Open email in modal - fetch and display full thread
async function openEmail(indexOrEmail) {
    // CRITICAL: Clear all previous email data FIRST to prevent showing wrong email
    const threadContainer = document.getElementById('threadContainer');
    const emailModal = document.getElementById('emailModal');
    
    // Clear thread container immediately
    if (threadContainer) {
        threadContainer.innerHTML = '';
    }
    
    // Clear composer fields
    clearComposerFields();
    
    // Accept either an index (from email list) or an email object directly (from deals table)
    let clickedEmail = null;
    if (typeof indexOrEmail === 'object' && indexOrEmail !== null) {
        // Email object passed directly
        clickedEmail = indexOrEmail;
    } else {
        // Index passed - this is now a GLOBAL index in filteredEmails (not page-relative)
        const globalIndex = indexOrEmail;
        
        // Use global index to get email directly from filteredEmails
        if (globalIndex >= 0 && globalIndex < filteredEmails.length) {
            clickedEmail = filteredEmails[globalIndex];
        } else if (globalIndex >= 0 && globalIndex < allEmails.length) {
            // Fallback to allEmails if not in filteredEmails
            clickedEmail = allEmails[globalIndex];
        } else {
            console.error(`Invalid email index: ${globalIndex} (filteredEmails: ${filteredEmails.length}, allEmails: ${allEmails.length})`);
        }
    }
    
    if (!clickedEmail || !clickedEmail.thread_id) {
        showAlert('error', 'Unable to load email thread');
        return;
    }
    
    // Set currentEmail to the clicked email IMMEDIATELY
    currentEmail = clickedEmail;
    currentReply = null;
    
    // Reset sending flag when opening a new email
    isSendingEmail = false;
    
    // Reset send button state if composer is visible (in case it was disabled from previous send)
    const composerSection = document.getElementById('composerSection');
    if (composerSection && composerSection.style.display !== 'none') {
        resetSendButtonState();
    }
    
    const threadId = currentEmail.thread_id;
    
    // Show modal immediately with correct email data
    if (emailModal) {
        emailModal.style.display = 'flex';
    }
    
    // Set modal header with clicked email's data IMMEDIATELY
    const subjectEl = document.getElementById('modalSubject');
    const initialSubject = currentEmail.subject && currentEmail.subject.trim() && currentEmail.subject !== 'No Subject' 
        ? decodeHtmlEntities(currentEmail.subject) 
        : 'No Subject';
    if (subjectEl) {
        subjectEl.textContent = initialSubject;
        subjectEl.style.display = 'block';
    }
    
    // Set initial sender/recipient info from clicked email
    const isSent = currentEmail.is_sent || currentEmail.classification?.category === 'SENT';
    const field = isSent ? (currentEmail.to || currentEmail.from || '') : (currentEmail.from || '');
    const { senderName, senderEmail } = parseSender(field);
    
    const modalFrom = document.getElementById('modalFrom');
    const modalFromEmail = document.getElementById('modalFromEmail');
    if (modalFrom) modalFrom.textContent = senderName;
    if (modalFromEmail) modalFromEmail.textContent = senderEmail;
    
    // Update label in modal header
    const modalFromSection = document.querySelector('.modal-from-section');
    if (modalFromSection) {
        const labelEl = modalFromSection.querySelector('.modal-from-label') || document.createElement('span');
        if (!labelEl.classList.contains('modal-from-label')) {
            labelEl.className = 'modal-from-label';
            labelEl.style.cssText = 'color: var(--text-secondary); font-size: 0.9em; margin-right: 8px;';
            modalFromSection.insertBefore(labelEl, modalFromSection.firstChild);
        }
        labelEl.textContent = isSent ? 'To:' : 'From:';
    }
    
    const avatarLetter = (senderName || senderEmail).charAt(0).toUpperCase();
    const modalAvatar = document.getElementById('modalAvatar');
    if (modalAvatar) modalAvatar.textContent = avatarLetter;
    
    // Set date
    const modalDate = document.getElementById('modalDate');
    if (modalDate) modalDate.textContent = formatDate(currentEmail.date);
    
    // Display CC and BCC if available
    const modalRecipients = document.getElementById('modalRecipients');
    const modalTo = document.getElementById('modalTo');
    const modalCc = document.getElementById('modalCc');
    const modalBcc = document.getElementById('modalBcc');
    
    if (modalRecipients && modalTo && modalCc && modalBcc) {
        let hasRecipients = false;
        
        // Display To field
        const toField = currentEmail.to || (isSent ? currentEmail.from : '');
        if (toField) {
            const toList = Array.isArray(toField) ? toField : (toField.includes(',') ? toField.split(',').map(e => e.trim()) : [toField]);
            modalTo.innerHTML = `<span style="color: #6b7280; margin-right: 8px;">To:</span>${toList.map(email => `<span style="color: #1f2937;">${escapeHtml(email)}</span>`).join(', ')}`;
            modalTo.style.display = 'block';
            hasRecipients = true;
        } else {
            modalTo.style.display = 'none';
        }
        
        // Display CC field
        const ccField = currentEmail.cc;
        if (ccField) {
            const ccList = Array.isArray(ccField) ? ccField : (ccField.includes(',') ? ccField.split(',').map(e => e.trim()) : [ccField]);
            modalCc.innerHTML = `<span style="color: #6b7280; margin-right: 8px;">Cc:</span>${ccList.map(email => `<span style="color: #1f2937;">${escapeHtml(email)}</span>`).join(', ')}`;
            modalCc.style.display = 'block';
            hasRecipients = true;
        } else {
            modalCc.style.display = 'none';
        }
        
        // Display BCC field
        const bccField = currentEmail.bcc;
        if (bccField) {
            const bccList = Array.isArray(bccField) ? bccField : (bccField.includes(',') ? bccField.split(',').map(e => e.trim()) : [bccField]);
            modalBcc.innerHTML = `<span style="color: #6b7280; margin-right: 8px;">Bcc:</span>${bccList.map(email => `<span style="color: #1f2937;">${escapeHtml(email)}</span>`).join(', ')}`;
            modalBcc.style.display = 'block';
            hasRecipients = true;
        } else {
            modalBcc.style.display = 'none';
        }
        
        // Show recipients section if any recipients exist
        if (hasRecipients) {
            modalRecipients.style.display = 'block';
        } else {
            modalRecipients.style.display = 'none';
        }
    }
    
    // Display category badge
    const classification = currentEmail.classification || {};
    const category = classification.category || 'UNKNOWN';
    const categoryBadge = getCategoryBadge(category);
    const modalCategoryBadge = document.getElementById('modalCategoryBadge');
    if (modalCategoryBadge) {
        modalCategoryBadge.innerHTML = categoryBadge || '';
    }
    
    // Show/hide spam warning banner
    const modalSpamWarning = document.getElementById('modalSpamWarning');
    if (modalSpamWarning) {
        if (category === 'SPAM') {
            modalSpamWarning.style.display = 'flex';
        } else {
            modalSpamWarning.style.display = 'none';
        }
    }
    
    // Hide single email section, show thread container
    const singleEmailSection = document.getElementById('singleEmailSection');
    if (singleEmailSection) singleEmailSection.style.display = 'none';
    
    // Show loading indicator if email content isn't available yet
    if (threadContainer && !(currentEmail.body || currentEmail.combined_text)) {
        threadContainer.innerHTML = `
            <div class="empty-state" style="text-align: center; padding: 60px 20px;">
                <div class="spinner" style="width: 40px; height: 40px; margin: 0 auto 20px; border: 3px solid rgba(99, 102, 241, 0.1); border-top-color: #6366f1; border-radius: 50%; animation: spin 1s linear infinite;"></div>
                <p style="font-size: 16px; color: var(--text-primary); margin-bottom: 8px; font-weight: 500;">Loading email...</p>
                <p style="font-size: 14px; color: var(--text-secondary);">Just a moment, we're fetching it for you ✨</p>
            </div>
        `;
    }
    
    // ALWAYS show clicked email from list IMMEDIATELY (0ms - no delay) if available
    if (threadContainer && (currentEmail.body || currentEmail.combined_text)) {
        threadContainer.innerHTML = renderThreadMessage(currentEmail, true);
        enhanceHtmlEmails([currentEmail]);
    }
    
    // INSTANT: Check in-memory cache first (0ms access) - but ONLY if thread_id matches
    let cached = threadCacheMemory.get(threadId);
    
    // Validate cached thread matches clicked email's thread_id BEFORE using it
    if (cached && cached.emails && cached.emails.length > 0) {
        const cachedThreadId = cached.emails[0]?.thread_id || cached.thread_id;
        if (cachedThreadId !== threadId) {
            // Wrong thread in cache - clear it
            cached = null;
            threadCacheMemory.delete(threadId);
        }
    }
    
    // If not in memory or invalid, check IndexedDB (async but should be fast if pre-fetched)
    if (!cached) {
        const indexedDBCache = await getCachedThread(threadId);
        if (indexedDBCache && indexedDBCache.emails && indexedDBCache.emails.length > 0) {
            const cachedThreadId = indexedDBCache.emails[0]?.thread_id || indexedDBCache.thread_id;
            if (cachedThreadId === threadId) {
                cached = indexedDBCache;
                // Store in memory for next time
                threadCacheMemory.set(threadId, cached);
            }
        }
    }
    
    // Only use cache if it matches the clicked email's thread_id
    if (cached && cached.emails && cached.emails.length > 0) {
        const cachedThreadId = cached.emails[0]?.thread_id || cached.thread_id;
        if (cachedThreadId === threadId && currentEmail && currentEmail.thread_id === threadId) {
            console.log(`⚡ Loading thread ${threadId} from cache (instant)`);
            
            // Display cached thread data immediately (replace single email with full thread)
            let threadHtml = '';
            cached.emails.forEach((email, idx) => {
                threadHtml += renderThreadMessage(email, idx === 0);
            });
            if (threadContainer) {
                threadContainer.innerHTML = threadHtml;
                enhanceHtmlEmails(cached.emails);
            }
            
            // Show subtle "refreshing" indicator
            showCacheRefreshIndicator();
        } else {
            console.log(`⚠️  Cache validation failed - keeping clicked email visible`);
            // Keep showing the clicked email - don't replace with wrong cache
        }
    }
    
    // Always fetch fresh data in background (even if cache exists)
    // BUT only update if we're still viewing the same email
    (async () => {
        // Store the threadId and emailId we're fetching for - CRITICAL for validation
        const fetchThreadId = threadId;
        const fetchEmailId = currentEmail.id || currentEmail.message_id;
        
        try {
            const response = await fetch(`/api/thread/${fetchThreadId}`);
            const data = await response.json();
            
            // CRITICAL: Validate we're still viewing the same email before ANY updates
            if (!currentEmail || currentEmail.thread_id !== fetchThreadId) {
                console.log(`⚠️  Email changed while fetching (expected ${fetchThreadId}, current ${currentEmail?.thread_id}), ignoring update`);
                hideCacheRefreshIndicator();
                return;
            }
            
            if (data.success && data.emails && data.emails.length > 0) {
                // Validate fetched thread matches
                const fetchedThreadId = data.emails[0]?.thread_id || fetchThreadId;
                if (fetchedThreadId !== fetchThreadId) {
                    console.log(`⚠️  Fetched thread ID mismatch (expected ${fetchThreadId}, got ${fetchedThreadId}), ignoring`);
                    return;
                }
                
                // Mark email as read automatically when opened
                // Check if email is unread: is_read === false OR has UNREAD label
                const isUnread = (currentEmail.is_read === false) || 
                                 (currentEmail.label_ids && currentEmail.label_ids.includes('UNREAD'));
                
                if (currentEmail && isUnread) {
                    console.log(`📧 Auto-marking email as read: ${currentEmail.id}`);
                    markEmailAsRead(currentEmail.id, currentEmail.thread_id);
                }
                
                // Cache the fresh data (both IndexedDB and memory)
                await cacheThread(fetchThreadId, data);
                threadCacheMemory.set(fetchThreadId, data); // Store in memory for instant access
                
                // Find the first email with a valid subject
                let subjectToUse = null;
                for (const email of data.emails) {
                    if (email.subject && email.subject.trim() && email.subject !== 'No Subject' && email.subject.trim().length > 0) {
                        subjectToUse = email.subject;
                        break;
                    }
                }
                
                // Update subject if we found one AND we're still viewing the same email
                if (subjectToUse && currentEmail && currentEmail.thread_id === fetchThreadId) {
                    const decodedSubject = decodeHtmlEntities(subjectToUse);
                    const subjectEl = document.getElementById('modalSubject');
                    if (subjectEl) {
                        subjectEl.textContent = decodedSubject;
                    }
                }
                
                // Update UI ONLY if we're still viewing the same thread
                if (currentEmail && currentEmail.thread_id === fetchThreadId && threadContainer) {
                    if (cached) {
                        // Check if thread changed (new messages arrived)
                        if (data.emails.length !== cached.emails.length || 
                            JSON.stringify(data.emails.map(e => e.id)) !== JSON.stringify(cached.emails.map(e => e.id))) {
                            // Render all messages in thread
                            let threadHtml = '';
                            data.emails.forEach((email, idx) => {
                                threadHtml += renderThreadMessage(email, idx === 0);
                            });
                            threadContainer.innerHTML = threadHtml;
                            enhanceHtmlEmails(data.emails);
                            showAlert('info', 'Thread updated');
                        }
                    } else {
                        // First time viewing - render fresh data
                        let threadHtml = '';
                        data.emails.forEach((email, idx) => {
                            threadHtml += renderThreadMessage(email, idx === 0);
                        });
                        threadContainer.innerHTML = threadHtml;
                        enhanceHtmlEmails(data.emails);
                    }
                } else {
                    console.log(`⚠️  Thread changed while loading (expected ${fetchThreadId}, current ${currentEmail?.thread_id}), ignoring update`);
                }
                
                hideCacheRefreshIndicator();
                
                // Only update currentEmail if we're still viewing the same thread
                if (currentEmail && currentEmail.thread_id === fetchThreadId) {
                    // Use the latest email for reply generation, but preserve original email fields
                    const latestEmail = data.emails[data.emails.length - 1];
                    // Merge with original email to preserve all fields (especially combined_text, attachments, etc.)
                    currentEmail = {
                        ...currentEmail,  // Keep original email data
                        ...latestEmail,    // Override with latest thread message data
                    // Ensure critical fields are preserved
                    subject: currentEmail.subject || latestEmail.subject || 'No Subject',
                    from: currentEmail.from || latestEmail.from || '',
                    combined_text: currentEmail.combined_text || latestEmail.combined_text || latestEmail.body || currentEmail.body || '',
                    body: latestEmail.body || currentEmail.body || '',
                    attachments: latestEmail.attachments || currentEmail.attachments || [],
                    headers: latestEmail.headers || currentEmail.headers || {},
                    thread_id: currentEmail.thread_id || latestEmail.thread_id,
                    id: latestEmail.id || currentEmail.id
                };
                }
            } else if (!currentEmail.body && !currentEmail.combined_text) {
                // Only show empty state if we didn't have cached data
                threadContainer.innerHTML = '<div class="empty-state"><p>No messages found in thread</p></div>';
                document.getElementById('singleEmailSection').style.display = 'block';
            }
        } catch (error) {
            console.error('Error fetching thread:', error);
            hideCacheRefreshIndicator();
            // Only show error if we didn't have cached data to display
            if (!cached && !currentEmail.body && !currentEmail.combined_text) {
                threadContainer.innerHTML = '<div class="empty-state"><p>Error loading thread</p></div>';
            }
        }
    })();
    
    // Reset AI reply section state (always visible in footer now)
    const replyContent = document.getElementById('replyContent');
    const replyActions = document.getElementById('replyActions');
    const replyLoading = document.getElementById('replyLoading');
    const aiReplyStatus = document.getElementById('aiReplyStatus');
    
    if (replyContent) {
        replyContent.innerHTML = '';
        replyContent.style.display = 'none';
    }
    if (replyActions) replyActions.style.display = 'none';
    if (replyLoading) replyLoading.style.display = 'none';
    if (aiReplyStatus) aiReplyStatus.textContent = 'Ready';
    
    // Clear composer when opening a new email (prevent draft from previous email)
    clearComposer();
}

// Close modal
function closeModal() {
    const emailModal = document.getElementById('emailModal');
    if (emailModal) {
        emailModal.style.display = 'none';
    }
    currentEmail = null;
    currentReply = null;
    
    // Reset AI reply section
    const replyContent = document.getElementById('replyContent');
    const replyLoading = document.getElementById('replyLoading');
    const replyActions = document.getElementById('replyActions');
    const aiReplyStatus = document.getElementById('aiReplyStatus');
    const generateReplyBtn = document.getElementById('generateReplyBtn');
    
    if (replyContent) {
        replyContent.style.display = 'none';
        replyContent.innerHTML = '';
    }
    if (replyLoading) replyLoading.style.display = 'none';
    if (replyActions) replyActions.style.display = 'none';
    if (aiReplyStatus) aiReplyStatus.textContent = 'Ready';
    if (generateReplyBtn) generateReplyBtn.disabled = false;
    
    // Restore pagination when modal closes
    // This ensures pagination is maintained after viewing an email
    if (filteredEmails && filteredEmails.length > EMAILS_PER_PAGE) {
        updatePagination();
    }
}

// Signature selector functions
function openSignatureSelector() {
    document.getElementById('signatureModal').style.display = 'flex';
    loadSignatures();
}

function closeSignatureModal() {
    document.getElementById('signatureModal').style.display = 'none';
}

async function loadSignatures() {
    const signatureList = document.getElementById('signatureList');
    signatureList.innerHTML = '<div class="spinner-small"></div><p>Loading signatures...</p>';
    
    try {
        const response = await fetch('/api/signatures');
        const data = await response.json();
        
        if (!data.success) {
            signatureList.innerHTML = `<div class="alert alert-danger">${escapeHtml(data.error)}</div>`;
            return;
        }
        
        const signatures = data.signatures || [];
        const selected = data.selected;
        
        if (signatures.length === 0) {
            signatureList.innerHTML = '<div class="alert alert-info">No signatures found. Please set up a signature in Gmail settings.</div>';
            return;
        }
        
        let html = '';
        signatures.forEach(sig => {
            const isSelected = (!selected && sig.isPrimary) || (selected === sig.email);
            const selectedClass = isSelected ? 'btn-primary' : 'btn-secondary';
            const selectedBadge = isSelected ? '<span style="margin-left: 8px; font-size: 12px; opacity: 0.8;">✓ Selected</span>' : '';
            const primaryBadge = sig.isPrimary ? '<span style="margin-left: 8px; font-size: 12px; opacity: 0.7;">Primary</span>' : '';
            
            // Check if signature exists (either processed or raw)
            const hasSignature = sig.hasSignature || (sig.signatureRaw && sig.signatureRaw.trim().length > 0) || (sig.signatureHtml && sig.signatureHtml.trim().length > 0);
            // Use HTML signature if available, otherwise fall back to plain text
            const signatureHtml = sig.signatureHtml || sig.signatureRaw || '';
            const signatureToShow = sig.signature || '';
            
            const signaturePreview = hasSignature && signatureHtml ? 
                `<div style="margin-top: 8px; padding: 12px; background: var(--bg-secondary); border-radius: 8px; font-size: 13px; max-height: 150px; overflow-y: auto; border: 1px solid var(--border-color); line-height: 1.5;">${signatureHtml}</div>` :
                hasSignature ? 
                `<div style="margin-top: 8px; padding: 12px; background: var(--bg-secondary); border-radius: 8px; font-size: 13px; color: var(--text-secondary); white-space: pre-wrap; max-height: 100px; overflow-y: auto; border: 1px solid var(--border-color);">${escapeHtml(signatureToShow.substring(0, 300))}${signatureToShow.length > 300 ? '...' : ''}</div>` :
                '<div style="margin-top: 8px; padding: 12px; background: var(--bg-secondary); border-radius: 8px; font-size: 12px; color: var(--text-light); font-style: italic; border: 1px dashed var(--border-color);">No signature set in Gmail settings</div>';
            
            html += `
                <div style="border: 1px solid var(--border-color); border-radius: 12px; padding: 16px; background: var(--bg-secondary);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <div>
                            <strong style="color: var(--text-primary);">${escapeHtml(sig.displayName || sig.email)}</strong>
                            ${primaryBadge}
                            ${selectedBadge}
                        </div>
                        <button class="btn btn-small ${selectedClass}" onclick="selectSignature('${sig.email}')" ${isSelected ? 'disabled' : ''}>
                            ${isSelected ? 'Selected' : 'Select'}
                        </button>
                    </div>
                    <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">${escapeHtml(sig.email)}</div>
                    ${signaturePreview}
                </div>
            `;
        });
        
        signatureList.innerHTML = html;
    } catch (error) {
        signatureList.innerHTML = `<div class="alert alert-danger">Error loading signatures: ${escapeHtml(error.message)}</div>`;
    }
}

async function selectSignature(email) {
    try {
        const response = await fetch('/api/signature/select', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ email: email || null })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Reload signatures to show updated selection
            loadSignatures();
            // Also reload in settings if modal is open
            if (document.getElementById('settingsModal')?.style.display !== 'none') {
                loadSignaturesInSettings();
            }
            
            // Show success message
            const alert = document.createElement('div');
            alert.className = 'alert alert-success';
            alert.style.position = 'fixed';
            alert.style.top = '20px';
            alert.style.right = '20px';
            alert.style.zIndex = '10000';
            alert.innerHTML = '✓ Signature preference saved';
            document.body.appendChild(alert);
            
            setTimeout(() => {
                alert.remove();
            }, 3000);
        } else {
            alert('Error: ' + data.error);
        }
    } catch (error) {
        alert('Error: ' + error.message);
    }
}

// Load signature (no preview box, just for insertion into body)
async function loadSignaturePreview(type) {
    // This function is kept for compatibility but doesn't show a preview box
    // Signature is inserted directly into the body textarea
    return;
}

// Helper function to get content from contenteditable div or textarea
function getBodyContent(element) {
    if (element.contentEditable === 'true') {
        return element.innerHTML;
    }
    return element.value || '';
}

// Helper function to set content in contenteditable div or textarea
function setBodyContent(element, content) {
    if (element.contentEditable === 'true') {
        element.innerHTML = content;
    } else {
        element.value = content;
    }
}

// Helper function to check if signature is already in body
function bodyContainsSignature(bodyContent, signatureHtml) {
    // Check both HTML and plain text versions
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = signatureHtml;
    const signatureText = tempDiv.textContent || tempDiv.innerText || '';
    return bodyContent.includes(signatureText.substring(0, 50)) || bodyContent.includes(signatureHtml.substring(0, 100));
}

// Cache signature to avoid repeated API calls
let cachedSignature = null;
let signatureCacheTime = 0;
let signatureLoadPromise = null; // Track ongoing load to avoid duplicate requests
const SIGNATURE_CACHE_DURATION = 60000; // 1 minute cache

// Pre-load signature on page load for instant access
function preloadSignature() {
    // Don't wait for it, just start loading in background
    getSignature();
}

// Get signature (with caching and instant return if cached)
async function getSignature() {
    // Check cache first - return instantly if available
    const now = Date.now();
    if (cachedSignature && (now - signatureCacheTime) < SIGNATURE_CACHE_DURATION) {
        return cachedSignature;
    }
    
    // If already loading, return the existing promise
    if (signatureLoadPromise) {
        return signatureLoadPromise;
    }
    
    // Start loading
    signatureLoadPromise = (async () => {
        try {
            const response = await fetch('/api/signatures');
            const data = await response.json();
            
            if (!data.success || !data.signatures || data.signatures.length === 0) {
                signatureLoadPromise = null;
                return null;
            }
            
            const signatures = data.signatures;
            const selected = data.selected;
            
            // Find selected signature (or primary if none selected)
            const selectedSig = signatures.find(sig => (!selected && sig.isPrimary) || (selected === sig.email)) || signatures[0];
            
            if (selectedSig && (selectedSig.signatureHtml || selectedSig.signatureRaw)) {
                cachedSignature = selectedSig.signatureHtml || selectedSig.signatureRaw;
                signatureCacheTime = Date.now();
                signatureLoadPromise = null;
                return cachedSignature;
            }
            
            signatureLoadPromise = null;
            return null;
        } catch (error) {
            console.error('Error fetching signature:', error);
            signatureLoadPromise = null;
            return null;
        }
    })();
    
    return signatureLoadPromise;
}

// Insert signature into body (for reply/reply all - a bit down from top)
async function insertSignatureIntoBody(type) {
    // type can be 'reply' or 'compose'
    const bodyId = type === 'compose' ? 'composeBody' : 'composerBody';
    const bodyEl = document.getElementById(bodyId);
    
    if (!bodyEl) return;
    
    // Get signature (uses cache if available - should be instant if preloaded)
    const signatureHtml = await getSignature();
    
    if (!signatureHtml) {
        return;
    }
    
    const currentBody = getBodyContent(bodyEl);
    
    // Check if signature is already in body
    if (bodyContainsSignature(currentBody, signatureHtml)) {
        return;
    }
    
    // For reply/reply all, insert a bit down (after some spacing for user to type)
    if (type === 'reply') {
        // Insert signature after a few line breaks, not at the very top
        // This gives space for the user to type their message above the signature
        const spacing = '<br><br>'; // Space for user to type
        const trimmedBody = currentBody.trim();
        
        // If body is empty or just has quoted text, add spacing then signature
        if (!trimmedBody || trimmedBody.startsWith('<br><br>')) {
            setBodyContent(bodyEl, spacing + signatureHtml + '<br><br>' + trimmedBody);
        } else {
            // If user has already typed something, insert signature after their text
            setBodyContent(bodyEl, trimmedBody + '<br><br>' + signatureHtml + '<br><br>');
        }
    } else {
        // For compose, always append at the very bottom (end) of the body
        const trimmedBody = currentBody.trim();
        
        // Check if signature is already in body
        if (bodyContainsSignature(trimmedBody, signatureHtml)) {
            return;
        }
        
        // Always add signature at the bottom, even if body is empty
        // This way it's ready and visible at the bottom
        if (trimmedBody) {
            // User has typed something, append signature at the end
            setBodyContent(bodyEl, trimmedBody + '<br><br>' + signatureHtml);
        } else {
            // Body is empty, add signature at the bottom (user will type above it)
            setBodyContent(bodyEl, '<br><br>' + signatureHtml);
        }
    }
}

// Load signatures in settings modal
async function loadSignaturesInSettings() {
    const signatureListContainer = document.getElementById('signatureListContainer');
    const signatureListSettings = document.getElementById('signatureListSettings');
    const selectedSignatureDisplay = document.getElementById('selectedSignatureDisplay');
    
    if (!signatureListContainer || !signatureListSettings || !selectedSignatureDisplay) {
        return;
    }
    
    // Always load and update the selected signature display first
    try {
        const response = await fetch('/api/signatures');
        const data = await response.json();
        
        if (data.success) {
            const signatures = data.signatures || [];
            const selected = data.selected;
            
            if (signatures.length > 0) {
                // Update selected signature display
                const selectedSig = signatures.find(sig => (!selected && sig.isPrimary) || (selected === sig.email)) || signatures[0];
                if (selectedSig) {
                    selectedSignatureDisplay.textContent = `${selectedSig.displayName || selectedSig.email}${selectedSig.isPrimary ? ' (Primary)' : ''}`;
                }
            } else {
                selectedSignatureDisplay.textContent = 'No signatures available';
            }
        }
    } catch (error) {
        selectedSignatureDisplay.textContent = 'Error loading signatures';
    }
    
    // Toggle visibility of signature list
    const isVisible = signatureListContainer.style.display !== 'none';
    if (isVisible) {
        signatureListContainer.style.display = 'none';
        return;
    }
    
    signatureListContainer.style.display = 'block';
    signatureListSettings.innerHTML = '<div class="spinner-small"></div><p style="text-align: center; color: #6B7280; margin-top: 8px;">Loading signatures...</p>';
    
    try {
        const response = await fetch('/api/signatures');
        const data = await response.json();
        
        if (!data.success) {
            signatureListSettings.innerHTML = `<div style="padding: 12px; background: #FEE2E2; color: #DC2626; border-radius: 8px; font-size: 14px;">${escapeHtml(data.error)}</div>`;
            return;
        }
        
        const signatures = data.signatures || [];
        const selected = data.selected;
        
        if (signatures.length === 0) {
            signatureListSettings.innerHTML = '<div style="padding: 12px; background: #FEF3C7; color: #92400E; border-radius: 8px; font-size: 14px;">No signatures found. Please set up a signature in Gmail settings.</div>';
            return;
        }
        
        // Render signature list
        let html = '';
        signatures.forEach(sig => {
            const isSelected = (!selected && sig.isPrimary) || (selected === sig.email);
            const hasSignature = sig.hasSignature || (sig.signatureRaw && sig.signatureRaw.trim().length > 0) || (sig.signatureHtml && sig.signatureHtml.trim().length > 0);
            // Use HTML signature if available, otherwise fall back to plain text
            const signatureHtml = sig.signatureHtml || sig.signatureRaw || '';
            const signatureToShow = sig.signature || '';
            
            html += `
                <div style="border: 1px solid #E5E7EB; border-radius: 8px; padding: 16px; background: #FFFFFF; ${isSelected ? 'border-color: #3B82F6; border-width: 2px;' : ''}">
                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
                        <div style="flex: 1;">
                            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
                                <strong style="color: #111827; font-size: 14px;">${escapeHtml(sig.displayName || sig.email)}</strong>
                                ${sig.isPrimary ? '<span style="font-size: 11px; padding: 2px 6px; background: #F3F4F6; color: #6B7280; border-radius: 4px;">Primary</span>' : ''}
                                ${isSelected ? '<span style="font-size: 11px; padding: 2px 6px; background: #DBEAFE; color: #1E40AF; border-radius: 4px; font-weight: 500;">Selected</span>' : ''}
                            </div>
                            <div style="font-size: 12px; color: #6B7280;">${escapeHtml(sig.email)}</div>
                        </div>
                        <button 
                            onclick="selectSignature('${sig.email}')" 
                            style="padding: 6px 12px; font-size: 13px; border-radius: 6px; border: 1px solid #D1D5DB; background: ${isSelected ? '#3B82F6' : '#FFFFFF'}; color: ${isSelected ? '#FFFFFF' : '#374151'}; cursor: ${isSelected ? 'default' : 'pointer'}; font-weight: 500;"
                            ${isSelected ? 'disabled' : ''}
                        >
                            ${isSelected ? 'Selected' : 'Select'}
                        </button>
                    </div>
                    ${hasSignature && signatureHtml ? 
                        `<div style="margin-top: 12px; padding: 12px; background: #F9FAFB; border-radius: 6px; font-size: 13px; max-height: 150px; overflow-y: auto; border: 1px solid #E5E7EB; line-height: 1.5;">${signatureHtml}</div>` :
                        hasSignature ? 
                        `<div style="margin-top: 12px; padding: 12px; background: #F9FAFB; border-radius: 6px; font-size: 13px; color: #374151; white-space: pre-wrap; max-height: 120px; overflow-y: auto; border: 1px solid #E5E7EB;">${escapeHtml(signatureToShow.substring(0, 200))}${signatureToShow.length > 200 ? '...' : ''}</div>` :
                        '<div style="margin-top: 12px; padding: 12px; background: #F9FAFB; border-radius: 6px; font-size: 12px; color: #9CA3AF; font-style: italic; border: 1px dashed #E5E7EB;">No signature set in Gmail settings</div>'
                    }
                </div>
            `;
        });
        
        signatureListSettings.innerHTML = html;
    } catch (error) {
        signatureListSettings.innerHTML = `<div style="padding: 12px; background: #FEE2E2; color: #DC2626; border-radius: 8px; font-size: 14px;">Error loading signatures: ${escapeHtml(error.message)}</div>`;
    }
}

// Close modal when clicking outside
window.onclick = function(event) {
    const emailModal = document.getElementById('emailModal');
    const signatureModal = document.getElementById('signatureModal');
    const composeModal = document.getElementById('composeModal');
    
    if (event.target === emailModal) {
        closeModal();
    }
    if (event.target === signatureModal) {
        closeSignatureModal();
    }
    if (event.target === composeModal) {
        closeComposeModal();
    }
}

// Generate AI reply
async function generateReply() {
    if (!currentEmail) return;
    
    const replyLoading = document.getElementById('replyLoading');
    const replyContent = document.getElementById('replyContent');
    const replyActions = document.getElementById('replyActions');
    const aiReplyStatus = document.getElementById('aiReplyStatus');
    const generateReplyBtn = document.getElementById('generateReplyBtn');
    
    // Show loading
    if (replyLoading) replyLoading.style.display = 'flex';
    if (replyContent) replyContent.style.display = 'none';
    if (replyContent) replyContent.innerHTML = '';
    if (replyActions) replyActions.style.display = 'none';
    if (aiReplyStatus) aiReplyStatus.textContent = 'Generating...';
    if (generateReplyBtn) generateReplyBtn.disabled = true;
    
    try {
        // Use combined_text (includes PDF content) if available, otherwise body
        const emailBody = currentEmail.combined_text || currentEmail.body || '';
        const attachments = currentEmail.attachments || [];
        const subject = currentEmail.subject || 'No Subject';
        const fromField = currentEmail.from || '';
        
        // Validate required fields
        if (!subject || !emailBody || !fromField) {
            console.error('Missing required fields:', {
                subject: subject,
                body: emailBody ? `${emailBody.length} chars` : 'missing',
                from: fromField
            });
            showAlert('error', `Missing required fields. Subject: ${subject ? '✓' : '✗'}, Body: ${emailBody ? '✓' : '✗'}, From: ${fromField ? '✓' : '✗'}`);
            replyLoading.style.display = 'none';
            return;
        }
        
        const response = await fetch('/api/generate-reply', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                email_id: currentEmail.id,
                subject: subject,
                body: emailBody,  // Use combined_text which includes PDF content
                combined_text: emailBody,  // Explicitly pass combined_text
                attachments: attachments,  // Pass attachment info
                from: fromField,
                thread_id: currentEmail.thread_id,
                headers: currentEmail.headers || {}
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            if (!data.should_reply) {
                if (replyContent) {
                    replyContent.innerHTML = `<div style="color: #6b7280; font-size: 0.875rem;">${data.message || 'AI determined this email doesn\'t need a reply'}</div>`;
                    replyContent.style.display = 'block';
                }
                if (aiReplyStatus) aiReplyStatus.textContent = 'No reply needed';
            } else {
                currentReply = data.reply;
                if (replyContent) {
                replyContent.textContent = data.reply;
                    replyContent.style.display = 'block';
                }
                if (replyActions) replyActions.style.display = 'flex';
                if (aiReplyStatus) aiReplyStatus.textContent = 'Generated';
            }
        } else {
            showToast('error', data.error || 'Failed to generate reply');
            if (aiReplyStatus) aiReplyStatus.textContent = 'Error';
        }
    } catch (error) {
        console.error('Error generating reply:', error);
        showToast('error', 'Error generating reply: ' + error.message);
        if (aiReplyStatus) aiReplyStatus.textContent = 'Error';
    } finally {
        if (replyLoading) replyLoading.style.display = 'none';
        if (generateReplyBtn) generateReplyBtn.disabled = false;
    }
}

// Edit reply
function editReply() {
    if (!currentReply) return;
    
    const replyContent = document.getElementById('replyContent');
    const replyEditor = document.getElementById('replyEditor');
    
    // Switch to editor mode
    replyEditor.value = currentReply;
    replyContent.style.display = 'none';
    replyEditor.style.display = 'block';
    
    // Update button
    const editBtn = document.querySelector('#replyActions .btn-secondary');
    if (editBtn) {
        editBtn.textContent = '💾 Save Edit';
        editBtn.onclick = saveEdit;
    }
}

// Save edited reply
function saveEdit() {
    const replyEditor = document.getElementById('replyEditor');
    const replyContent = document.getElementById('replyContent');
    
    currentReply = replyEditor.value;
    replyContent.textContent = currentReply;
    
    // Switch back to display mode
    replyEditor.style.display = 'none';
    replyContent.style.display = 'block';
    
    // Update button
    const editBtn = document.querySelector('#replyActions .btn-secondary');
    if (editBtn) {
        editBtn.textContent = '✏️ Edit';
        editBtn.onclick = editReply;
    }
}

// Delete current email from modal
async function deleteCurrentEmail() {
    if (!currentEmail || !currentEmail.id) {
        showToast('No email selected', 'error');
        return;
    }
    await deleteEmail(currentEmail.id, currentEmail.thread_id);
}

// Archive email (remove from inbox)
async function archiveEmail() {
    if (!currentEmail || !currentEmail.id) {
        showAlert('error', 'No email selected');
        return;
    }
    // TODO: Implement archive functionality
    showAlert('info', 'Archive functionality coming soon');
}

// Mark email as unread
async function markAsUnread() {
    if (!currentEmail || !currentEmail.id) {
        showToast('No email selected', 'error');
        return;
    }
    await markEmailAsUnread(currentEmail.id);
}

// Mark email as spam and archive
async function markAsSpam() {
    if (!currentEmail || !currentEmail.id) {
        showToast('No email selected', 'error');
        return;
    }
    // TODO: Implement mark as spam functionality
    showToast('Mark as spam functionality coming soon', 'info');
}

// Mark email as not spam
async function markAsNotSpam() {
    if (!currentEmail || !currentEmail.id) {
        showToast('No email selected', 'error');
        return;
    }
    // TODO: Implement mark as not spam functionality
    showToast('Mark as not spam functionality coming soon', 'info');
}

// Open reply composer (to be implemented with full features)
// Composer state
let composerMode = 'reply'; // 'reply', 'reply-all', or 'forward'
let composerAttachments = [];
let currentDraftId = null; // Track the current draft ID for updates
let autosaveTimeout = null; // Debounce autosave
let quotedTextStartMarker = '\n\n'; // Marker to identify where quoted text starts

// Extract new content from composer (excluding quoted text)
function getNewComposerContent() {
    const composerBody = document.getElementById('composerBody');
    if (!composerBody) return '';
    
    const fullBody = getBodyContent(composerBody);
    
    // For HTML content, find where quoted text starts (look for "On " in text)
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = fullBody;
    const textContent = tempDiv.textContent || tempDiv.innerText || '';
    
    // Find where quoted text starts
    const quotedIndex = textContent.indexOf('\n\nOn ');
    if (quotedIndex === -1) {
        // No quoted text found, return full body (strip HTML tags for comparison)
        return textContent.trim();
    }
    
    // Return only the new content before quoted text (as HTML)
    const htmlBeforeQuoted = fullBody.substring(0, fullBody.indexOf(textContent.substring(quotedIndex).substring(0, 20)));
    return htmlBeforeQuoted.trim();
}

// Check if composer has meaningful new content
function hasNewContent() {
    const newContent = getNewComposerContent();
    return newContent.length > 0;
}

// Autosave draft to Gmail
async function autosaveDraft() {
    // Don't autosave if email is currently being sent
    if (isSendingEmail) {
        console.log('💾 Skipping autosave: email is being sent');
        return;
    }
    
    // Clear any pending autosave
    if (autosaveTimeout) {
        clearTimeout(autosaveTimeout);
        autosaveTimeout = null;
    }
    
    // Check if there's new content to save
    if (!hasNewContent()) {
        console.log('💾 Skipping autosave: no new content (only quoted text)');
        return;
    }
    
    const composerTo = document.getElementById('composerTo');
    const composerCc = document.getElementById('composerCc');
    const composerBcc = document.getElementById('composerBcc');
    const composerSubject = document.getElementById('composerSubject');
    const composerBody = document.getElementById('composerBody');
    
    if (!composerTo || !composerSubject || !composerBody) return;
    
    const to = composerTo.value.trim();
    const cc = composerCc && composerCc.value.trim();
    const bcc = composerBcc && composerBcc.value.trim();
    const subject = composerSubject.value.trim();
    const body = getBodyContent(composerBody); // Keep full body with quoted text for display
    
    if (!to) {
        console.log('💾 Skipping autosave: no recipient');
        return;
    }
    
    try {
        const thread_id = currentEmail ? currentEmail.thread_id : null;
        
        if (currentDraftId) {
            // Update existing draft
            console.log(`💾 Updating draft: ${currentDraftId}`);
            const response = await fetch(`/api/drafts/${currentDraftId}/update`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ to, cc, bcc, subject, body, thread_id })
            });
            
            const data = await response.json();
            if (data.success) {
                console.log(`✅ Draft updated: ${currentDraftId}`);
                // Only show toast if not sending (to prevent "Draft saved" when clicking send)
                if (!isSendingEmail) {
                showToast('Draft saved', 'info');
                }
            } else {
                console.error('Failed to update draft:', data.error);
            }
        } else {
            // Create new draft
            console.log('💾 Creating new draft');
            const response = await fetch('/api/drafts/create', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ to, cc, bcc, subject, body, thread_id })
            });
            
            const data = await response.json();
            if (data.success) {
                currentDraftId = data.draft.draft_id;
                console.log(`✅ Draft created: ${currentDraftId}`);
                // Only show toast if not sending (to prevent "Draft saved" when clicking send)
                if (!isSendingEmail) {
                showToast('Draft saved', 'info');
                }
            } else {
                console.error('Failed to create draft:', data.error);
            }
        }
    } catch (error) {
        console.error('Error autosaving draft:', error);
    }
}

// Schedule autosave with debounce (saves 2 seconds after user stops typing)
function scheduleAutosave() {
    if (autosaveTimeout) {
        clearTimeout(autosaveTimeout);
    }
    
    autosaveTimeout = setTimeout(() => {
        autosaveDraft();
    }, 2000); // 2 second debounce
}

// Real-time Gmail sync: Poll for label changes
let labelChangePollInterval = null;

function startLabelChangePolling() {
    // Poll every 10 seconds for label changes from Gmail
    if (labelChangePollInterval) {
        clearInterval(labelChangePollInterval);
    }
    
    labelChangePollInterval = setInterval(async () => {
        try {
            const response = await fetch('/api/sync/label-changes');
            const data = await response.json();
            
            if (data.success && data.changes && Object.keys(data.changes).length > 0) {
                console.log(`🔄 [SYNC] Received ${Object.keys(data.changes).length} label changes from Gmail`);
                
                // Process each label change
                for (const [messageId, changeInfo] of Object.entries(data.changes)) {
                    const isRead = changeInfo.is_read;
                    const labelIds = changeInfo.label_ids || [];
                    
                    console.log(`  ${ isRead ? '✅' : '📧'} Message ${messageId.substring(0, 16)}: ${isRead ? 'read' : 'unread'} in Gmail`);
                    
                    // Update local caches with the new read status
                    updateEmailReadStatusFromSync(messageId, isRead, labelIds);
                }
                
                // Show toast notification
                const changeCount = Object.keys(data.changes).length;
                const readCount = Object.values(data.changes).filter(c => c.is_read).length;
                const unreadCount = changeCount - readCount;
                
                let message = 'Synced with Gmail: ';
                if (readCount > 0) message += `${readCount} marked as read`;
                if (readCount > 0 && unreadCount > 0) message += ', ';
                if (unreadCount > 0) message += `${unreadCount} marked as unread`;
                
                showToast(message, 'info');
            }
        } catch (error) {
            console.error('Error polling for label changes:', error);
        }
    }, 10000); // Poll every 10 seconds
    
    console.log('🔄 Started polling for Gmail label changes (every 10 seconds)');
}

function stopLabelChangePolling() {
    if (labelChangePollInterval) {
        clearInterval(labelChangePollInterval);
        labelChangePollInterval = null;
        console.log('🛑 Stopped polling for Gmail label changes');
    }
}

// Update email read status from Gmail sync (similar to updateEmailReadStatus but for external changes)
function updateEmailReadStatusFromSync(messageId, isRead, labelIds) {
    console.log(`🔄 [SYNC] Updating email ${messageId.substring(0, 16)} to ${isRead ? 'read' : 'unread'} from Gmail sync`);
    
    let updatedCount = 0;
    
    // Helper function to update email object
    const updateEmail = (email) => {
        if (email.id === messageId || email.message_id === messageId) {
            email.is_read = isRead;
            email.label_ids = labelIds;
            updatedCount++;
            return true;
        }
        return false;
    };
    
    // Update in allEmails
    allEmails.forEach(updateEmail);
    
    // Update in emailCache
    if (emailCache && emailCache.data) {
        emailCache.data.forEach(updateEmail);
        saveEmailCacheToStorage();
    }
    
    // Update in filteredEmails
    filteredEmails.forEach(updateEmail);
    
    if (updatedCount > 0) {
        console.log(`✅ [SYNC] Updated ${updatedCount} instance(s) of email ${messageId.substring(0, 16)}`);
        
        // Refresh display to show updated read/unread styling
        updatePagination(); // Use updatePagination to preserve pagination
        
        // Update unread counts
        updateSidebarUnreadCounts();
    }
}

// Initialize autosave listeners for composer
function initAutosaveListeners() {
    const composerBody = document.getElementById('composerBody');
    const composerTo = document.getElementById('composerTo');
    const composerSubject = document.getElementById('composerSubject');
    
    if (composerBody) {
        // Autosave on input (debounced)
        composerBody.addEventListener('input', scheduleAutosave);
        
        // Autosave when leaving the composer
        composerBody.addEventListener('blur', () => {
            if (hasNewContent()) {
                autosaveDraft();
            }
        });
    }
    
    if (composerTo) {
        composerTo.addEventListener('blur', () => {
            if (hasNewContent()) {
                autosaveDraft();
            }
        });
    }
    
    if (composerSubject) {
        composerSubject.addEventListener('input', scheduleAutosave);
    }
}

// Clear draft state (call when sending or canceling)
function clearDraftState() {
    currentDraftId = null;
    if (autosaveTimeout) {
        clearTimeout(autosaveTimeout);
        autosaveTimeout = null;
    }
}

// Reset send button state (enabled, text back to original)
function resetSendButtonState() {
    const sendBtn = document.querySelector('#composerSection .btn-primary');
    if (sendBtn) {
        sendBtn.disabled = false;
        sendBtn.textContent = '✉️ Send';
    }
}

function openDraft(draftIndex) {
    // Get the draft email from filteredEmails
    const draftEmail = filteredEmails[draftIndex];
    
    if (!draftEmail || !draftEmail.is_draft) {
        showAlert('error', 'Draft not found');
        return;
    }
    
    console.log('📝 Opening draft for editing:', draftEmail);
    
    // Set current email to the draft
    currentEmail = draftEmail;
    
    // Clear previous draft state
    clearDraftState();
    
    // Set composer mode based on draft type
    composerMode = draftEmail.in_reply_to ? 'reply' : 'compose';
    
    // Open composer
    const composerSection = document.getElementById('composerSection');
    const composerTitle = document.getElementById('composerTitle');
    const composerTo = document.getElementById('composerTo');
    const composerSubject = document.getElementById('composerSubject');
    const composerBody = document.getElementById('composerBody');
    
    // Set title
    composerTitle.textContent = composerMode === 'reply' ? 'Edit Draft Reply' : 'Edit Draft';
    
    // Populate fields with draft data
    composerTo.value = draftEmail.to || '';
    composerSubject.value = draftEmail.subject || '';
    setBodyContent(composerBody, draftEmail.body_html || draftEmail.body || '');
    
    // Store draft ID for later update/deletion
    currentDraftId = draftEmail.draft_id || draftEmail.id;
    console.log(`📝 Editing draft ID: ${currentDraftId}`);
    
    // Show composer
    composerSection.style.display = 'block';
    composerBody.focus();
    
    // Scroll to composer
    composerSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function openReplyComposer() {
    if (!currentEmail) {
        showAlert('error', 'No email selected');
        return;
    }
    
    // Reset sending flag when opening reply composer
    isSendingEmail = false;
    
    // Reset send button state (in case it was disabled from previous send)
    resetSendButtonState();
    
    // Clear draft state for new compose
    clearDraftState();
    
    composerMode = 'reply';
    const composerSection = document.getElementById('composerSection');
    const composerTitle = document.getElementById('composerTitle');
    const composerTo = document.getElementById('composerTo');
    const composerSubject = document.getElementById('composerSubject');
    const composerBody = document.getElementById('composerBody');
    
    // Set title
    composerTitle.textContent = 'Reply';
    
    // Extract email from sender
    const senderEmail = extractEmail(currentEmail.from || '');
    composerTo.value = senderEmail;
    
    // Set subject
    const subject = currentEmail.subject || 'No Subject';
    composerSubject.value = subject.startsWith('Re:') ? subject : `Re: ${subject}`;
    
    // Set body with quoted text (signature will be inserted a bit down)
    const quotedText = formatQuotedText(currentEmail);
    setBodyContent(composerBody, `<br><br>${escapeHtml(quotedText)}`);
    
    // Insert signature (will appear a bit down, not at the very top)
    insertSignatureIntoBody('reply'); // Don't await - let it load in background
    
    // Clear attachments
    composerAttachments = [];
    updateAttachmentPreview();
    
    // Show composer (AI reply section stays visible in footer)
    composerSection.style.display = 'block';
    
    // Focus on body
    composerBody.focus();
}

// Open reply all composer
async function openReplyAllComposer() {
    if (!currentEmail) {
        showAlert('error', 'No email selected');
        return;
    }
    
    // Reset sending flag when opening reply all composer
    isSendingEmail = false;
    
    // Reset send button state (in case it was disabled from previous send)
    resetSendButtonState();
    
    // Clear draft state for new compose
    clearDraftState();
    
    composerMode = 'reply-all';
    const composerSection = document.getElementById('composerSection');
    const composerTitle = document.getElementById('composerTitle');
    const composerTo = document.getElementById('composerTo');
    const composerCc = document.getElementById('composerCc');
    const composerSubject = document.getElementById('composerSubject');
    const composerBody = document.getElementById('composerBody');
    const ccBccFields = document.getElementById('ccBccFields');
    
    // Set title
    composerTitle.textContent = 'Reply All';
    
    // Extract email from sender
    const senderEmail = extractEmail(currentEmail.from || '');
    composerTo.value = senderEmail;
    
    // Show CC/BCC fields
    ccBccFields.style.display = 'flex';
    
    // Extract all recipients for CC (excluding current user)
    const toEmails = extractAllEmails(currentEmail.to || '');
    const ccEmails = extractAllEmails(currentEmail.cc || '');
    const allRecipients = [...toEmails, ...ccEmails].filter(email => email !== senderEmail);
    composerCc.value = allRecipients.join(', ');
    
    // Set subject
    const subject = currentEmail.subject || 'No Subject';
    composerSubject.value = subject.startsWith('Re:') ? subject : `Re: ${subject}`;
    
    // Set body with quoted text (signature will be inserted a bit down)
    const quotedText = formatQuotedText(currentEmail);
    setBodyContent(composerBody, `<br><br>${escapeHtml(quotedText)}`);
    
    // Insert signature (will appear a bit down, not at the very top)
    insertSignatureIntoBody('reply'); // Don't await - let it load in background
    
    // Clear attachments
    composerAttachments = [];
    updateAttachmentPreview();
    
    // Show composer (AI reply section stays visible in footer)
    composerSection.style.display = 'block';
    
    // Focus on body
    composerBody.focus();
}

// Open forward composer
function openForwardComposer() {
    if (!currentEmail) {
        showAlert('error', 'No email selected');
        return;
    }

    // Clear draft state for new compose
    clearDraftState();

    composerMode = 'forward';
    const composerSection = document.getElementById('composerSection');
    const composerTitle = document.getElementById('composerTitle');
    const composerTo = document.getElementById('composerTo');
    const composerSubject = document.getElementById('composerSubject');
    const composerBody = document.getElementById('composerBody');
    
    // Set title
    composerTitle.textContent = 'Forward';
    
    // Clear recipient
    composerTo.value = '';
    
    // Set subject
    const subject = currentEmail.subject || 'No Subject';
    composerSubject.value = subject.startsWith('Fwd:') ? subject : `Fwd: ${subject}`;
    
    // Set body with forwarded message
    const forwardedText = formatForwardedMessage(currentEmail);
    setBodyContent(composerBody, `<br><br>${escapeHtml(forwardedText)}`);
    
    // Include original attachments if any
    composerAttachments = [];
    if (currentEmail.attachments && currentEmail.attachments.length > 0) {
        showAlert('info', 'Original attachments will be included automatically');
    }
    updateAttachmentPreview();
    
    // Show composer (AI reply section stays visible in footer)
    composerSection.style.display = 'block';
    
    // Focus on TO field
    composerTo.focus();
}

// Helper functions
function extractEmail(emailString) {
    if (!emailString) return '';
    const match = emailString.match(/<(.+?)>/);
    return match ? match[1] : emailString.split('@')[0].includes(' ') ? '' : emailString;
}

function extractAllEmails(emailString) {
    if (!emailString) return [];
    const emails = [];
    const parts = emailString.split(',');
    parts.forEach(part => {
        const email = extractEmail(part.trim());
        if (email) emails.push(email);
    });
    return emails;
}

function formatQuotedText(email) {
    const sender = email.from || 'Unknown';
    const date = email.date ? new Date(parseInt(email.date)).toLocaleString() : '';
    const body = email.body || email.snippet || '';
    
    return `---------- Original Message ----------
From: ${sender}
Date: ${date}
Subject: ${email.subject || 'No Subject'}

${body}`;
}

function formatForwardedMessage(email) {
    const sender = email.from || 'Unknown';
    const date = email.date ? new Date(parseInt(email.date)).toLocaleString() : '';
    const to = email.to || '';
    const body = email.body || email.snippet || '';
    
    return `---------- Forwarded message ---------
From: ${sender}
Date: ${date}
Subject: ${email.subject || 'No Subject'}
To: ${to}

${body}`;
}

function toggleCCBCC() {
    const ccBccFields = document.getElementById('ccBccFields');
    ccBccFields.style.display = ccBccFields.style.display === 'none' ? 'flex' : 'none';
}

function closeComposer() {
    document.getElementById('composerSection').style.display = 'none';
    document.getElementById('ccBccFields').style.display = 'none';
    composerAttachments = [];
    // Clear composer fields when closing
    clearComposerFields();
    // Clear draft state (don't delete draft, user might want to continue later)
    clearDraftState();
    // Reset sending flag when closing composer
    isSendingEmail = false;
    // Reset send button state
    resetSendButtonState();
}

function clearComposer() {
    // Clear composer section and fields
    document.getElementById('composerSection').style.display = 'none';
    document.getElementById('ccBccFields').style.display = 'none';
    clearComposerFields();
}

function clearComposerFields() {
    // Clear all composer input fields
    const composerTo = document.getElementById('composerTo');
    const composerCc = document.getElementById('composerCc');
    const composerBcc = document.getElementById('composerBcc');
    const composerSubject = document.getElementById('composerSubject');
    const composerBody = document.getElementById('composerBody');
    
    if (composerTo) composerTo.value = '';
    if (composerCc) composerCc.value = '';
    if (composerBcc) composerBcc.value = '';
    if (composerSubject) composerSubject.value = '';
    if (composerBody) setBodyContent(composerBody, '');
    
    // Clear attachments
    composerAttachments = [];
    updateAttachmentPreview();
}

function applyFormatting(command) {
    const textarea = document.getElementById('composerBody');
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selectedText = textarea.value.substring(start, end);
    
    if (!selectedText) {
        showAlert('info', 'Please select text to format');
        return;
    }
    
    let formattedText = selectedText;
    switch(command) {
        case 'bold':
            formattedText = `**${selectedText}**`;
            break;
        case 'italic':
            formattedText = `*${selectedText}*`;
            break;
        case 'underline':
            formattedText = `__${selectedText}__`;
            break;
    }
    
    textarea.value = textarea.value.substring(0, start) + formattedText + textarea.value.substring(end);
    textarea.focus();
    textarea.setSelectionRange(start, start + formattedText.length);
}

function handleAttachmentUpload(event) {
    const files = event.target.files;
    if (!files || files.length === 0) return;
    
    Array.from(files).forEach(file => {
        // Convert file to base64
        const reader = new FileReader();
        reader.onload = (e) => {
            composerAttachments.push({
                filename: file.name,
                data: e.target.result.split(',')[1], // Remove data:mime;base64, prefix
                size: file.size,
                type: file.type
            });
            updateAttachmentPreview();
        };
        reader.readAsDataURL(file);
    });
    
    // Clear input
    event.target.value = '';
}

function updateAttachmentPreview() {
    const previewList = document.getElementById('attachmentPreviewList');
    if (composerAttachments.length === 0) {
        previewList.innerHTML = '';
        return;
    }
    
    previewList.innerHTML = composerAttachments.map((att, index) => `
        <div class="attachment-preview">
            <div class="attachment-preview-icon">📎</div>
            <div class="attachment-preview-info">
                <div class="attachment-preview-name">${escapeHtml(att.filename)}</div>
                <div class="attachment-preview-size">${formatFileSize(att.size)}</div>
            </div>
            <div class="attachment-preview-remove" onclick="removeAttachment(${index})">&times;</div>
        </div>
    `).join('');
}

function removeAttachment(index) {
    composerAttachments.splice(index, 1);
    updateAttachmentPreview();
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// Send reply
async function sendReply() {
    if (!currentEmail || !currentReply) return;
    
    // Confirm before sending
    if (!confirm('Are you sure you want to send this reply?')) {
        return;
    }
    
    const replyActions = document.getElementById('replyActions');
    const buttons = replyActions.querySelectorAll('.btn');
    buttons.forEach(btn => btn.disabled = true);
    
    try {
        const response = await fetch('/api/send-reply', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                email_id: currentEmail.id,
                to: currentEmail.from,
                subject: currentEmail.subject,
                body: currentReply,
                thread_id: currentEmail.thread_id
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showAlert('success', 'Reply sent successfully! ✓');
            
            // Remove email from list
            allEmails = allEmails.filter(e => e.id !== currentEmail.id);
            applyFilters(); // Apply filters including search
            const emailCountEl = document.getElementById('emailCount');
            if (emailCountEl) {
                const searchText = searchQuery ? ` (${filteredEmails.length} found)` : '';
                emailCountEl.textContent = `${allEmails.length} email${allEmails.length !== 1 ? 's' : ''} found${searchText}`;
            }
            
            // Reload deals if on Deal Flow tab
            if (currentTab === 'deal-flow') {
                loadDeals();
            }
            
            // Close modal after a short delay
            setTimeout(() => {
                closeModal();
            }, 1500);
        } else {
            showAlert('error', data.error || 'Failed to send reply');
            buttons.forEach(btn => btn.disabled = false);
        }
    } catch (error) {
        console.error('Error sending reply:', error);
        showAlert('error', 'Error sending reply: ' + error.message);
        buttons.forEach(btn => btn.disabled = false);
    }
}

// Mark email as read
async function markAsRead() {
    if (!currentEmail) return;
    
    if (!confirm('Mark this email as read without replying?')) {
        return;
    }
    
    try {
        const response = await fetch('/api/mark-read', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                email_id: currentEmail.id
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showAlert('success', 'Email marked as read');
            
            // Remove email from list
            allEmails = allEmails.filter(e => e.id !== currentEmail.id);
            applyFilters(); // Apply filters including search
            const emailCountEl = document.getElementById('emailCount');
            if (emailCountEl) {
                const searchText = searchQuery ? ` (${filteredEmails.length} found)` : '';
                emailCountEl.textContent = `${allEmails.length} email${allEmails.length !== 1 ? 's' : ''} found${searchText}`;
            }
            
            // Reload deals if on Deal Flow tab
            if (currentTab === 'deal-flow') {
                loadDeals();
            }
            
            closeModal();
        } else {
            showAlert('error', data.error || 'Failed to mark as read');
        }
    } catch (error) {
        console.error('Error marking as read:', error);
        showAlert('error', 'Error: ' + error.message);
    }
}

// Show alert message
function showAlert(type, message) {
    // Create alert element
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.textContent = message;
    alert.style.position = 'fixed';
    alert.style.top = '20px';
    alert.style.right = '20px';
    alert.style.zIndex = '9999';
    alert.style.maxWidth = '400px';
    alert.style.animation = 'slideIn 0.3s ease';
    
    document.body.appendChild(alert);
    
    // Remove after 5 seconds
    setTimeout(() => {
        alert.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => {
            document.body.removeChild(alert);
        }, 300);
    }, 5000);
}

// Mark email as read (sync with Gmail)
async function markEmailAsRead(messageId, threadId) {
    try {
        console.log(`📧 Marking email ${messageId} as read (syncing with Gmail...)`);
        const response = await fetch(`/api/email/${messageId}/mark-read`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        if (data.success) {
            // Update local email state
            updateEmailReadStatus(messageId, threadId, true);
            console.log('✅ Email marked as read in Gmail and local cache');
        } else {
            console.error('❌ Failed to mark email as read in Gmail:', data.error);
        }
    } catch (error) {
        console.error('❌ Error marking email as read:', error);
    }
}

// Mark email as unread (sync with Gmail)
async function markEmailAsUnread(messageId, threadId) {
    try {
        console.log(`📧 Marking email ${messageId} as unread`);
        const response = await fetch(`/api/email/${messageId}/mark-unread`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        if (data.success) {
            // Update local email state
            updateEmailReadStatus(messageId, threadId, false);
            showToast('Marked as unread', 'success');
            console.log('✅ Email marked as unread');
        } else {
            showToast('Failed to mark as unread', 'error');
        }
    } catch (error) {
        console.error('Error marking email as unread:', error);
        showToast('Error marking as unread', 'error');
    }
}

// Update email read status in local cache
function updateEmailReadStatus(messageId, threadId, isRead) {
    console.log(`🔄 Updating email read status: messageId=${messageId}, threadId=${threadId}, isRead=${isRead}`);
    
    let updatedCount = 0;
    
    // Helper function to update email object
    const updateEmail = (email) => {
        email.is_read = isRead;
        
        // Also update label_ids to match
        if (email.label_ids) {
            if (isRead) {
                // Remove UNREAD label
                email.label_ids = email.label_ids.filter(label => label !== 'UNREAD');
            } else {
                // Add UNREAD label if not present
                if (!email.label_ids.includes('UNREAD')) {
                    email.label_ids.push('UNREAD');
                }
            }
        } else if (!isRead) {
            // If no label_ids array exists and marking as unread, create one
            email.label_ids = ['UNREAD'];
        }
    };
    
    // Update in allEmails (search by both messageId and threadId)
    allEmails.forEach(email => {
        if (email.id === messageId || email.message_id === messageId || email.thread_id === threadId) {
            updateEmail(email);
            updatedCount++;
            console.log(`  ✓ Updated in allEmails: ${email.subject?.substring(0, 50)}`);
        }
    });
    
    // Update in emailCache
    if (emailCache && emailCache.data) {
        emailCache.data.forEach(email => {
            if (email.id === messageId || email.message_id === messageId || email.thread_id === threadId) {
                updateEmail(email);
                updatedCount++;
                console.log(`  ✓ Updated in emailCache: ${email.subject?.substring(0, 50)}`);
            }
        });
        saveEmailCacheToStorage();
    }
    
    // Update in filteredEmails
    filteredEmails.forEach(email => {
        if (email.id === messageId || email.message_id === messageId || email.thread_id === threadId) {
            updateEmail(email);
            updatedCount++;
            console.log(`  ✓ Updated in filteredEmails: ${email.subject?.substring(0, 50)}`);
        }
    });
    
    console.log(`✅ Updated ${updatedCount} email(s) to ${isRead ? 'read' : 'unread'}`);
    
    // Refresh display to show updated read/unread styling
    updatePagination(); // Use updatePagination to preserve pagination
    
    // Update unread counts
    updateSidebarUnreadCounts();
}

// Modern toast notification (Superhuman style) - shows for 2 seconds
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `modern-toast modern-toast-${type}`;
    
    // Add icon based on type
    let icon = '';
    if (type === 'success') {
        icon = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>';
    } else if (type === 'error') {
        icon = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>';
    } else if (type === 'info') {
        icon = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>';
    }
    
    toast.innerHTML = `
        <div class="toast-icon">${icon}</div>
        <div class="toast-message">${message}</div>
    `;
    
    document.body.appendChild(toast);
    
    // Trigger animation
    setTimeout(() => toast.classList.add('show'), 10);
    
    // Remove after 2 seconds
    setTimeout(() => {
        toast.classList.remove('show');
        toast.classList.add('hide');
        setTimeout(() => {
            if (document.body.contains(toast)) {
                document.body.removeChild(toast);
            }
        }, 300);
    }, 2000);
}

// Add animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// Utility function to escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Decode HTML entities (like &#39; -> ', &quot; -> ", etc.)
function decodeHtmlEntities(text) {
    if (!text) return '';
    // Create a temporary element, set innerHTML (which decodes entities), then read textContent
    const div = document.createElement('div');
    div.innerHTML = text;
    return div.textContent || div.innerText || '';
}


// Compose email attachment storage
let composeAttachments = [];

// Compose email functions
async function openComposeModal() {
    document.getElementById('composeModal').style.display = 'flex';
    // Clear previous values
    document.getElementById('composeTo').value = '';
    document.getElementById('composeCc').value = '';
    document.getElementById('composeBcc').value = '';
    document.getElementById('composeSubject').value = '';
    const composeBodyEl = document.getElementById('composeBody');
    if (composeBodyEl) setBodyContent(composeBodyEl, '');
    composeAttachments = [];
    updateAttachmentList();
    // Hide CC/BCC fields by default
    document.getElementById('composeCcBcc').style.display = 'none';
    
    // Insert signature immediately at the bottom (loads in background if not cached yet)
    insertSignatureIntoBody('compose');
    
    // Focus on To field
    setTimeout(() => {
        document.getElementById('composeTo').focus();
    }, 100);
}

function closeComposeModal() {
    document.getElementById('composeModal').style.display = 'none';
    composeAttachments = [];
    updateAttachmentList();
}

// Toggle CC/BCC fields
function toggleCcBcc() {
    const ccBccDiv = document.getElementById('composeCcBcc');
    if (ccBccDiv.style.display === 'none') {
        ccBccDiv.style.display = 'block';
    } else {
        ccBccDiv.style.display = 'none';
    }
}

// Handle attachment selection
function handleAttachmentSelection(event) {
    const files = Array.from(event.target.files);
    files.forEach(file => {
        composeAttachments.push(file);
    });
    updateAttachmentList();
    // Reset input to allow selecting same file again
    event.target.value = '';
}

// Update attachment list display
function updateAttachmentList() {
    const attachmentList = document.getElementById('attachmentList');
    if (!attachmentList) return;
    
    if (composeAttachments.length === 0) {
        attachmentList.style.display = 'none';
        attachmentList.innerHTML = '';
        return;
    }
    
    attachmentList.style.display = 'block';
    attachmentList.innerHTML = composeAttachments.map((file, index) => {
        const fileSize = formatFileSize(file.size);
        return `
            <div style="display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; background: var(--bg-secondary, #f9fafb); border-radius: 6px; margin-bottom: 6px; font-size: 13px;">
                <div style="display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0;">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0; color: var(--text-secondary, #6b7280);">
                        <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path>
                    </svg>
                    <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-primary, #111827);">${escapeHtml(file.name)}</span>
                    <span style="color: var(--text-secondary, #6b7280); font-size: 12px; flex-shrink: 0;">${fileSize}</span>
                </div>
                <button type="button" onclick="removeAttachment(${index})" style="background: none; border: none; color: var(--text-secondary, #6b7280); cursor: pointer; padding: 4px; margin-left: 8px; flex-shrink: 0;" title="Remove attachment">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </button>
            </div>
        `;
    }).join('');
}

// Remove attachment
function removeAttachment(index) {
    composeAttachments.splice(index, 1);
    updateAttachmentList();
}

// Track if email is currently being sent to prevent multiple sends
let isSendingEmail = false;

// Send composed email
async function sendComposedEmail() {
    // Prevent multiple simultaneous sends
    if (isSendingEmail) {
        console.log('⚠️ Email send already in progress, ignoring duplicate click');
        return;
    }
    
    // Set sending flag IMMEDIATELY to prevent autosave from showing "Draft saved"
    isSendingEmail = true;
    
    // Cancel any pending autosave to prevent draft creation during send
    if (autosaveTimeout) {
        clearTimeout(autosaveTimeout);
        autosaveTimeout = null;
    }
    
    // Detect which modal is active (old composer or new compose modal)
    const composerSection = document.getElementById('composerSection');
    const composeModal = document.getElementById('composeModal');
    const isOldComposer = composerSection && composerSection.style.display !== 'none';
    
    let to, cc, bcc, subject, body;
    
    if (isOldComposer) {
        // Old composer modal (used for Reply/Reply All inside email modal)
        to = document.getElementById('composerTo')?.value.trim() || '';
        cc = document.getElementById('composerCc')?.value.trim() || '';
        bcc = document.getElementById('composerBcc')?.value.trim() || '';
        subject = document.getElementById('composerSubject')?.value.trim() || '';
        const composerBodyEl = document.getElementById('composerBody');
        body = getBodyContent(composerBodyEl).trim() || '';
    } else {
        // New compose modal (standalone)
        to = document.getElementById('composeTo')?.value.trim() || '';
        cc = document.getElementById('composeCc')?.value.trim() || '';
        bcc = document.getElementById('composeBcc')?.value.trim() || '';
        subject = document.getElementById('composeSubject')?.value.trim() || '';
        const composeBodyEl = document.getElementById('composeBody');
        body = getBodyContent(composeBodyEl).trim() || '';
        
        // Ensure signature is added before sending (if not already present)
        if (body && composeBodyEl) {
            const signatureHtml = await getSignature();
            if (signatureHtml && !bodyContainsSignature(body, signatureHtml)) {
                body = body + '<br><br>' + signatureHtml;
                setBodyContent(composeBodyEl, body);
            }
        }
    }
    
    if (!to) {
        if (isOldComposer) {
            showAlert('error', 'Please enter a recipient');
        } else {
            showToast('Please enter a recipient', 'error');
        }
        return;
    }
    
    if (!body) {
        if (isOldComposer) {
            showAlert('error', 'Please enter a message');
        } else {
            showToast('Please enter a message', 'error');
        }
        return;
    }
    
    // Handle old composer (Reply/Reply All/Forward)
    if (isOldComposer) {
        // Disable send button to prevent multiple clicks
        const sendBtn = document.querySelector('#composerSection .btn-primary');
        if (sendBtn) {
    sendBtn.disabled = true;
            const originalText = sendBtn.textContent;
            sendBtn.textContent = 'Sending...';
            
            try {
                let response;
                
                if (composerMode === 'forward') {
                    // Forward email
                    response = await fetch('/api/forward-email', {
            method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                to: to,
                subject: subject,
                            body: body,
                            original_message_id: currentEmail.id,
                            include_attachments: true
            })
        });
                } else {
                    // Reply or Reply All
                    const endpoint = composerAttachments.length > 0 ? 
                        '/api/send-reply-with-attachments' : '/api/send-reply';
                    
                    const payload = {
                        email_id: currentEmail.id,
                        to: to,
                        subject: subject,
                        body: body,
                        thread_id: currentEmail.thread_id
                    };
                    
                    if (composerAttachments.length > 0) {
                        payload.attachments = composerAttachments;
                    }
                    
                    if (cc) payload.cc = cc;
                    if (bcc) payload.bcc = bcc;
                    
                    response = await fetch(endpoint, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                }
        
        const data = await response.json();
        
        if (data.success) {
                    showAlert('success', '✉️ Email sent successfully!');
                    
                    // Delete the draft if it exists (prevent it from being saved)
                    if (currentDraftId) {
                        try {
                            await fetch(`/api/drafts/${currentDraftId}`, { method: 'DELETE' });
                            console.log(`🗑️  Deleted draft ${currentDraftId} after sending`);
                            currentDraftId = null; // Clear draft ID
                        } catch (error) {
                            console.error('Error deleting draft:', error);
                        }
                    }
                    
                    // Clear draft state
                    clearDraftState();
                    
                    // Close composer and modal immediately
                    closeComposer();
                    // Small delay before closing modal to show success message
            setTimeout(() => {
                        closeModal();
                        isSendingEmail = false; // Reset flag after modal closes
                    }, 500);
                } else {
                    showAlert('error', data.error || 'Failed to send email');
                    isSendingEmail = false; // Reset flag on error
                    if (sendBtn) {
                        sendBtn.disabled = false;
                        sendBtn.textContent = originalText;
                    }
                }
            } catch (error) {
                console.error('Error sending email:', error);
                showAlert('error', 'Failed to send email: ' + error.message);
                isSendingEmail = false; // Reset flag on error
                if (sendBtn) {
                    sendBtn.disabled = false;
                    sendBtn.textContent = originalText;
                }
            }
        } else {
            // If send button not found, still try to send but reset flag on error
            try {
                let response;
                
                if (composerMode === 'forward') {
                    response = await fetch('/api/forward-email', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            to: to,
                            subject: subject,
                            body: body,
                            original_message_id: currentEmail.id,
                            include_attachments: true
                        })
                    });
                } else {
                    const endpoint = composerAttachments.length > 0 ? 
                        '/api/send-reply-with-attachments' : '/api/send-reply';
                    
                    const payload = {
                        email_id: currentEmail.id,
                        to: to,
                        subject: subject,
                        body: body,
                        thread_id: currentEmail.thread_id
                    };
                    
                    if (composerAttachments.length > 0) {
                        payload.attachments = composerAttachments;
                    }
                    
                    if (cc) payload.cc = cc;
                    if (bcc) payload.bcc = bcc;
                    
                    response = await fetch(endpoint, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                }
                
                const data = await response.json();
                
                if (data.success) {
                    showAlert('success', '✉️ Email sent successfully!');
                    
                    if (currentDraftId) {
                        try {
                            await fetch(`/api/drafts/${currentDraftId}`, { method: 'DELETE' });
                            currentDraftId = null;
                        } catch (error) {
                            console.error('Error deleting draft:', error);
                        }
                    }
                    
                    clearDraftState();
                    closeComposer();
                    setTimeout(() => {
                        closeModal();
                        isSendingEmail = false;
                    }, 500);
        } else {
                    showAlert('error', data.error || 'Failed to send email');
                    isSendingEmail = false;
        }
    } catch (error) {
                console.error('Error sending email:', error);
                showAlert('error', 'Failed to send email: ' + error.message);
                isSendingEmail = false;
            }
        }
        return;
    }
    
    // Handle new compose modal (standalone)
    isSendingEmail = true;
    
    const sendBtn = document.getElementById('sendComposeBtn');
    const sendBtnText = document.getElementById('sendComposeBtnText');
    const sendBtnSpinner = document.getElementById('sendComposeBtnSpinner');
    
    // Disable button and show loading
    if (sendBtn) {
        sendBtn.disabled = true;
        if (sendBtnText) sendBtnText.style.display = 'none';
        if (sendBtnSpinner) sendBtnSpinner.style.display = 'inline-block';
    }
    
    try {
        const formData = new FormData();
        formData.append('to', to);
        formData.append('subject', subject);
        formData.append('body', body);
        
        // Add CC and BCC if provided
        if (cc) formData.append('cc', cc);
        if (bcc) formData.append('bcc', bcc);
        
        // Add attachments
        composeAttachments.forEach(file => {
            formData.append('attachments', file);
        });
        
        const response = await fetch('/api/send-email', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast('Email sent successfully', 'success');
            // Close modal immediately after successful send
            closeComposeModal();
            isSendingEmail = false;
            
            // Refresh sent emails if on sent tab, otherwise stay on current tab
            if (currentTab === 'sent') {
                console.log('📤 [SEND] Refreshing sent emails after sending...');
                fetchSentEmails();
            }
        } else {
            showToast(data.error || 'Failed to send email', 'error');
            isSendingEmail = false;
        }
    } catch (error) {
        console.error('Error sending email:', error);
        showToast('Error sending email', 'error');
        isSendingEmail = false;
    } finally {
        // Re-enable button only if send failed
        if (!isSendingEmail && sendBtn) {
        sendBtn.disabled = false;
            if (sendBtnText) sendBtnText.style.display = 'inline';
            if (sendBtnSpinner) sendBtnSpinner.style.display = 'none';
        }
    }
}

// Keyboard shortcuts
document.addEventListener('keydown', function(event) {
    // ESC to close modal
    if (event.key === 'Escape') {
        closeModal();
        closeSignatureModal();
        closeComposeModal();
        hideContextMenu();
    }
});

// Toggle Categories Section
function toggleCategoriesSection() {
    const section = document.getElementById('categoriesSection');
    if (section) {
        section.classList.toggle('collapsed');
    }
}

// Context Menu Functions
let currentContextEmailIndex = null;

function showContextMenu(event, emailIndex) {
    event.preventDefault();
    event.stopPropagation();
    
    // Hide any existing context menu first
    hideContextMenu();
    
    currentContextEmailIndex = emailIndex;
    const contextMenu = document.getElementById('contextMenu');
    if (!contextMenu) {
        console.error('Context menu element not found');
        return;
    }
    
    // Position the menu
    contextMenu.style.display = 'block';
    contextMenu.style.left = event.pageX + 'px';
    contextMenu.style.top = event.pageY + 'px';
    
    // Prevent the menu from being positioned off-screen
    const menuRect = contextMenu.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    
    if (menuRect.right > viewportWidth) {
        contextMenu.style.left = (viewportWidth - menuRect.width - 10) + 'px';
    }
    if (menuRect.bottom > viewportHeight) {
        contextMenu.style.top = (viewportHeight - menuRect.height - 10) + 'px';
    }
    
    // Close on click outside (with a small delay to prevent immediate closing)
    setTimeout(() => {
        const clickHandler = (e) => {
            // Don't close if clicking inside the context menu
            if (!contextMenu.contains(e.target)) {
                hideContextMenu();
                document.removeEventListener('click', clickHandler);
            }
        };
        document.addEventListener('click', clickHandler, { once: true });
    }, 100);
}

function hideContextMenu() {
    const contextMenu = document.getElementById('contextMenu');
    if (contextMenu) {
        contextMenu.style.display = 'none';
    }
    // Don't clear currentContextEmailIndex immediately - keep it for menu actions
    // It will be cleared when an action is performed
}

function contextMenuReply() {
    hideContextMenu();
    if (currentContextEmailIndex !== null) {
        openEmail(currentContextEmailIndex);
        setTimeout(() => {
            openReplyComposer();
        }, 300);
    }
}

function contextMenuForward() {
    hideContextMenu();
    if (currentContextEmailIndex !== null) {
        openEmail(currentContextEmailIndex);
        setTimeout(() => {
            openForwardComposer();
        }, 300);
    }
}

function contextMenuArchive() {
    if (currentContextEmailIndex !== null) {
        // Use filteredEmails to match the displayed email list
        const email = filteredEmails[currentContextEmailIndex] || allEmails[currentContextEmailIndex];
        if (email) {
            hideContextMenu();
            archiveEmail(email.id, email.message_id || email.id);
        }
    }
    currentContextEmailIndex = null;
}

function contextMenuMarkUnread() {
    if (currentContextEmailIndex !== null) {
        // Use filteredEmails to match the displayed email list
        const email = filteredEmails[currentContextEmailIndex] || allEmails[currentContextEmailIndex];
        if (email) {
            hideContextMenu();
            markEmailAsUnread(email.id, email.thread_id);
        }
    }
    currentContextEmailIndex = null;
}

function contextMenuDelete() {
    if (currentContextEmailIndex !== null) {
        // Use filteredEmails to match the displayed email list
        const email = filteredEmails[currentContextEmailIndex] || allEmails[currentContextEmailIndex];
        if (email) {
            hideContextMenu();
            deleteEmail(email.id, email.thread_id);
        }
    }
    currentContextEmailIndex = null;
}

// Email Actions
async function archiveEmail(emailId, emailIndex) {
    // TODO: Implement archive functionality
    showAlert('info', 'Archive functionality coming soon');
}

// Older Emails Fetch Functions
let olderEmailsTaskId = null;
let olderEmailsPollInterval = null;
let olderEmailsSilentMode = false;

// Silent mode: automatically fetch older emails without showing progress bar
async function startFetchOlderEmailsSilently(maxEmails = 200) {
    // Check if we already have a task running (client-side check)
    if (olderEmailsTaskId) {
        console.log('📧 Older email fetch already in progress (client-side), skipping...');
        return;
    }
    
    // Check if we already have enough emails (200+)
    try {
        const countResponse = await fetch('/api/emails/count');
        const countData = await countResponse.json();
        const currentCount = countData.count || 0;
        console.log(`📊 Current email count: ${currentCount}`);
        
        if (countData.success && currentCount >= 200) {
            console.log(`✅ Already have ${currentCount} emails (200+), skipping older email fetch`);
            return;
        }
        
        const needed = 200 - currentCount;
        console.log(`📧 Need ${needed} more emails (have ${currentCount}, target: 200), starting fetch...`);
    } catch (error) {
        console.warn('⚠️ Could not check email count:', error);
        console.log('📧 Proceeding with older email fetch anyway...');
        // Continue anyway - might be a temporary error
    }
    
    try {
        olderEmailsSilentMode = true; // Enable silent mode
        const response = await fetch('/api/emails/fetch-older', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ max: maxEmails })
        });
        
        const data = await response.json();
        
        if (data.success) {
            olderEmailsTaskId = data.task_id;
            console.log(`📧 Started silent older email fetch (up to 200 emails), task_id: ${data.task_id}`);
            // Don't show progress bar in silent mode, just poll quietly
            startOlderEmailsPollingSilent();
        } else if (response.status === 200 && data.error === 'Already have 200+ emails') {
            // Already have enough emails - this is fine, just log it
            console.log(`✅ Already have ${data.count || 200}+ emails, no fetch needed`);
        } else if (response.status === 409 && data.error === 'Older email fetch already in progress') {
            // Task already running on server - use that task ID
            console.log('📧 Older email fetch already in progress on server, using existing task');
            olderEmailsTaskId = data.task_id;
            startOlderEmailsPollingSilent();
        } else {
            console.warn('⚠️ Failed to start older email fetch:', data.error);
        }
    } catch (error) {
        console.error('Error starting older email fetch:', error);
    }
}

// Manual trigger (with progress bar) - kept for potential future use
async function startFetchOlderEmails(maxEmails = 200) {
    try {
        const response = await fetch('/api/emails/fetch-older', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ max: maxEmails })
        });
        
        const data = await response.json();
        
        if (data.success) {
            olderEmailsTaskId = data.task_id;
            olderEmailsSilentMode = false; // Show progress bar
            showOlderEmailsProgress();
            startOlderEmailsPolling();
            showAlert('success', 'Started fetching older emails in the background');
        } else {
            showAlert('error', data.error || 'Failed to start older email fetch');
        }
    } catch (error) {
        console.error('Error starting older email fetch:', error);
        showAlert('error', 'Failed to start older email fetch');
    }
}

function showOlderEmailsProgress() {
    const progressDiv = document.getElementById('olderEmailsProgress');
    if (progressDiv) {
        progressDiv.style.display = 'block';
    }
}

function hideOlderEmailsProgress() {
    const progressDiv = document.getElementById('olderEmailsProgress');
    if (progressDiv) {
        progressDiv.style.display = 'none';
    }
}

// Silent polling (no UI updates, just logs)
function startOlderEmailsPollingSilent() {
    if (olderEmailsPollInterval) {
        clearInterval(olderEmailsPollInterval);
    }
    
    olderEmailsPollInterval = setInterval(async () => {
        if (!olderEmailsTaskId) {
            clearInterval(olderEmailsPollInterval);
            return;
        }
        
        try {
            const response = await fetch(`/api/emails/sync/status/${olderEmailsTaskId}`);
            const data = await response.json();
            
            if (data.success) {
                // Log all status updates for debugging
                if (data.status === 'PENDING') {
                    console.log(`⏳ Older email fetch task ${olderEmailsTaskId} is PENDING (waiting for worker)...`);
                } else if (data.status === 'PROGRESS') {
                    const fetched = data.fetched || data.progress || 0;
                    const classified = data.classified || 0;
                    const total = data.total || 200;
                    const statusMsg = data.message || data.status;
                    console.log(`📧 Older emails: ${statusMsg} - ${fetched} fetched, ${classified} classified / ${total}`);
                } else if (data.status === 'SUCCESS' || data.status === 'FAILURE') {
                    clearInterval(olderEmailsPollInterval);
                    olderEmailsTaskId = null;
                    olderEmailsSilentMode = false;
                    
                    if (data.status === 'SUCCESS') {
                        console.log(`✅ Older email fetch complete: ${data.emails_classified || 0} emails classified`);
                        // Silently refresh email list in background
                        setTimeout(() => {
                            loadEmailsFromDatabase();
                        }, 1000);
                    } else {
                        console.warn(`⚠️ Older email fetch failed: ${data.error || 'Unknown error'}`);
                    }
                }
            } else {
                console.error(`❌ Error polling older emails status: ${data.error || 'Unknown error'}`);
            }
        } catch (error) {
            console.error('Error polling older emails status:', error);
        }
    }, 5000); // Poll every 5 seconds in silent mode (less frequent)
}

// Manual polling (with UI updates)
function startOlderEmailsPolling() {
    if (olderEmailsPollInterval) {
        clearInterval(olderEmailsPollInterval);
    }
    
    olderEmailsPollInterval = setInterval(async () => {
        if (!olderEmailsTaskId) {
            clearInterval(olderEmailsPollInterval);
            return;
        }
        
        try {
            const response = await fetch(`/api/emails/sync/status/${olderEmailsTaskId}`);
            const data = await response.json();
            
            if (data.success) {
                updateOlderEmailsProgress(data);
                
                if (data.status === 'SUCCESS' || data.status === 'FAILURE') {
                    clearInterval(olderEmailsPollInterval);
                    olderEmailsTaskId = null;
                    olderEmailsSilentMode = false;
                    
                    if (data.status === 'SUCCESS') {
                        setTimeout(() => {
                            hideOlderEmailsProgress();
                            showAlert('success', `Successfully fetched and classified ${data.emails_classified || 0} older emails`);
                            // Refresh email list
                            loadEmailsFromDatabase();
                        }, 2000);
                    } else {
                        hideOlderEmailsProgress();
                        showAlert('error', data.error || 'Failed to fetch older emails');
                    }
                }
            } else {
                console.error('Error polling older emails status:', data.error);
            }
        } catch (error) {
            console.error('Error polling older emails status:', error);
        }
    }, 2000); // Poll every 2 seconds
}

function updateOlderEmailsProgress(data) {
    const progressBar = document.getElementById('olderEmailsProgressBar');
    const fetchedSpan = document.getElementById('olderEmailsFetched');
    const classifiedSpan = document.getElementById('olderEmailsClassified');
    const totalSpan = document.getElementById('olderEmailsTotal');
    
    if (progressBar) {
        const total = data.total || 200;
        const progress = data.fetched || data.progress || 0;
        const percentage = total > 0 ? (progress / total) * 100 : 0;
        progressBar.style.width = `${percentage}%`;
    }
    
    if (fetchedSpan) {
        fetchedSpan.textContent = data.fetched || data.progress || 0;
    }
    
    if (classifiedSpan) {
        classifiedSpan.textContent = data.classified || 0;
    }
    
    if (totalSpan) {
        totalSpan.textContent = data.total || 200;
    }
}

function stopOlderEmailsFetch() {
    if (olderEmailsPollInterval) {
        clearInterval(olderEmailsPollInterval);
        olderEmailsPollInterval = null;
    }
    
    olderEmailsTaskId = null;
    hideOlderEmailsProgress();
    showAlert('info', 'Stopped fetching older emails');
}

// Add button to trigger older email fetch (can be called from console or added to UI)
// Example: startFetchOlderEmails(200)

// ==================== SETTINGS MODAL ====================

function switchSettingsTab(tabName) {
    // Hide all tab contents
    document.querySelectorAll('.settings-tab-content').forEach(content => {
        content.classList.remove('active');
        content.style.display = 'none';
    });
    
    // Remove active class from all tabs (using correct selector)
    document.querySelectorAll('.modern-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Show selected tab content
    const content = document.getElementById(`settings-${tabName}`);
    if (content) {
        content.classList.add('active');
        content.style.display = 'block';
    }
    
    // Activate selected tab
    const tab = document.getElementById(`tab-${tabName}`);
    if (tab) {
        tab.classList.add('active');
    }
    
    // Show/hide save button based on tab
    const saveBtn = document.getElementById('saveSettingsBtn');
    if (saveBtn) {
        // Show save button for WhatsApp and User tabs (editable)
        const editableTabs = ['whatsapp', 'user'];
        saveBtn.style.display = editableTabs.includes(tabName) ? 'block' : 'none';
    }
    
    // Load signatures when Gmail tab is opened
    if (tabName === 'gmail') {
        loadSignaturesInSettings();
    }
}

async function openSettingsModal() {
    const modal = document.getElementById('settingsModal');
    if (!modal) return;
    
    modal.style.display = 'flex';
    
    // Reset to WhatsApp tab
    switchSettingsTab('whatsapp');
    
    // Load current WhatsApp settings
    try {
        const response = await fetch('/api/whatsapp/settings');
        const data = await response.json();
        
        if (data.success) {
            const enabledCheckbox = document.getElementById('whatsappEnabled');
            const numberInput = document.getElementById('whatsappNumber');
            if (enabledCheckbox) enabledCheckbox.checked = data.whatsapp_enabled || false;
            if (numberInput) numberInput.value = data.whatsapp_number || '';
            
            // Update WhatsApp status badge
            const statusBadge = document.getElementById('whatsappStatusBadge');
            if (statusBadge) {
                if (data.whatsapp_enabled && data.whatsapp_number) {
                    statusBadge.textContent = `Enabled (${data.whatsapp_number})`;
                    statusBadge.style.color = '#10b981';
                    statusBadge.parentElement.style.background = '#ECFDF5';
                } else {
                    statusBadge.textContent = 'Not configured';
                    statusBadge.style.color = '#6B7280';
                    statusBadge.parentElement.style.background = '#F3F4F6';
                }
            }
        }
    } catch (error) {
        console.error('Error loading WhatsApp settings:', error);
        showAlert('error', 'Failed to load settings');
    }
    
    // Load user profile
    try {
        const profileResponse = await fetch('/api/user/profile');
        const profileData = await profileResponse.json();
        
        if (profileData.success) {
            const fullNameInput = document.getElementById('userFullName');
            if (fullNameInput && profileData.full_name) {
                fullNameInput.value = profileData.full_name;
            }
        }
    } catch (error) {
        console.error('Error loading user profile:', error);
    }
}

function disconnectGmail() {
    if (confirm('Are you sure you want to disconnect your Gmail account? This will stop all email processing.')) {
        fetch('/disconnect-gmail', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => {
            if (response.redirected) {
                window.location.href = response.url;
            } else {
                return response.json();
            }
        })
        .then(data => {
            if (data && data.success) {
                showAlert('success', 'Gmail disconnected successfully');
                setTimeout(() => {
                    window.location.reload();
                }, 1500);
            } else if (data) {
                showAlert('error', data.error || 'Failed to disconnect Gmail');
            }
        })
        .catch(error => {
            console.error('Error disconnecting Gmail:', error);
            showAlert('error', 'Error disconnecting Gmail');
        });
    }
}

async function saveAllSettings() {
    // Fixed: use '.modern-tab.active' instead of '.settings-tab.active'
    const activeTab = document.querySelector('.modern-tab.active');
    
    if (!activeTab) {
        console.error('❌ No active tab found when saving settings');
        return;
    }
    
    const tabName = activeTab.id.replace('tab-', '');
    console.log(`💾 Saving settings for tab: ${tabName}`);
    
    if (tabName === 'whatsapp') {
        await saveWhatsAppSettings();
    } else if (tabName === 'user') {
        await saveUserProfile();
    } else if (tabName === 'gmail') {
        console.log('ℹ️  Gmail tab has no saveable settings (connection managed separately)');
    }
}

async function saveUserProfile() {
    const fullNameInput = document.getElementById('userFullName');
    if (!fullNameInput) return;
    
    const fullName = fullNameInput.value.trim();
    const statusDiv = document.getElementById('userStatus');
    const saveBtn = document.getElementById('saveSettingsBtn');
    
    // Show loading state
    let originalText = 'Save Settings';
    if (saveBtn) {
        originalText = saveBtn.textContent;
        saveBtn.textContent = 'Saving...';
        saveBtn.disabled = true;
    }
    if (statusDiv) {
        statusDiv.style.display = 'none';
    }
    
    try {
        const response = await fetch('/api/user/profile', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                full_name: fullName
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast('Profile updated successfully', 'success');
            console.log('✅ Profile updated successfully');
        } else {
            showToast(data.error || 'Failed to update profile', 'error');
            console.error('❌ Failed to update profile:', data.error);
        }
    } catch (error) {
        console.error('Error saving user profile:', error);
        showToast('Error updating profile. Please try again.', 'error');
    } finally {
        if (saveBtn) {
            saveBtn.textContent = originalText;
            saveBtn.disabled = false;
        }
    }
}

function closeSettingsModal() {
    const modal = document.getElementById('settingsModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

async function saveWhatsAppSettings() {
    const enabled = document.getElementById('whatsappEnabled').checked;
    const number = document.getElementById('whatsappNumber').value.trim();
    const statusDiv = document.getElementById('whatsappStatus');
    const saveBtn = document.getElementById('saveSettingsBtn');
    
    // Validate phone number if enabled
    if (enabled && number) {
        if (!number.startsWith('+')) {
            if (statusDiv) {
                statusDiv.style.display = 'block';
                statusDiv.style.background = '#fee';
                statusDiv.style.color = '#c33';
                statusDiv.style.border = '1px solid #fcc';
                statusDiv.textContent = '❌ Phone number must start with + (e.g., +1234567890)';
            }
            return;
        }
        
        // Basic validation: + followed by 10-15 digits
        if (!/^\+[1-9]\d{9,14}$/.test(number)) {
            if (statusDiv) {
                statusDiv.style.display = 'block';
                statusDiv.style.background = '#fee';
                statusDiv.style.color = '#c33';
                statusDiv.style.border = '1px solid #fcc';
                statusDiv.textContent = '❌ Invalid phone number format. Use: +1234567890';
            }
            return;
        }
    }
    
    // Show loading state
    let originalText = 'Save Settings';
    if (saveBtn) {
        originalText = saveBtn.textContent;
        saveBtn.textContent = 'Saving...';
        saveBtn.disabled = true;
    }
    if (statusDiv) {
        statusDiv.style.display = 'none';
    }
    
    console.log('💾 Saving WhatsApp settings:', { enabled, number: number ? number.substring(0, 8) + '...' : 'none' });
    
    try {
        const response = await fetch('/api/whatsapp/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                enabled: enabled,
                number: number
            })
        });
        
        console.log('📡 Response status:', response.status);
        const data = await response.json();
        console.log('📦 Response data:', data);
        
        if (data.success) {
            // Show modern toast notification
            showToast('WhatsApp settings saved successfully', 'success');
            
            // Update WhatsApp status badge
            const statusBadge = document.getElementById('whatsappStatusBadge');
            if (statusBadge) {
                if (enabled && number) {
                    statusBadge.textContent = `Enabled (${number})`;
                    statusBadge.style.color = '#10b981';
                    statusBadge.parentElement.style.background = '#ECFDF5';
                } else {
                    statusBadge.textContent = 'Not configured';
                    statusBadge.style.color = '#6B7280';
                    statusBadge.parentElement.style.background = '#F3F4F6';
                }
            }
            
            console.log('✅ WhatsApp settings saved successfully');
            
            // Auto-close after 1.5 seconds
            setTimeout(() => {
                closeSettingsModal();
            }, 1500);
        } else {
            console.error('❌ Failed to save:', data.error);
            showToast(data.error || 'Failed to save settings', 'error');
        }
    } catch (error) {
        console.error('❌ Error saving WhatsApp settings:', error);
        showToast('Error saving settings. Please try again.', 'error');
    } finally {
        if (saveBtn) {
            saveBtn.textContent = originalText;
            saveBtn.disabled = false;
        }
    }
}

// Close modal when clicking outside
document.addEventListener('click', function(event) {
    const modal = document.getElementById('settingsModal');
    if (modal && event.target === modal) {
        closeSettingsModal();
    }
});

// Close modal on Escape key
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        const modal = document.getElementById('settingsModal');
        if (modal && modal.style.display === 'flex') {
            closeSettingsModal();
        }
    }
});

// ============================================
// User Dropdown Functions
// ============================================

function toggleUserDropdown() {
    const dropdown = document.getElementById('userDropdownMenu');
    if (!dropdown) return;
    
    if (dropdown.style.display === 'none' || !dropdown.style.display) {
        dropdown.style.display = 'block';
    } else {
        dropdown.style.display = 'none';
    }
}

// SECURITY: Clear all user data before logout to prevent cross-user data leakage
function handleLogout(event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    
    console.log('🔒 Logging out - clearing ALL user data from device...');
    
    try {
        // 1. Clear ALL localStorage
        console.log('🗑️  Clearing localStorage...');
        localStorage.clear();
        
        // 2. Clear ALL sessionStorage
        console.log('🗑️  Clearing sessionStorage...');
        sessionStorage.clear();
        
        // 3. Clear IndexedDB (don't wait for it - do it in background)
        try {
            if (typeof indexedDB !== 'undefined' && indexedDB.deleteDatabase) {
                console.log('🗑️  Deleting IndexedDB databases...');
                indexedDB.deleteDatabase('gmail_threads');
                indexedDB.deleteDatabase('gmail_sent_emails');
            }
        } catch (e) {
            console.warn('Could not delete IndexedDB:', e);
        }
        
        // 4. Clear in-memory caches
        try {
            if (typeof emailCache !== 'undefined') {
                emailCache.data = [];
                emailCache.timestamp = null;
            }
            if (typeof allEmails !== 'undefined') allEmails = [];
            if (typeof filteredEmails !== 'undefined') filteredEmails = [];
            if (typeof sentEmailsCache !== 'undefined') sentEmailsCache = [];
            if (typeof starredEmailsCache !== 'undefined') starredEmailsCache = [];
            if (typeof draftsCache !== 'undefined') draftsCache = [];
            if (typeof threadCacheMemory !== 'undefined' && threadCacheMemory && threadCacheMemory.clear) {
                threadCacheMemory.clear();
            }
        } catch (e) {
            console.warn('Error clearing in-memory caches:', e);
        }
        
        // 5. Clear JavaScript-accessible cookies
        try {
            document.cookie.split(";").forEach(function(c) { 
                document.cookie = c.replace(/^ +/, "").replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/"); 
            });
        } catch (e) {
            console.warn('Could not clear cookies:', e);
        }
        
        console.log('✅ All user data cleared from device');
    } catch (error) {
        console.error('Error clearing cache on logout:', error);
    }
    
    // IMMEDIATELY redirect to logout endpoint (server will clear session cookie)
    console.log('🔄 Redirecting to logout...');
    window.location.href = '/logout';
    
    // Return false to prevent any default link behavior
    return false;
}

// Close dropdown when clicking outside
document.addEventListener('click', function(event) {
    const dropdown = document.getElementById('userDropdownMenu');
    const userMenu = document.querySelector('.nav-user-menu');
    
    if (dropdown && userMenu) {
        // Check if click is outside both the dropdown and user avatar
        if (!userMenu.contains(event.target)) {
            dropdown.style.display = 'none';
        }
    }
});

// ============================================
// Delete Account Function
// ============================================

async function confirmDeleteAccount() {
    const confirmed = confirm(
        '⚠️ WARNING: This will permanently delete your account and ALL your data.\n\n' +
        'This includes:\n' +
        '- All email classifications\n' +
        '- All deal flow data\n' +
        '- All settings and preferences\n' +
        '- Gmail connection\n\n' +
        'This action CANNOT be undone.\n\n' +
        'Are you absolutely sure you want to delete your account?'
    );
    
    if (!confirmed) return;
    
    const doubleConfirm = confirm(
        '⚠️ FINAL CONFIRMATION\n\n' +
        'Type confirmation: Are you 100% sure you want to permanently delete your account and all data?\n\n' +
        'Click OK to DELETE EVERYTHING or Cancel to keep your account.'
    );
    
    if (!doubleConfirm) return;
    
    try {
        const response = await fetch('/api/user/delete', {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            showAlert('success', 'Account deleted successfully. Redirecting...');
            setTimeout(() => {
                window.location.href = '/login';
            }, 1500);
        } else {
            showAlert('error', data.error || 'Failed to delete account');
        }
    } catch (error) {
        console.error('Delete account error:', error);
        showAlert('error', 'Failed to delete account. Please try again.');
    }
}
