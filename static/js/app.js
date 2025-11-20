// Global state
let currentEmail = null;
let currentReply = null;
let allEmails = [];
let filteredEmails = []; // Currently displayed/filtered emails
let currentTab = 'all';
let searchQuery = ''; // Current search query

// Pagination state
let currentPage = 1;
const EMAILS_PER_PAGE = 40;
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
        // Use incremental sync - only fetch new emails (no force_full_sync)
        const response = await fetch(`/api/emails?max=100&show_spam=true`);
        const data = await response.json();
        
        // Handle rate limit errors
        if (response.status === 429 || data.rate_limit) {
            // Pause auto-fetch for 10 minutes after rate limit
            autoFetchPausedUntil = Date.now() + (10 * 60 * 1000);
            console.log(`⚠️  Auto-fetch paused due to rate limit. Will resume in 10 minutes.`);
            return;
        }
        
        if (data.success && data.emails && data.emails.length > 0) {
            // Check if these are actually new emails
            const existingThreadIds = new Set(emailCache.data.map(e => e.thread_id));
            const uniqueNewEmails = data.emails.filter(e => !existingThreadIds.has(e.thread_id));
            
            if (uniqueNewEmails.length > 0) {
                // Add new emails to cache
                emailCache.data = [...emailCache.data, ...uniqueNewEmails];
                emailCache.timestamp = Date.now();
                saveEmailCacheToStorage(); // Save to localStorage
                allEmails = emailCache.data;
                
                // Apply filters and update display
                applyFilters();
                
                // Show notification
                showAlert('success', `📧 ${uniqueNewEmails.length} new email${uniqueNewEmails.length !== 1 ? 's' : ''} detected!`);
                
                console.log(`✅ Auto-fetch: Detected and loaded ${uniqueNewEmails.length} new emails`);
            } else {
                console.log(`ℹ️  Auto-fetch: No new emails detected`);
            }
        }
    } catch (error) {
        console.error('Error in auto-fetch:', error);
        // Silently fail - don't spam user with errors for background polling
    }
}

