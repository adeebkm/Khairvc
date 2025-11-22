-- Delete user 'adeebkm' and all associated data
-- Run these queries in order

-- Step 1: Find the user_id (run this first to verify)
SELECT id, username, email FROM users WHERE username = 'adeebkm';

-- Step 2: Delete email classifications for this user
DELETE FROM email_classifications WHERE user_id = (SELECT id FROM users WHERE username = 'adeebkm');

-- Step 3: Delete deals for this user
DELETE FROM deals WHERE user_id = (SELECT id FROM users WHERE username = 'adeebkm');

-- Step 4: Delete Gmail tokens for this user
DELETE FROM gmail_tokens WHERE user_id = (SELECT id FROM users WHERE username = 'adeebkm');

-- Step 5: Delete the user
DELETE FROM users WHERE username = 'adeebkm';

-- Verify deletion (should return 0 rows)
SELECT * FROM users WHERE username = 'adeebkm';
SELECT * FROM email_classifications WHERE user_id = (SELECT id FROM users WHERE username = 'adeebkm');
SELECT * FROM deals WHERE user_id = (SELECT id FROM users WHERE username = 'adeebkm');
SELECT * FROM gmail_tokens WHERE user_id = (SELECT id FROM users WHERE username = 'adeebkm');

