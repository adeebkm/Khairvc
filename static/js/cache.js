/**
 * IndexedDB Cache System for Email Threads
 * Provides instant loading for previously viewed threads
 */

let threadDB = null;
const DB_NAME = 'gmail_threads';
const DB_VERSION = 1;
const STORE_NAME = 'threads';
const CACHE_EXPIRATION = 5 * 60 * 1000; // 5 minutes
const CLEANUP_AGE = 24 * 60 * 60 * 1000; // 24 hours

/**
 * Initialize IndexedDB for thread caching
 * @returns {Promise<IDBDatabase>}
 */
async function initThreadCache() {
    if (threadDB) {
        return threadDB;
    }

    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DB_NAME, DB_VERSION);
        
        request.onerror = () => {
            console.error('IndexedDB initialization failed:', request.error);
            reject(request.error);
        };
        
        request.onsuccess = () => {
            threadDB = request.result;
            console.log('✅ IndexedDB thread cache initialized');
            resolve(threadDB);
        };
        
        request.onupgradeneeded = (event) => {
            const db = event.target.result;
            
            // Create threads object store if it doesn't exist
            if (!db.objectStoreNames.contains(STORE_NAME)) {
                const store = db.createObjectStore(STORE_NAME, { keyPath: 'thread_id' });
                
                // Create index on cached_at for cleanup queries
                store.createIndex('cached_at', 'cached_at', { unique: false });
                
                console.log('✅ Created threads object store');
            }
        };
    });
}

/**
 * Cache thread data in IndexedDB
 * @param {string} threadId - Gmail thread ID
 * @param {Object} threadData - Thread data with emails array
 * @returns {Promise<void>}
 */
async function cacheThread(threadId, threadData) {
    try {
        if (!threadDB) {
            await initThreadCache();
        }
        
        const transaction = threadDB.transaction([STORE_NAME], 'readwrite');
        const store = transaction.objectStore(STORE_NAME);
        
        const cacheEntry = {
            thread_id: threadId,
            emails: threadData.emails || threadData,
            cached_at: Date.now(),
            version: 1,
            email_count: (threadData.emails || threadData).length
        };
        
        await store.put(cacheEntry);
        
        console.log(`📦 Cached thread ${threadId} (${cacheEntry.email_count} messages)`);
    } catch (error) {
        console.error('Error caching thread:', error);
    }
}

/**
 * Get cached thread from IndexedDB
 * @param {string} threadId - Gmail thread ID
 * @returns {Promise<Object|null>} Cached thread data or null if not found/expired
 */
async function getCachedThread(threadId) {
    try {
        if (!threadDB) {
            await initThreadCache();
        }
        
        const transaction = threadDB.transaction([STORE_NAME], 'readonly');
        const store = transaction.objectStore(STORE_NAME);
        
        return new Promise((resolve) => {
            const request = store.get(threadId);
            
            request.onsuccess = () => {
                const cached = request.result;
                
                if (!cached) {
                    resolve(null);
                    return;
                }
                
                // Check if cache is still valid (not expired)
                const age = Date.now() - cached.cached_at;
                if (age < CACHE_EXPIRATION) {
                    console.log(`⚡ Retrieved thread ${threadId} from cache (age: ${Math.round(age / 1000)}s)`);
                    resolve(cached);
                } else {
                    console.log(`⏰ Cache expired for thread ${threadId} (age: ${Math.round(age / 1000)}s)`);
                    resolve(null);
                }
            };
            
            request.onerror = () => {
                console.error('Error retrieving cached thread:', request.error);
                resolve(null);
            };
        });
    } catch (error) {
        console.error('Error getting cached thread:', error);
        return null;
    }
}

/**
 * Invalidate (delete) a cached thread
 * @param {string} threadId - Gmail thread ID
 * @returns {Promise<void>}
 */
async function invalidateThreadCache(threadId) {
    try {
        if (!threadDB) {
            await initThreadCache();
        }
        
        const transaction = threadDB.transaction([STORE_NAME], 'readwrite');
        const store = transaction.objectStore(STORE_NAME);
        
        await store.delete(threadId);
        
        console.log(`🗑️  Invalidated cache for thread ${threadId}`);
    } catch (error) {
        console.error('Error invalidating thread cache:', error);
    }
}

