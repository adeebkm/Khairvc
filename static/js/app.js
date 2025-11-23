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
function getCacheKey() {
    // Try to get username from the page
    const userInfo = document.querySelector('.user-info');
    if (userInfo) {
        const text = userInfo.textContent || '';
        const match = text.match(/Welcome, (\w+)/);
        if (match) {
            return `emailCache_${match[1]}`;
        }
    }
    // Fallback to generic key
    return 'emailCache';
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
// Auto-fetch polling
let autoFetchInterval = null;
let autoFetchEnabled = false;
const AUTO_FETCH_INTERVAL = 5 * 60 * 1000; // Check every 5 minutes
let autoFetchPausedUntil = null; // Timestamp when auto-fetch should resume after rate limit

// Auto-fetch function (only fetches new emails using incremental sync)
async function autoFetchNewEmails() {
    // Don't auto-fetch if already fetching or if user is viewing an email
    if (isFetching || document.getElementById('emailModal')?.style.display === 'flex') {
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
                    allEmails = emailCache.data;
                    
                    // Apply filters and update display
                    applyFilters();
                    
                    // Show notification
                    showAlert('success', `📧 ${uniqueNewEmails.length} new email${uniqueNewEmails.length !== 1 ? 's' : ''} detected!`);
                    
                    console.log(`✅ Auto-fetch: Updated UI with ${uniqueNewEmails.length} new email(s), total: ${allEmails.length}`);
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
async function deleteEmail(messageId, threadId) {
    if (!confirm('Are you sure you want to delete this email?')) {
        return;
    }
    
    try {
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
            // Invalidate thread cache
            if (threadId) {
                await invalidateThreadCache(threadId);
            }
            
            // Remove from email list cache
            emailCache.data = emailCache.data.filter(e => e.id !== messageId);
            saveEmailCacheToStorage();
            
            // Close modal if open
            const modal = document.getElementById('emailModal');
            if (modal && modal.style.display === 'flex') {
                closeModal();
            }
            
            showAlert('success', 'Email deleted');
        } else {
            // Rollback: restore email in UI if delete failed
            if (removedEmail) {
                allEmails.splice(emailIndex, 0, removedEmail);
                applyFilters();
            }
            showAlert('error', 'Failed to delete email');
        }
    } catch (error) {
        console.error('Error deleting email:', error);
        showAlert('error', 'Error deleting email');
    }
}

// Start/stop auto-fetch polling
function toggleAutoFetch(enabled) {
    // Auto-fetch enabled - polls database for new emails synced by Pub/Sub
    // Pub/Sub syncs emails to database, but frontend needs to poll to update UI
    autoFetchEnabled = true;
    
    // Start polling every 30 seconds to check for new emails in database
    if (autoFetchInterval) {
        clearInterval(autoFetchInterval);
    }
    
    // Poll immediately, then every 30 seconds
    autoFetchNewEmails();
    autoFetchInterval = setInterval(autoFetchNewEmails, 30 * 1000); // 30 seconds
    
    console.log('✅ Auto-fetch enabled - polling database every 30 seconds for new emails synced by Pub/Sub');
    // No polling needed - Pub/Sub will trigger background sync when new emails arrive
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
async function startSetup() {
    const setupScreen = document.getElementById('setupScreen');
    const startBtn = document.getElementById('startSetupBtn');
    const progressDiv = document.getElementById('setupProgress');
    const progressBar = document.getElementById('setupProgressBar');
    const progressText = document.getElementById('setupProgressText');
    
    if (!setupScreen) return;
    
    // Hide start button, show progress
    if (startBtn) startBtn.style.display = 'none';
    if (progressDiv) progressDiv.style.display = 'block';
    
    try {
        // Start initial fetch (200 emails)
        if (progressText) progressText.textContent = 'Fetching your first 200 emails...';
        if (progressBar) progressBar.style.width = '10%';
        
        const response = await fetch('/api/setup/fetch-initial', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        
        // If setup is already complete (user has emails), skip to completion
        if (data.success && data.already_complete) {
            console.log(`✅ Setup already complete: ${data.email_count} emails found`);
            if (progressBar) progressBar.style.width = '90%';
            if (progressText) progressText.textContent = `Loading emails...`;
            
            // Mark as complete first
            await fetch('/api/setup/complete', { method: 'POST' });
            
            // Auto-setup Pub/Sub if enabled (test environment)
            try {
                const pubsubResponse = await fetch('/api/setup-pubsub', { method: 'POST' });
                const pubsubData = await pubsubResponse.json();
                if (pubsubData.success) {
                    console.log('✅ Pub/Sub watch configured automatically');
                } else if (pubsubResponse.status === 400 && pubsubData.error?.includes('not enabled')) {
                    console.log('ℹ️  Pub/Sub not enabled (production environment)');
                } else {
                    console.warn('⚠️  Pub/Sub setup failed (non-critical):', pubsubData.error);
                }
            } catch (error) {
                console.warn('⚠️  Pub/Sub setup error (non-critical):', error);
            }
            
        // Use hardcoded timer approach: random 7-10 minutes, then show inbox
        await startHardcodedTimer(progressBar, progressText, setupScreen);
        
        showAlert('success', `Setup complete! Found ${data.email_count} existing emails.`);
        return; // Exit early since setup is already complete
        } else if (data.success && data.task_id) {
            // Poll for progress
            try {
                await pollSetupProgress(data.task_id, progressBar, progressText);
            } catch (pollError) {
                console.warn('Polling failed, falling back to streaming:', pollError);
                // Fall back to streaming if polling fails
                await fetchInitialEmailsStreaming(progressBar, progressText);
            }
        } else if (data.use_streaming) {
            // Use streaming endpoint
            await fetchInitialEmailsStreaming(progressBar, progressText);
        } else {
            throw new Error(data.error || 'Failed to start setup');
        }
        
        // Keep setup screen visible until the timer completes (completeSetupAfterTimer handles the UI transition)
        await startHardcodedTimer(progressBar, progressText, setupScreen);
        return;
    } catch (error) {
        console.error('Setup error:', error);
        // Even if setup fails, try to load existing emails and mark setup as complete
        // This prevents users from being stuck on the setup screen
        try {
            // Check if we already have emails
            await loadEmailsFromDatabase();
            const emailCount = allEmails.length;
            
            if (emailCount > 0) {
                // We have emails, mark setup as complete and continue
                console.log(`✅ Found ${emailCount} existing emails, marking setup as complete`);
                await finalizeSetupStatus();
                
                // Hide setup screen
                if (setupScreen) setupScreen.style.display = 'none';
                const compactHeader = document.querySelector('.main-content > .compact-header');
                if (compactHeader) compactHeader.style.display = 'block';
                const emailList = document.getElementById('emailList');
                if (emailList) emailList.style.display = 'block';
                
                showAlert('info', `Loaded ${emailCount} existing emails. Setup can be completed later.`);
            } else {
                // No emails, show error but allow retry
                if (progressText) progressText.textContent = `Error: ${error.message}. Click "Start Setup" to retry.`;
                if (startBtn) startBtn.style.display = 'block';
                if (progressDiv) progressDiv.style.display = 'none';
            }
        } catch (loadError) {
            console.error('Error loading emails after setup failure:', loadError);
            if (progressText) progressText.textContent = `Error: ${error.message}. Click "Start Setup" to retry.`;
            if (startBtn) startBtn.style.display = 'block';
            if (progressDiv) progressDiv.style.display = 'none';
        }
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
async function startHardcodedTimer(progressBar, progressText, setupScreen) {
    const TIMER_STORAGE_KEY = 'setup_timer_state';
    
    // Check if there's an existing timer in localStorage
    let timerState = null;
    let remaining = null;
    try {
        const stored = localStorage.getItem(TIMER_STORAGE_KEY);
        if (stored) {
            timerState = JSON.parse(stored);
            const now = Date.now();
            const elapsed = Math.floor((now - timerState.startTime) / 1000);
            remaining = timerState.totalSeconds - elapsed;
            
            if (remaining > 0) {
                // Timer still active, resume from where we left off
                console.log(`⏱️ Resuming timer: ${Math.floor(remaining / 60)} minutes remaining (was ${Math.floor(timerState.totalSeconds / 60)} minutes total)`);
            } else {
                // Timer has expired, complete setup immediately
                console.log(`⏱️ Timer expired while page was closed, completing setup...`);
                localStorage.removeItem(TIMER_STORAGE_KEY);
                // Complete setup immediately
                completeSetupAfterTimer(progressBar, progressText, setupScreen);
                return;
            }
        }
    } catch (error) {
        console.warn('Error reading timer state from localStorage:', error);
        localStorage.removeItem(TIMER_STORAGE_KEY);
    }
    
    // Generate new timer if none exists, or use existing
    let totalSeconds, remainingSeconds, startTime;
    if (timerState && remaining !== null && remaining > 0) {
        // Resume existing timer
        totalSeconds = timerState.totalSeconds;
        remainingSeconds = remaining;
        startTime = timerState.startTime;
    } else {
        // Fixed 5-minute timer (300 seconds)
        const minMinutes = 5;
        totalSeconds = minMinutes * 60;  // 300 seconds
        remainingSeconds = totalSeconds;
        startTime = Date.now();
        
        // Save timer state to localStorage
        try {
            localStorage.setItem(TIMER_STORAGE_KEY, JSON.stringify({
                startTime: startTime,
                totalSeconds: totalSeconds
            }));
        } catch (error) {
            console.warn('Error saving timer state to localStorage:', error);
        }
        
        console.log(`⏱️ Starting new 5-minute timer: ${Math.floor(totalSeconds / 60)} minutes (${totalSeconds} seconds)`);
    }
    let lastUpdateTime = Date.now();
    let secondsUpdateTimeout = null;
    let isInSecondsMode = false;
    
    // Update progress bar smoothly
    const updateProgress = () => {
        const progressPercent = ((totalSeconds - remainingSeconds) / totalSeconds) * 100;
        if (progressBar) {
            progressBar.style.width = `${Math.min(progressPercent, 100)}%`;
        }
    };
    
    // Schedule next seconds update (random interval)
    const scheduleNextSecondsUpdate = () => {
        if (secondsUpdateTimeout) {
            clearTimeout(secondsUpdateTimeout);
        }
        if (remainingSeconds <= 0 || !isInSecondsMode) {
            return;
        }
        // Random interval between 3-8 seconds
        const randomInterval = Math.floor(Math.random() * 6) + 3;
        secondsUpdateTimeout = setTimeout(() => {
            if (remainingSeconds > 0 && progressText && isInSecondsMode) {
                const seconds = remainingSeconds;
                progressText.textContent = `Classifying your emails... Approximately ${seconds} second${seconds !== 1 ? 's' : ''} remaining`;
                // Schedule next update
                scheduleNextSecondsUpdate();
            }
        }, randomInterval * 1000);
    };
    
    // Motivational quotes
    const quotes = [
        "Good things take time...",
        "Excellence is not a skill, it's an attitude...",
        "Patience is the key to success...",
        "Great things never come from comfort zones...",
        "Progress, not perfection...",
        "Quality takes time...",
        "Building something amazing...",
        "The best is yet to come...",
        "Excellence requires patience...",
        "Good things come to those who wait..."
    ];
    let currentQuoteIndex = 0;
    
    // Update timer display (MM:SS format)
    const updateTimerDisplay = () => {
        const timerMinutesEl = document.getElementById('timerMinutes');
        const timerSecondsEl = document.getElementById('timerSeconds');
        
        if (timerMinutesEl && timerSecondsEl) {
            const minutes = Math.floor(remainingSeconds / 60);
            const seconds = remainingSeconds % 60;
            timerMinutesEl.textContent = String(minutes).padStart(2, '0');
            timerSecondsEl.textContent = String(seconds).padStart(2, '0');
        }
    };
    
    // Rotate motivational quotes every 8 seconds
    const rotateQuote = () => {
        const quoteEl = document.getElementById('motivationalQuote');
        if (quoteEl) {
            currentQuoteIndex = (currentQuoteIndex + 1) % quotes.length;
            quoteEl.textContent = quotes[currentQuoteIndex];
        }
    };
    let quoteInterval = setInterval(rotateQuote, 8000); // Rotate every 8 seconds
    
    // Update display text
    const updateDisplay = () => {
        // Update timer display
        updateTimerDisplay();
        
        if (!progressText) return;
        
        if (remainingSeconds >= 60) {
            // Show minutes
            const minutes = Math.ceil(remainingSeconds / 60);
            progressText.textContent = `Classifying your emails... Approximately ${minutes} minute${minutes !== 1 ? 's' : ''} remaining`;
            if (isInSecondsMode) {
                isInSecondsMode = false;
                if (secondsUpdateTimeout) {
                    clearTimeout(secondsUpdateTimeout);
                    secondsUpdateTimeout = null;
                }
            }
        } else {
            // Show seconds (update at random intervals, not continuously)
            if (!isInSecondsMode) {
                isInSecondsMode = true;
                // Initial seconds display
                const seconds = remainingSeconds;
                progressText.textContent = `Classifying your emails... Approximately ${seconds} second${seconds !== 1 ? 's' : ''} remaining`;
                // Schedule first random update
                scheduleNextSecondsUpdate();
            }
        }
    };
    
    // Initial display
    updateDisplay();
    updateProgress();
    updateTimerDisplay(); // Initial timer display
    
    // Start progressive email loading
    let emailLoadInterval = null;
    let lastEmailCount = 0;
    const startProgressiveLoading = async () => {
        // Load emails immediately
        try {
            const response = await fetch(`/api/emails?max=200&show_spam=true`);
            const data = await response.json();
            if (data.success && data.emails) {
                lastEmailCount = data.emails.length;
                console.log(`📧 Progressive loading: ${lastEmailCount} emails classified so far`);
                
                // Update progress text with email count
                if (progressText && remainingSeconds > 0) {
                    const minutes = Math.ceil(remainingSeconds / 60);
                    const timeText = remainingSeconds >= 60 ? 
                        `${minutes} minute${minutes !== 1 ? 's' : ''}` : 
                        `${remainingSeconds} second${remainingSeconds !== 1 ? 's' : ''}`;
                    progressText.textContent = `Classified ${lastEmailCount} emails... ${timeText} remaining`;
                }
            }
        } catch (error) {
            console.error('Error in progressive loading:', error);
        }
    };
    
    // Start progressive loading immediately
    startProgressiveLoading();
    
    // Poll every 15 seconds for new classified emails
    emailLoadInterval = setInterval(startProgressiveLoading, 15000);
    
    // Countdown timer
    const timerInterval = setInterval(() => {
        remainingSeconds--;
        updateProgress();
        updateTimerDisplay(); // Update timer display every second
        
        // Update display at different intervals based on time remaining
        if (remainingSeconds >= 60) {
            // Update every 30 seconds when showing minutes
            const now = Date.now();
            if (now - lastUpdateTime >= 30000) {
                updateDisplay();
                lastUpdateTime = now;
            }
        }
        // Note: seconds mode updates are handled by scheduleNextSecondsUpdate()
        
        // Save timer state to localStorage every 5 seconds (for persistence across refreshes)
        if (remainingSeconds % 5 === 0) {
            try {
                localStorage.setItem(TIMER_STORAGE_KEY, JSON.stringify({
                    startTime: startTime,
                    totalSeconds: totalSeconds
                }));
            } catch (error) {
                // Ignore localStorage errors (might be full or disabled)
            }
        }
        
        // Timer complete
        if (remainingSeconds <= 0) {
            clearInterval(timerInterval);
            if (emailLoadInterval) {
                clearInterval(emailLoadInterval);
            }
            if (secondsUpdateTimeout) {
                clearTimeout(secondsUpdateTimeout);
            }
            if (quoteInterval) {
                clearInterval(quoteInterval);
            }
            
            // Clear timer state from localStorage
            localStorage.removeItem(TIMER_STORAGE_KEY);
            
            // Complete setup (don't await - let it run asynchronously)
            completeSetupAfterTimer(progressBar, progressText, setupScreen);
        }
    }, 1000); // Update every second
}

/**
 * Complete setup after timer expires - loads emails and shows inbox
 */
async function completeSetupAfterTimer(progressBar, progressText, setupScreen) {
    // Load emails and show inbox
    console.log('⏱️ Timer complete, loading emails and showing inbox...');
    if (progressText) progressText.textContent = 'Loading your inbox...';
    if (progressBar) progressBar.style.width = '95%';
    
    // DON'T hide setup screen yet - load emails FIRST
    // Load emails from database
    try {
        console.log('📧 Loading emails from database (setup screen still visible)...');
        await loadEmailsFromDatabase();
        console.log(`📧 Loaded ${allEmails.length} emails after timer`);
        
        // If no emails loaded, wait and try again
        if (allEmails.length === 0) {
            console.warn('⚠️ No emails loaded yet, waiting 2 seconds...');
            if (progressText) progressText.textContent = 'Waiting for emails to be classified...';
            await new Promise(resolve => setTimeout(resolve, 2000));
            await loadEmailsFromDatabase();
            console.log(`📧 Second attempt: Loaded ${allEmails.length} emails`);
        }
        
        // Now that emails are loaded, hide setup screen and show inbox
        if (progressText) progressText.textContent = 'Setup complete!';
        if (progressBar) progressBar.style.width = '100%';
        
        if (setupScreen) setupScreen.style.display = 'none';
        const compactHeader = document.querySelector('.main-content > .compact-header');
        if (compactHeader) compactHeader.style.display = 'block';
        const emailListEl = document.getElementById('emailList');
        if (emailListEl) emailListEl.style.display = 'block';
        
        // Wait for DOM to update
        await new Promise(resolve => setTimeout(resolve, 100));
        
        console.log(`📧 Now displaying ${allEmails.length} emails`);
        
        // Ensure all emails have category
        allEmails.forEach(email => {
            if (!email.category && email.classification?.category) {
                email.category = email.classification.category.toLowerCase();
            } else if (!email.category) {
                email.category = 'general';
            }
        });
        
        // Force apply filters and display emails
        applyFilters();
        updatePagination();
        
        // Double-check emails are displayed
        setTimeout(() => {
            const visibleCount = emailListEl ? emailListEl.querySelectorAll('.email-item').length : 0;
            console.log(`📊 After timer: ${visibleCount} emails visible, ${allEmails.length} total, ${filteredEmails.length} filtered`);
            
            if (visibleCount === 0 && allEmails.length > 0) {
                console.warn('⚠️ Emails not visible after timer, forcing display...');
                // Ensure categories are set
                allEmails.forEach(email => {
                    if (!email.category && email.classification?.category) {
                        email.category = email.classification.category.toLowerCase();
                    } else if (!email.category) {
                        email.category = 'general';
                    }
                });
                applyFilters();
                if (filteredEmails.length > 0) {
                    displayEmails(filteredEmails.slice(0, EMAILS_PER_PAGE));
                    updatePagination();
                } else {
                    // Last resort - display all emails directly
                    displayEmails(allEmails.slice(0, EMAILS_PER_PAGE));
                    updatePagination();
                }
            }
            
            // Show success message
            if (allEmails.length > 0) {
                showAlert('success', `Setup complete! Loaded ${allEmails.length} emails.`);
            } else {
                showAlert('info', 'Setup complete! Emails are still being classified in the background. They will appear as they\'re ready.');
            }
        }, 300);
    } catch (error) {
        console.error('Error loading emails after timer:', error);
        showAlert('info', 'Setup complete! Emails are being classified in the background.');
    } finally {
        await finalizeSetupStatus();
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
    // Initialize IndexedDB thread cache and pre-fetching
    try {
        await initThreadCache();
        await cleanupOldThreads();
        initThreadPrefetching();
    } catch (error) {
        console.error('Error initializing cache:', error);
    }
    
    // Initialize sidebar state
    initSidebar();
    loadConfig();
    
    // Check if setup is needed and auto-start
    const setupScreen = document.getElementById('setupScreen');
    const urlParams = new URLSearchParams(window.location.search);
    const autoSetup = urlParams.get('auto_setup') === 'true';
    
    if (setupScreen && setupScreen.style.display !== 'none') {
        // Setup screen is visible - auto-start setup
        console.log('📋 Setup screen detected - auto-starting setup');
        if (autoSetup || !document.getElementById('startSetupBtn')) {
            // Auto-start if from signup or if no start button (auto-setup mode)
            setTimeout(() => startSetup(), 500);
        }
        return;
    }
    
    // Auto-fetch is disabled - using Pub/Sub for real-time notifications
    // Pub/Sub automatically notifies when new emails arrive
    toggleAutoFetch(false);
    
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
            displayEmails(filteredEmails);
            
            // If we're on the starred tab and unstarred, remove from view
            if (currentTab === 'starred' && !star) {
                // Remove from current view
                filteredEmails = filteredEmails.filter(e => e.id !== emailId);
                allEmails = allEmails.filter(e => e.id !== emailId);
                emailCache.data = emailCache.data.filter(e => e.id !== emailId);
                saveEmailCacheToStorage();
                displayEmails(filteredEmails);
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

// Cache for sent, starred, and drafts emails
let sentEmailsCache = [];
let starredEmailsCache = [];
let draftsCache = [];

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
        loadDeals();
    } else if (tabName === 'sent') {
        emailList.style.display = 'block';
        dealFlowTable.style.display = 'none';
        
        // Show cached data immediately if available
        if (sentEmailsCache.length > 0) {
            allEmails = sentEmailsCache;
            applyFilters();
            const emailCountEl = document.getElementById('emailCount');
            if (emailCountEl) {
                const searchText = searchQuery ? ` (${filteredEmails.length} found)` : '';
                emailCountEl.textContent = `${sentEmailsCache.length} sent email${sentEmailsCache.length !== 1 ? 's' : ''} (cached)${searchText}`;
            }
        } else {
            // Show empty state immediately
            displayEmails([]);
        }
        
        // Fetch fresh data in background
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
            // Show empty state immediately
            displayEmails([]);
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
        
        // Show cached data immediately if available
        if (draftsCache.length > 0) {
            allEmails = draftsCache;
            applyFilters();
            const emailCountEl = document.getElementById('emailCount');
            if (emailCountEl) {
                const searchText = searchQuery ? ` (${filteredEmails.length} found)` : '';
                emailCountEl.textContent = `${draftsCache.length} draft${draftsCache.length !== 1 ? 's' : ''} (cached)${searchText}`;
            }
        } else {
            // Show empty state immediately
            displayEmails([]);
        }
        
        // Fetch fresh data in background
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
            }
        } else {
            console.error('Error fetching starred emails:', data.error);
            if (currentTab === 'starred') {
                displayEmails([]);
            }
        }
    } catch (error) {
        console.error('Error fetching starred emails:', error);
        if (currentTab === 'starred') {
            displayEmails([]);
        }
    }
}

// Fetch sent emails
async function fetchSentEmails() {
    try {
        const response = await fetch(`/api/sent-emails?max=100`);
        const data = await response.json();
        
        if (data.success) {
            // Format sent emails similar to received emails
            const sentEmails = data.emails.map(email => ({
                ...email,
                classification: { category: 'SENT' },
                is_sent: true
            }));
            
            // Update cache
            sentEmailsCache = sentEmails;
            
            // Only update UI if we're still on the sent tab
            if (currentTab === 'sent') {
                allEmails = sentEmails;
                applyFilters(); // Apply filters including search
                
                const emailCountEl = document.getElementById('emailCount');
                if (emailCountEl) {
                    const searchText = searchQuery ? ` (${filteredEmails.length} found)` : '';
                    emailCountEl.textContent = `${sentEmails.length} sent email${sentEmails.length !== 1 ? 's' : ''}${searchText}`;
                }
            }
        } else {
            console.error('Error fetching sent emails:', data.error);
            if (currentTab === 'sent') {
                displayEmails([]);
            }
        }
    } catch (error) {
        console.error('Error fetching sent emails:', error);
        if (currentTab === 'sent') {
            displayEmails([]);
        }
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
            
            // Update cache
            draftsCache = drafts;
            
            // Only update UI if we're still on the drafts tab
            if (currentTab === 'drafts') {
                allEmails = drafts;
                applyFilters(); // Apply filters including search
                
                const emailCountEl = document.getElementById('emailCount');
                if (emailCountEl) {
                    const searchText = searchQuery ? ` (${filteredEmails.length} found)` : '';
                    emailCountEl.textContent = `${drafts.length} draft${drafts.length !== 1 ? 's' : ''}${searchText}`;
                }
            }
        } else {
            console.error('Error fetching drafts:', data.error);
            if (currentTab === 'drafts') {
                displayEmails([]);
            }
        }
    } catch (error) {
        console.error('Error fetching drafts:', error);
        if (currentTab === 'drafts') {
            displayEmails([]);
        }
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
    
    let filtered = allEmails;
    
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
    } else if (currentTab === 'sent') {
        filtered = allEmails.filter(e => e.from_me === true);
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
    try {
        const response = await fetch('/api/deals');
        const data = await response.json();
        
        if (data.success) {
            displayDeals(data.deals);
        } else {
            console.error('Error loading deals:', data.error);
        }
    } catch (error) {
        console.error('Error loading deals:', error);
    }
}

// Display Deal Flow deals in table
function displayDeals(deals) {
    const tbody = document.getElementById('dealFlowBody');
    
    if (deals.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="empty-state">No deals found</td></tr>';
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
                <td>${stateBadge}</td>
                <td>${deckLink}</td>
                <td class="basics">${basics}</td>
                <td>
                    <div class="overlap-info">${escapeHtml(overlapText)}</div>
                </td>
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
    emailList.innerHTML = emails.map((email, index) => {
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
        const isUnread = !email.is_read || false;
        const unreadClass = isUnread ? 'unread' : '';
        const attachmentClass = hasAttachments ? 'has-attachment' : '';
        
        return `
            <div class="email-card ${unreadClass} ${attachmentClass}" 
                 onclick="openEmail(${index})" 
                 oncontextmenu="event.preventDefault(); showContextMenu(event, ${index});"
                 data-email-index="${index}"
                 data-thread-id="${escapeHtml(email.thread_id || '')}">
                <div class="email-row">
                    <div class="email-star" onclick="event.stopPropagation(); toggleStar('${email.id}', ${isStarred}, ${index})" title="${isStarred ? 'Unstar' : 'Star'}">
                        <span class="star-icon ${starClass}">★</span>
                    </div>
                    <div class="email-sender-name">
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
                        <button class="email-action-btn" onclick="event.stopPropagation(); archiveEmail('${email.id}', ${index})" title="Archive">📦</button>
                        <button class="email-action-btn" onclick="event.stopPropagation(); deleteEmail('${email.id}', ${index})" title="Delete">🗑️</button>
                    </div>
                    ${dateText ? `<div class="email-date">${dateText}</div>` : ''}
                </div>
            </div>
        `;
    }).join('');
    
    // Start observing new emails for pre-fetching
    setTimeout(() => observeEmailsForPrefetch(), 100);
}

// Get category badge HTML
function getCategoryBadge(category) {
    const badges = {
        'DEAL_FLOW': '<span class="badge badge-deal-flow">💼 Deal Flow</span>',
        'NETWORKING': '<span class="badge badge-networking">🤝 Networking</span>',
        'HIRING': '<span class="badge badge-hiring">👔 Hiring</span>',
        'GENERAL': '<span class="badge badge-general">📰 General</span>',
        'SPAM': '<span class="badge badge-spam">⚠️ Spam</span>',
        'SENT': '<span class="badge badge-sent">📤 Sent</span>',
        'STARRED': '<span class="badge badge-starred">⭐ Starred</span>'
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
    
    // Handle attachments - use message_id for each attachment
    let attachmentsHtml = '';
    const attachments = email.attachments || [];
    if (attachments.length > 0) {
        const attHtml = attachments.map(att => {
            const filename = att.filename || 'attachment';
            const mimeType = att.mime_type || '';
            // URL encode the filename for the URL
            const encodedFilename = encodeURIComponent(filename);
            
            if (mimeType === 'application/pdf') {
                // Use message_id instead of thread_id so each message's attachments work correctly
                return `<a href="/api/attachment/${escapeHtml(email.id)}/${encodedFilename}" target="_blank" class="attachment-link" style="display: inline-flex; align-items: center; gap: 8px; padding: 8px 12px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 8px; color: var(--primary-color); text-decoration: none; margin-right: 8px; margin-bottom: 8px;">📎 ${escapeHtml(filename)}</a>`;
            } else if (mimeType.startsWith('image/')) {
                // Inline preview for image attachments
                const url = `/api/attachment/${escapeHtml(email.id)}/${encodedFilename}`;
                return `
                    <a href="${url}" target="_blank" class="attachment-link" style="display: inline-flex; flex-direction: column; align-items: flex-start; gap: 4px; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 8px; text-decoration: none; margin-right: 8px; margin-bottom: 8px;">
                        <span style="color: var(--text-secondary); font-size: 12px; margin-bottom: 4px;">📎 ${escapeHtml(filename)}</span>
                        <img src="${url}" alt="${escapeHtml(filename)}" style="max-width: 220px; max-height: 160px; border-radius: 6px; display: block; object-fit: contain; background: #fff;" />
                    </a>
                `;
            } else {
                // Generic downloadable attachment
                const url = `/api/attachment/${escapeHtml(email.id)}/${encodedFilename}`;
                return `<a href="${url}" target="_blank" class="attachment-link" style="display: inline-flex; align-items: center; gap: 8px; padding: 8px 12px; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 8px; color: var(--text-secondary); text-decoration: none; margin-right: 8px; margin-bottom: 8px;">📎 ${escapeHtml(filename)}</a>`;
            }
        }).join('');
        attachmentsHtml = `<div style="margin-bottom: 16px; margin-top: 12px;"><strong style="color: var(--text-primary); font-size: 13px;">Attachments:</strong><div style="margin-top: 8px;">${attHtml}</div></div>`;
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
            iframe.setAttribute('sandbox', 'allow-same-origin'); // no scripts, but allow styles
            iframe.style.width = '100%';
            iframe.style.border = 'none';
            iframe.style.minHeight = '400px';
            
            node.appendChild(iframe);
            
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
    // Accept either an index (from email list) or an email object directly (from deals table)
    if (typeof indexOrEmail === 'object' && indexOrEmail !== null) {
        // Email object passed directly
        currentEmail = indexOrEmail;
    } else {
        // Index passed - use filteredEmails instead of allEmails to get the correct email
        // This ensures we open the email that's actually displayed in the current tab
        const index = indexOrEmail;
        if (index >= 0 && index < filteredEmails.length) {
            currentEmail = filteredEmails[index];
        } else {
            // Fallback: try to find by allEmails index
            currentEmail = allEmails[index];
        }
    }
    currentReply = null;
    
    if (!currentEmail || !currentEmail.thread_id) {
        showAlert('error', 'Unable to load email thread');
        return;
    }
    
    // Set modal header with initial subject (will be updated from thread if available)
    const subjectEl = document.getElementById('modalSubject');
    const initialSubject = currentEmail.subject && currentEmail.subject.trim() && currentEmail.subject !== 'No Subject' 
        ? decodeHtmlEntities(currentEmail.subject) 
        : 'Loading...';
    subjectEl.textContent = initialSubject;
    subjectEl.style.display = 'block';
    
    // Set initial sender/recipient info (from first email)
    // For sent emails, show "To:" instead of "From:"
    const isSent = currentEmail.is_sent || currentEmail.classification?.category === 'SENT';
    const field = isSent ? (currentEmail.to || currentEmail.from || '') : (currentEmail.from || '');
    const { senderName, senderEmail } = parseSender(field);
    document.getElementById('modalFrom').textContent = senderName;
    document.getElementById('modalFromEmail').textContent = senderEmail;
    
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
    document.getElementById('modalAvatar').textContent = avatarLetter;
    
    // Set date
    document.getElementById('modalDate').textContent = formatDate(currentEmail.date);
    
    // Display tags
    const classification = currentEmail.classification || {};
    const tags = classification.tags || [];
    const tagsHtml = tags.map(tag => `<span class="tag">${escapeHtml(tag)}</span>`).join('');
    document.getElementById('modalTags').innerHTML = tagsHtml || '';
    
    // Deal scores section removed
    
    // Hide single email section, show thread container
    document.getElementById('singleEmailSection').style.display = 'none';
    const threadContainer = document.getElementById('threadContainer');
    
    // Show modal immediately
    document.getElementById('emailModal').style.display = 'flex';
    
    const threadId = currentEmail.thread_id;
    
    // Clear thread container first to prevent showing wrong email
    threadContainer.innerHTML = '';
    
    // ALWAYS show email from list immediately (no "Loading thread..." delay)
    if (currentEmail.body || currentEmail.combined_text) {
        threadContainer.innerHTML = renderThreadMessage(currentEmail, true);
        enhanceHtmlEmails([currentEmail]);
    }
    
    // Check IndexedDB cache for full thread - ONLY if thread_id matches
    const cached = await getCachedThread(threadId);
    if (cached && cached.emails && cached.emails.length > 0) {
        // Validate that cached thread matches the current email's thread_id
        const cachedThreadId = cached.emails[0]?.thread_id || cached.thread_id;
        if (cachedThreadId === threadId) {
            console.log(`⚡ Loading thread ${threadId} from cache (instant)`);
            
            // Display cached thread data immediately (replace single email with full thread)
            let threadHtml = '';
            cached.emails.forEach((email, idx) => {
                threadHtml += renderThreadMessage(email, idx === 0);
            });
            threadContainer.innerHTML = threadHtml;
            enhanceHtmlEmails(cached.emails);
            
            // Show subtle "refreshing" indicator
            showCacheRefreshIndicator();
        } else {
            console.log(`⚠️  Cached thread ID mismatch (expected ${threadId}, got ${cachedThreadId}), ignoring cache`);
            // Invalid cache - keep showing the current email from list
        }
    }
    
    // Always fetch fresh data in background (even if cache exists)
    (async () => {
        try {
            const response = await fetch(`/api/thread/${currentEmail.thread_id}`);
            const data = await response.json();
            
            if (data.success && data.emails && data.emails.length > 0) {
                // Cache the fresh data
                await cacheThread(threadId, data);
                
                // Find the first email with a valid subject
                let subjectToUse = null;
                for (const email of data.emails) {
                    if (email.subject && email.subject.trim() && email.subject !== 'No Subject' && email.subject.trim().length > 0) {
                        subjectToUse = email.subject;
                        break;
                    }
                }
                
                // Update subject if we found one
                if (subjectToUse) {
                    const decodedSubject = decodeHtmlEntities(subjectToUse);
                    const subjectEl = document.getElementById('modalSubject');
                    if (subjectEl) {
                        subjectEl.textContent = decodedSubject;
                    }
                }
                
                // Update UI if cache was shown (or display if no cache)
                // Only update if we're still viewing the same thread
                if (currentEmail && currentEmail.thread_id === threadId) {
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
                    console.log(`⚠️  Thread changed while loading (expected ${threadId}, current ${currentEmail?.thread_id}), ignoring update`);
                }
                
                hideCacheRefreshIndicator();
                
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
    
    // Show reply section and reset state
    document.getElementById('replySection').style.display = 'block';
    document.getElementById('replyContent').innerHTML = '';
    document.getElementById('replyActions').style.display = 'none';
    document.getElementById('replyEditor').style.display = 'none';
    document.getElementById('replyLoading').style.display = 'none';
    
    // Clear composer when opening a new email (prevent draft from previous email)
    clearComposer();
}

// Close modal
function closeModal() {
    document.getElementById('emailModal').style.display = 'none';
    currentEmail = null;
    currentReply = null;
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
            const hasSignature = sig.hasSignature || (sig.signatureRaw && sig.signatureRaw.trim().length > 0);
            const signatureToShow = sig.signature || (sig.signatureRaw ? 'Raw signature available but could not be processed' : '');
            
            const signaturePreview = hasSignature ? 
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
    
    // Show loading
    replyLoading.style.display = 'block';
    replyContent.innerHTML = '';
    replyActions.style.display = 'none';
    
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
                replyContent.innerHTML = `
                    <div class="alert alert-info">
                        ${data.message || 'AI determined this email doesn\'t need a reply'}
                    </div>
                `;
            } else {
                currentReply = data.reply;
                replyContent.textContent = data.reply;
                replyActions.style.display = 'flex';
            }
        } else {
            showAlert('error', data.error || 'Failed to generate reply');
        }
    } catch (error) {
        console.error('Error generating reply:', error);
        showAlert('error', 'Error generating reply: ' + error.message);
    } finally {
        replyLoading.style.display = 'none';
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
        showAlert('error', 'No email selected');
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
        showAlert('error', 'No email selected');
        return;
    }
    // TODO: Implement mark as unread functionality
    showAlert('info', 'Mark as unread functionality coming soon');
}

// Open reply composer (to be implemented with full features)
// Composer state
let composerMode = 'reply'; // 'reply', 'reply-all', or 'forward'
let composerAttachments = [];

function openReplyComposer() {
    if (!currentEmail) {
        showAlert('error', 'No email selected');
        return;
    }
    
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
    
    // Set body with quoted text
    const quotedText = formatQuotedText(currentEmail);
    composerBody.value = `\n\n${quotedText}`;
    
    // Clear attachments
    composerAttachments = [];
    updateAttachmentPreview();
    
    // Hide reply section, show composer
    document.getElementById('replySection').style.display = 'none';
    composerSection.style.display = 'block';
    
    // Focus on body
    composerBody.focus();
}

// Open reply all composer
function openReplyAllComposer() {
    if (!currentEmail) {
        showAlert('error', 'No email selected');
        return;
    }
    
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
    
    // Set body with quoted text
    const quotedText = formatQuotedText(currentEmail);
    composerBody.value = `\n\n${quotedText}`;
    
    // Clear attachments
    composerAttachments = [];
    updateAttachmentPreview();
    
    // Hide reply section, show composer
    document.getElementById('replySection').style.display = 'none';
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
    composerBody.value = `\n\n${forwardedText}`;
    
    // Include original attachments if any
    composerAttachments = [];
    if (currentEmail.attachments && currentEmail.attachments.length > 0) {
        showAlert('info', 'Original attachments will be included automatically');
    }
    updateAttachmentPreview();
    
    // Hide reply section, show composer
    document.getElementById('replySection').style.display = 'none';
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
    if (composerBody) composerBody.value = '';
    
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

async function sendComposedEmail() {
    const to = document.getElementById('composerTo').value.trim();
    const cc = document.getElementById('composerCc').value.trim();
    const bcc = document.getElementById('composerBcc').value.trim();
    const subject = document.getElementById('composerSubject').value.trim();
    const body = document.getElementById('composerBody').value.trim();
    
    if (!to) {
        showAlert('error', 'Please enter a recipient');
        return;
    }
    
    if (!body) {
        showAlert('error', 'Please enter a message');
        return;
    }
    
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
            closeComposer();
            closeModal();
        } else {
            showAlert('error', data.error || 'Failed to send email');
        }
    } catch (error) {
        console.error('Error sending email:', error);
        showAlert('error', 'Failed to send email: ' + error.message);
    }
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


// Compose email functions
function openComposeModal() {
    document.getElementById('composeModal').style.display = 'flex';
    // Clear previous values
    document.getElementById('composeTo').value = '';
    document.getElementById('composeSubject').value = '';
    document.getElementById('composeBody').value = '';
    // Focus on To field
    setTimeout(() => {
        document.getElementById('composeTo').focus();
    }, 100);
}

function closeComposeModal() {
    document.getElementById('composeModal').style.display = 'none';
}

async function sendComposedEmail() {
    const to = document.getElementById('composeTo').value.trim();
    const subject = document.getElementById('composeSubject').value.trim();
    const body = document.getElementById('composeBody').value.trim();
    
    if (!to || !subject || !body) {
        alert('Please fill in all fields: To, Subject, and Message');
        return;
    }
    
    // Validate email format (basic)
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(to)) {
        alert('Please enter a valid email address');
        return;
    }
    
    const sendBtn = document.getElementById('sendComposeBtn');
    const sendBtnText = document.getElementById('sendComposeBtnText');
    const sendBtnSpinner = document.getElementById('sendComposeBtnSpinner');
    
    // Show loading state
    sendBtn.disabled = true;
    sendBtnText.style.display = 'none';
    sendBtnSpinner.style.display = 'inline-block';
    
    try {
        const response = await fetch('/api/send-email', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                to: to,
                subject: subject,
                body: body
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Show success message
            const alert = document.createElement('div');
            alert.className = 'alert alert-success';
            alert.style.position = 'fixed';
            alert.style.top = '20px';
            alert.style.right = '20px';
            alert.style.zIndex = '10000';
            alert.innerHTML = '✓ Email sent successfully';
            document.body.appendChild(alert);
            
            setTimeout(() => {
                alert.remove();
            }, 3000);
            
            // Close modal and clear fields
            closeComposeModal();
            
            // Refresh sent emails if on sent tab
            if (currentTab === 'sent') {
                fetchSentEmails();
            }
        } else {
            alert('Error: ' + (data.error || 'Failed to send email'));
        }
    } catch (error) {
        alert('Error: ' + error.message);
    } finally {
        // Reset button state
        sendBtn.disabled = false;
        sendBtnText.style.display = 'inline';
        sendBtnSpinner.style.display = 'none';
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

async function deleteEmail(emailId, emailIndex) {
    if (!confirm('Are you sure you want to delete this email?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/emails/${emailId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Remove email from list
            allEmails = allEmails.filter(e => e.id !== emailId);
            filteredEmails = filteredEmails.filter(e => e.id !== emailId);
            displayEmails(filteredEmails);
            showAlert('success', 'Email deleted');
        } else {
            showAlert('error', data.error || 'Failed to delete email');
        }
    } catch (error) {
        console.error('Error deleting email:', error);
        showAlert('error', 'Failed to delete email');
    }
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
    });
    
    // Remove active class from all tabs
    document.querySelectorAll('.settings-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Show selected tab content
    const content = document.getElementById(`settings-${tabName}`);
    if (content) {
        content.classList.add('active');
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
                    statusBadge.textContent = `✅ Enabled (${data.whatsapp_number})`;
                    statusBadge.style.color = '#10b981';
                } else {
                    statusBadge.textContent = 'Not configured';
                    statusBadge.style.color = '#6B7280';
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
    const activeTab = document.querySelector('.settings-tab.active');
    if (!activeTab) return;
    
    const tabName = activeTab.id.replace('tab-', '');
    
    if (tabName === 'whatsapp') {
        saveWhatsAppSettings();
    } else if (tabName === 'user') {
        await saveUserProfile();
    }
}

async function saveUserProfile() {
    const fullNameInput = document.getElementById('userFullName');
    if (!fullNameInput) return;
    
    const fullName = fullNameInput.value.trim();
    const statusDiv = document.getElementById('userStatus');
    
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
            if (statusDiv) {
                statusDiv.style.display = 'block';
                statusDiv.style.background = '#efe';
                statusDiv.style.color = '#3c3';
                statusDiv.style.border = '1px solid #cfc';
                statusDiv.textContent = '✅ Profile updated successfully!';
            }
            
            setTimeout(() => {
                if (statusDiv) statusDiv.style.display = 'none';
            }, 2000);
        } else {
            if (statusDiv) {
                statusDiv.style.display = 'block';
                statusDiv.style.background = '#fee';
                statusDiv.style.color = '#c33';
                statusDiv.style.border = '1px solid #fcc';
                statusDiv.textContent = '❌ ' + (data.error || 'Failed to update profile');
            }
        }
    } catch (error) {
        console.error('Error saving user profile:', error);
        if (statusDiv) {
            statusDiv.style.display = 'block';
            statusDiv.style.background = '#fee';
            statusDiv.style.color = '#c33';
            statusDiv.style.border = '1px solid #fcc';
            statusDiv.textContent = '❌ Error updating profile. Please try again.';
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
    
    // Validate phone number if enabled
    if (enabled && number) {
        if (!number.startsWith('+')) {
            statusDiv.style.display = 'block';
            statusDiv.style.background = '#fee';
            statusDiv.style.color = '#c33';
            statusDiv.style.border = '1px solid #fcc';
            statusDiv.textContent = '❌ Phone number must start with + (e.g., +1234567890)';
            return;
        }
        
        // Basic validation: + followed by 10-15 digits
        if (!/^\+[1-9]\d{9,14}$/.test(number)) {
            statusDiv.style.display = 'block';
            statusDiv.style.background = '#fee';
            statusDiv.style.color = '#c33';
            statusDiv.style.border = '1px solid #fcc';
            statusDiv.textContent = '❌ Invalid phone number format. Use: +1234567890';
            return;
        }
    }
    
    // Show loading state
    const saveBtn = event.target;
    const originalText = saveBtn.textContent;
    saveBtn.textContent = 'Saving...';
    saveBtn.disabled = true;
    statusDiv.style.display = 'none';
    
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
        
        const data = await response.json();
        
        if (data.success) {
            if (statusDiv) {
                statusDiv.style.display = 'block';
                statusDiv.style.background = '#efe';
                statusDiv.style.color = '#3c3';
                statusDiv.style.border = '1px solid #cfc';
                statusDiv.textContent = '✅ Settings saved successfully!';
            }
            
            // Update WhatsApp status badge
            const statusBadge = document.getElementById('whatsappStatusBadge');
            if (statusBadge) {
                if (enabled && number) {
                    statusBadge.textContent = `✅ Enabled (${number})`;
                    statusBadge.style.color = '#10b981';
                } else {
                    statusBadge.textContent = 'Not configured';
                    statusBadge.style.color = '#6B7280';
                }
            }
            
            // Auto-close after 2 seconds
            setTimeout(() => {
                closeSettingsModal();
            }, 2000);
        } else {
            statusDiv.style.display = 'block';
            statusDiv.style.background = '#fee';
            statusDiv.style.color = '#c33';
            statusDiv.style.border = '1px solid #fcc';
            statusDiv.textContent = '❌ ' + (data.error || 'Failed to save settings');
        }
    } catch (error) {
        console.error('Error saving WhatsApp settings:', error);
        statusDiv.style.display = 'block';
        statusDiv.style.background = '#fee';
        statusDiv.style.color = '#c33';
        statusDiv.style.border = '1px solid #fcc';
        statusDiv.textContent = '❌ Error saving settings. Please try again.';
    } finally {
        saveBtn.textContent = originalText;
        saveBtn.disabled = false;
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