// Start/stop auto-fetch polling
function toggleAutoFetch(enabled) {
    autoFetchEnabled = enabled;
    
    // Save preference to localStorage
    localStorage.setItem('autoFetchEnabled', enabled ? 'true' : 'false');
    
    // Update checkbox if it exists
    const checkbox = document.getElementById('autoFetchCheck');
    if (checkbox) {
        checkbox.checked = enabled;
    }
    
    if (enabled) {
        // Start polling
        if (autoFetchInterval) {
            clearInterval(autoFetchInterval);
        }
        autoFetchInterval = setInterval(autoFetchNewEmails, AUTO_FETCH_INTERVAL);
        console.log('✅ Auto-fetch enabled: Checking for new emails every 5 minutes');
        
        // Do an initial check after 30 seconds
        setTimeout(autoFetchNewEmails, 30000);
    } else {
        // Stop polling
        if (autoFetchInterval) {
            clearInterval(autoFetchInterval);
            autoFetchInterval = null;
        }
        console.log('⏸️  Auto-fetch disabled');
    }
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
        // Start initial fetch (60 emails)
        if (progressText) progressText.textContent = 'Fetching your first 60 emails...';
        if (progressBar) progressBar.style.width = '10%';
        
        const response = await fetch('/api/setup/fetch-initial', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        
        // If setup is already complete (user has emails), skip to completion
        if (data.success && data.already_complete) {
            console.log(`✅ Setup already complete: ${data.email_count} emails found`);
            if (progressBar) progressBar.style.width = '100%';
            if (progressText) progressText.textContent = `Found ${data.email_count} existing emails!`;
            // Wait a moment then proceed
            await new Promise(resolve => setTimeout(resolve, 1500));
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
        
        // Mark setup as complete
        await fetch('/api/setup/complete', { method: 'POST' });
        
        // Hide setup screen and show main content
        if (setupScreen) setupScreen.style.display = 'none';
        const compactHeader = document.querySelector('.main-content > .compact-header');
        if (compactHeader) compactHeader.style.display = 'block';
        const emailList = document.getElementById('emailList');
        if (emailList) emailList.style.display = 'block';
        
        // Load emails
        await loadEmailsFromDatabase();
        
        // Start background fetching
        startBackgroundFetching();
        
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
                await fetch('/api/setup/complete', { method: 'POST' });
                
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
                } else if (data.status === 'FAILURE') {
                    clearInterval(interval);
                    reject(new Error(data.error || 'Setup failed'));
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

async function fetchInitialEmailsStreaming(progressBar, progressText) {
    // Use streaming endpoint for initial fetch
    if (progressText) progressText.textContent = 'Connecting to server...';
    
    const response = await fetch('/api/emails/stream?max=60&force_full_sync=true');
    
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
    const total = 60;
    
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
    
    // Remove existing pagination
    const existingPagination = emailList.querySelector('.pagination');
    if (existingPagination) {
        existingPagination.remove();
    }
    
    // Calculate pagination
    const totalEmails = filteredEmails.length;
    const totalPages = Math.ceil(totalEmails / EMAILS_PER_PAGE);
    
    if (totalPages <= 1) return; // No pagination needed
    
    // Get emails for current page
    const startIndex = (currentPage - 1) * EMAILS_PER_PAGE;
    const endIndex = startIndex + EMAILS_PER_PAGE;
    paginatedEmails = filteredEmails.slice(startIndex, endIndex);
    
    // Display current page emails
    displayEmails(paginatedEmails);
    
    // Create pagination controls
    const pagination = document.createElement('div');
    pagination.className = 'pagination';
    
    // Previous button
    const prevBtn = document.createElement('button');
    prevBtn.textContent = '← Previous';
    prevBtn.disabled = currentPage === 1;
    prevBtn.onclick = () => {
        if (currentPage > 1) {
            currentPage--;
            updatePagination();
        }
    };
    pagination.appendChild(prevBtn);
    
    // Page info
    const pageInfo = document.createElement('span');
    pageInfo.className = 'pagination-info';
    pageInfo.textContent = `Page ${currentPage} of ${totalPages} (${totalEmails} emails)`;
    pagination.appendChild(pageInfo);
    
    // Next button
    const nextBtn = document.createElement('button');
    nextBtn.textContent = 'Next →';
    nextBtn.disabled = currentPage === totalPages;
    nextBtn.onclick = () => {
        if (currentPage < totalPages) {
            currentPage++;
            updatePagination();
        }
    };
    pagination.appendChild(nextBtn);
    
    // Insert pagination after email list
    emailList.appendChild(pagination);
}

// ==================== BACKGROUND FETCHING ====================
let backgroundFetchInterval = null;
let backgroundFetchActive = false;

async function startBackgroundFetching() {
    if (backgroundFetchActive) return;
    
    backgroundFetchActive = true;
    
    // Check every 2 minutes if we need to fetch more emails
    backgroundFetchInterval = setInterval(async () => {
        try {
            const response = await fetch('/api/emails/background-fetch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            const data = await response.json();
            
            if (data.success && data.task_id) {
                console.log(`🔄 Background fetch started: ${data.fetching} emails (${data.current_count}/${data.target_total})`);
                
                // Poll for completion (silently)
                pollBackgroundTask(data.task_id);
            } else if (data.message === 'Already have enough emails') {
                console.log('✅ Background fetch: Already have 150 emails');
                stopBackgroundFetching();
            }
        } catch (error) {
            console.error('Background fetch error:', error);
        }
    }, 2 * 60 * 1000); // Every 2 minutes
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
document.addEventListener('DOMContentLoaded', async function() {
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
    
    // Restore auto-fetch preference from localStorage (default to true)
    const savedAutoFetch = localStorage.getItem('autoFetchEnabled');
    const shouldAutoFetch = savedAutoFetch === null ? true : savedAutoFetch === 'true';
    toggleAutoFetch(shouldAutoFetch);
    
    // Start background fetching if setup is complete
    try {
        const setupResponse = await fetch('/api/setup/status');
        const setupData = await setupResponse.json();
        if (setupData.success && setupData.setup_completed) {
            startBackgroundFetching();
        }
    } catch (error) {
        console.error('Error checking setup status:', error);
    }
    
    // Check if we have cached emails and display them
    const justConnected = urlParams.get('connected') === 'true';
    
    // ALWAYS verify database first before using cache
    // This ensures cache is cleared if database was reset
    try {
        const verifyResponse = await fetch(`/api/emails?max=100&db_only=true`);
        const verifyData = await verifyResponse.json();
        
        if (verifyData.success) {
            if (verifyData.emails && verifyData.emails.length > 0) {
                // Database has emails - use them (they're fresh from database)
                emailCache.data = verifyData.emails;
                emailCache.timestamp = Date.now();
                saveEmailCacheToStorage();
                
                allEmails = verifyData.emails;
                applyFilters();
                
                const emailCountEl = document.getElementById('emailCount');
                if (emailCountEl) {
                    emailCountEl.textContent = `${allEmails.length} email${allEmails.length !== 1 ? 's' : ''} (loaded from database)`;
                }
                console.log(`✅ Loaded ${verifyData.emails.length} emails from database`);
            } else {
                // Database is empty - clear any stale cache
                console.log('⚠️  Database is empty. Clearing any stale cache...');
                clearEmailCache();
                allEmails = [];
                applyFilters();
                
                const emailCountEl = document.getElementById('emailCount');
                if (emailCountEl) {
                    emailCountEl.textContent = 'No emails found. Click "Fetch" to load from Gmail.';
                }
            }
        } else {
            // Error fetching from database - try loading cache as fallback
            loadEmailCacheFromStorage();
            if (emailCache.data.length > 0 && emailCache.timestamp) {
                const cacheAge = Date.now() - emailCache.timestamp;
                const isFresh = cacheAge < emailCache.maxAge;
                console.log(`Using cached emails (${emailCache.data.length} emails, cached ${Math.round(cacheAge / 1000)}s ago, ${isFresh ? 'fresh' : 'stale'})`);
                allEmails = emailCache.data;
                applyFilters();
                const emailCountEl = document.getElementById('emailCount');
                if (emailCountEl) {
                    emailCountEl.textContent = `${allEmails.length} email${allEmails.length !== 1 ? 's' : ''} (${isFresh ? 'cached' : 'stale - click Fetch to refresh'})`;
                }
            }
        }
    } catch (error) {
        console.error('Error loading emails from database:', error);
        // On error, try loading cache as fallback
        loadEmailCacheFromStorage();
        if (emailCache.data.length > 0 && emailCache.timestamp) {
            const cacheAge = Date.now() - emailCache.timestamp;
            const isFresh = cacheAge < emailCache.maxAge;
            console.log(`Using cached emails (${emailCache.data.length} emails, cached ${Math.round(cacheAge / 1000)}s ago, ${isFresh ? 'fresh' : 'stale'})`);
            allEmails = emailCache.data;
            applyFilters();
            const emailCountEl = document.getElementById('emailCount');
            if (emailCountEl) {
                emailCountEl.textContent = `${allEmails.length} email${allEmails.length !== 1 ? 's' : ''} (${isFresh ? 'cached' : 'stale - click Fetch to refresh'})`;
            }
        } else {
            const emailCountEl = document.getElementById('emailCount');
            if (emailCountEl) {
                emailCountEl.textContent = 'Click "Fetch" to load emails';
            }
        }
    }
    
    // Skip auto-load if just connected
    if (justConnected) {
        console.log('Gmail just connected. Click "Fetch" button to load emails.');
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
                }
            } else {
                // Remove from starred cache
                starredEmailsCache = starredEmailsCache.filter(e => e.id !== emailId);
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
        
        // Show cached data immediately if available
        if (starredEmailsCache.length > 0) {
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
        }
        
        // Fetch fresh data in background
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
            const starredEmails = data.emails.map(email => ({
                ...email,
                classification: { category: 'STARRED' },
                is_starred: true
            }));
            
            // Update cache
            starredEmailsCache = starredEmails;
            
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
    let filtered = allEmails;
    
    // Apply category filter
    if (currentTab === 'networking') {
        filtered = allEmails.filter(e => e.classification?.category === 'NETWORKING');
    } else if (currentTab === 'hiring') {
        filtered = allEmails.filter(e => e.classification?.category === 'HIRING');
    } else if (currentTab === 'general') {
        filtered = allEmails.filter(e => e.classification?.category === 'GENERAL');
    } else if (currentTab === 'spam') {
        filtered = allEmails.filter(e => e.classification?.category === 'SPAM');
    } else if (currentTab === 'deal-flow') {
        filtered = allEmails.filter(e => e.classification?.category === 'DEAL_FLOW');
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
    
    // Use pagination if we have more than 40 emails
    if (sortedFiltered.length > EMAILS_PER_PAGE) {
        updatePagination();
    } else {
        // Display all emails if less than one page
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
        
        // NEW Scores: team_background_score, white_space_score, overall_score
        // Check for null/undefined explicitly (0 is a valid score)
        const overallScore = (deal.overall_score !== null && deal.overall_score !== undefined) ? Math.round(deal.overall_score) : 'N/A';
        const teamScore = (deal.team_background_score !== null && deal.team_background_score !== undefined) ? Math.round(deal.team_background_score) : 'N/A';
        const whiteSpaceScore = (deal.white_space_score !== null && deal.white_space_score !== undefined) ? Math.round(deal.white_space_score) : 'N/A';
        
        const scoreBadge = (deal.overall_score !== null && deal.overall_score !== undefined) ? 
            `<span class="score-badge score-${overallScore >= 70 ? 'high' : overallScore >= 50 ? 'medium' : 'low'}">${overallScore}</span>` :
            'N/A';
        
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
                <td>
                    <div class="score-display">
                        ${scoreBadge}
                        <div class="score-details">
                            <strong>Breakdown:</strong><br>
                            Team: ${teamScore}<br>
                            White Space: ${whiteSpaceScore}<br>
                            Overall: ${overallScore}
                            ${deal.score_summary ? `<br><br><strong>Summary:</strong><br><span style="font-size: 11px; color: var(--text-secondary); line-height: 1.4;">${escapeHtml(deal.score_summary)}</span>` : ''}
                        </div>
                    </div>
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
async function fetchEmails() {
    // Prevent multiple simultaneous fetches
    if (isFetching) {
        console.log('Already fetching emails, please wait...');
        return;
    }
    
    isFetching = true;
    const loading = document.getElementById('loading');
    const emailList = document.getElementById('emailList');
    const fetchBtn = document.getElementById('fetchEmailsBtn');
    
    // Show loading state
    loading.style.display = 'block';
    loading.innerHTML = '<div class="loading-spinner"></div><p>Starting email sync...</p><p class="loading-progress">Initializing...</p>';
    emailList.innerHTML = '';
    fetchBtn.disabled = true;
    
    try {
        const forceFullSync = document.getElementById('forceFullSyncCheck')?.checked || false;
        const maxEmails = 100; // Fixed to 100 emails
        
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
        let url = `/api/emails/stream?max=100&`;
        if (forceFullSync) url += 'force_full_sync=true&';
        
        const response = await fetch(url);
        
        // Check if streaming is supported
        if (!response.body) {
            console.warn('Streaming not supported, falling back to regular fetch');
            // Fallback to regular endpoint
            url = `/api/emails?max=100&`;
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
        const categoryParam = currentTab !== 'all' ? currentTab.toUpperCase().replace('-', '_') : null;
        let url = `/api/emails?db_only=true&max=100&`;
        if (categoryParam) url += `category=${categoryParam}&`;
        url += 'show_spam=true';
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.success) {
            const emails = data.emails || [];
            emailCache.data = emails;
            emailCache.timestamp = Date.now();
            saveEmailCacheToStorage();
            // CRITICAL: Set allEmails so applyFilters() can use it
            allEmails = emails;
            console.log(`✅ Loaded ${emails.length} emails from database`);
            applyFilters();
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
                message += '<br><small style="color: var(--text-secondary);">Click "Fetch Emails" button above to load emails from Gmail</small>';
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
        
        return `
            <div class="email-card" onclick="openEmail(${index})">
                <div class="email-row">
                    <div class="email-star" onclick="event.stopPropagation(); toggleStar('${email.id}', ${isStarred}, ${index})" title="${isStarred ? 'Unstar' : 'Star'}">
                        <span class="star-icon ${starClass}">★</span>
                    </div>
                    <div class="email-sender-name">
                        <span style="color: var(--text-secondary); font-size: 0.85em; margin-right: 4px; flex-shrink: 0;">${senderLabel}</span>
                        <span>${escapeHtml(decodeHtmlEntities(displayName))}</span>
                    </div>
                    <div class="email-content">
                        <div class="email-subject">
                            <span>${escapeHtml(decodedSubject)}</span>
                            ${categoryBadge}
                        </div>
                        <div class="email-snippet">${escapeHtml(decodedSnippet)}</div>
                    </div>
                    ${tagsHtml ? `<div class="email-tags">${tagsHtml}</div>` : ''}
                    ${dateText ? `<div class="email-date">${dateText}</div>` : ''}
                </div>
            </div>
        `;
    }).join('');
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
    
    // Load deal scores if this is a DEAL_FLOW email
    const modalDealScores = document.getElementById('modalDealScores');
    if (classification.category === 'DEAL_FLOW') {
        // Show scores section
        modalDealScores.style.display = 'block';
        
        // Fetch deal data to get scores
        try {
            const dealsResponse = await fetch('/api/deals');
            const dealsData = await dealsResponse.json();
            
            if (dealsData.success && dealsData.deals) {
                // Find the deal with matching thread_id
                const deal = dealsData.deals.find(d => d.thread_id === currentEmail.thread_id);
                
                if (deal) {
                    // Display scores
                    document.getElementById('modalTeamScore').textContent = 
                        deal.team_background_score !== null && deal.team_background_score !== undefined 
                        ? Math.round(deal.team_background_score) : '0';
                    
                    document.getElementById('modalWhiteSpaceScore').textContent = 
                        deal.white_space_score !== null && deal.white_space_score !== undefined 
                        ? Math.round(deal.white_space_score) : '0';
                    
                    document.getElementById('modalOverallScore').textContent = 
                        deal.overall_score !== null && deal.overall_score !== undefined 
                        ? Math.round(deal.overall_score) : '0';
                    
                    // Display score summary if available
                    const modalScoreSummary = document.getElementById('modalScoreSummary');
                    if (deal.score_summary) {
                        modalScoreSummary.style.display = 'block';
                        modalScoreSummary.querySelector('.score-summary-text').textContent = deal.score_summary;
                    } else {
                        modalScoreSummary.style.display = 'none';
                    }
                } else {
                    // Deal not found, hide scores
                    modalDealScores.style.display = 'none';
                }
            } else {
                modalDealScores.style.display = 'none';
            }
        } catch (error) {
            console.error('Error fetching deal scores:', error);
            modalDealScores.style.display = 'none';
        }
    } else {
        // Not a deal flow email, hide scores
        modalDealScores.style.display = 'none';
    }
    
    // Hide single email section, show thread container
    document.getElementById('singleEmailSection').style.display = 'none';
    const threadContainer = document.getElementById('threadContainer');
    
    // Show modal immediately
    document.getElementById('emailModal').style.display = 'flex';
    
    // Display cached email immediately for instant opening
    if (currentEmail.body || currentEmail.combined_text) {
        // Render the cached email first
        threadContainer.innerHTML = renderThreadMessage(currentEmail, true);
        enhanceHtmlEmails([currentEmail]);
    } else {
        threadContainer.innerHTML = '<div class="spinner-small"></div><p>Loading thread...</p>';
    }
    
    // Fetch full thread in the background (async, non-blocking)
    (async () => {
        try {
            const response = await fetch(`/api/thread/${currentEmail.thread_id}`);
            const data = await response.json();
            
            if (data.success && data.emails && data.emails.length > 0) {
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
                
                // Render all messages in thread
                let threadHtml = '';
                data.emails.forEach((email, idx) => {
                    threadHtml += renderThreadMessage(email, idx === 0);
                });
                threadContainer.innerHTML = threadHtml;
                enhanceHtmlEmails(data.emails);
                
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
            // Only show error if we didn't have cached data to display
            if (!currentEmail.body && !currentEmail.combined_text) {
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
    }
});