/**
 * Clean up old threads (older than 24 hours)
 * @returns {Promise<number>} Number of threads deleted
 */
async function cleanupOldThreads() {
    try {
        if (!threadDB) {
            await initThreadCache();
        }
        
        const transaction = threadDB.transaction([STORE_NAME], 'readwrite');
        const store = transaction.objectStore(STORE_NAME);
        const index = store.index('cached_at');
        
        const cutoffTime = Date.now() - CLEANUP_AGE;
        const range = IDBKeyRange.upperBound(cutoffTime);
        
        return new Promise((resolve) => {
            const request = index.openCursor(range);
            let deletedCount = 0;
            
            request.onsuccess = (event) => {
                const cursor = event.target.result;
                if (cursor) {
                    cursor.delete();
                    deletedCount++;
                    cursor.continue();
                } else {
                    if (deletedCount > 0) {
                        console.log(`🧹 Cleaned up ${deletedCount} old thread(s) from cache`);
                    }
                    resolve(deletedCount);
                }
            };
            
            request.onerror = () => {
                console.error('Error cleaning up old threads:', request.error);
                resolve(0);
            };
        });
    } catch (error) {
        console.error('Error during cleanup:', error);
        return 0;
    }
}

/**
 * Get cache statistics
 * @returns {Promise<Object>} Cache stats
 */
async function getCacheStats() {
    try {
        if (!threadDB) {
            await initThreadCache();
        }
        
        const transaction = threadDB.transaction([STORE_NAME], 'readonly');
        const store = transaction.objectStore(STORE_NAME);
        
        return new Promise((resolve) => {
            const countRequest = store.count();
            
            countRequest.onsuccess = () => {
                const count = countRequest.result;
                
                // Estimate size (rough approximation)
                const estimatedSize = count * 50; // ~50KB per thread average
                
                resolve({
                    threadCount: count,
                    estimatedSizeKB: estimatedSize,
                    estimatedSizeMB: (estimatedSize / 1024).toFixed(2)
                });
            };
            
            countRequest.onerror = () => {
                resolve({ threadCount: 0, estimatedSizeKB: 0, estimatedSizeMB: '0.00' });
            };
        });
    } catch (error) {
        console.error('Error getting cache stats:', error);
        return { threadCount: 0, estimatedSizeKB: 0, estimatedSizeMB: '0.00' };
    }
}

/**
 * Clear all cached threads
 * @returns {Promise<void>}
 */
async function clearAllThreadCache() {
    try {
        if (!threadDB) {
            await initThreadCache();
        }
        
        const transaction = threadDB.transaction([STORE_NAME], 'readwrite');
        const store = transaction.objectStore(STORE_NAME);
        
        await store.clear();
        
        console.log('🗑️  Cleared all thread cache');
    } catch (error) {
        console.error('Error clearing thread cache:', error);
    }
}

/**
 * Pre-fetch a thread in the background
 * @param {string} threadId - Gmail thread ID
 * @returns {Promise<void>}
 */
async function prefetchThread(threadId) {
    try {
        // Check if already cached
        const cached = await getCachedThread(threadId);
        if (cached) {
            return; // Already cached, no need to fetch
        }
        
        // Fetch in background
        const response = await fetch(`/api/thread/${threadId}`);
        if (!response.ok) {
            return;
        }
        
        const data = await response.json();
        if (data.success && data.emails) {
            await cacheThread(threadId, data);
            console.log(`📦 Pre-fetched thread ${threadId}`);
        }
    } catch (error) {
        // Silently fail - pre-fetching shouldn't break UX
        console.debug('Pre-fetch failed for thread:', threadId, error);
    }
}

// Run cleanup on initialization
if (typeof document !== 'undefined') {
    document.addEventListener('DOMContentLoaded', async () => {
        try {
            await initThreadCache();
            await cleanupOldThreads();
        } catch (error) {
            console.error('Error initializing thread cache:', error);
        }
    });
}

