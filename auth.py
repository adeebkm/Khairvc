"""
Authentication utilities for token encryption
"""
from cryptography.fernet import Fernet
import os
import base64

# Generate encryption key (should be in .env in production)
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')
if not ENCRYPTION_KEY:
    # Generate a key for development
    key = Fernet.generate_key()
    ENCRYPTION_KEY = key.decode()
    print(f"⚠️  Generated encryption key for development. Add to .env: ENCRYPTION_KEY={ENCRYPTION_KEY}")


def get_cipher():
    """Get Fernet cipher instance"""
    if isinstance(ENCRYPTION_KEY, str):
        key = ENCRYPTION_KEY.encode()
    else:
        key = ENCRYPTION_KEY
    
    # Ensure key is 32 bytes base64-encoded
    if len(key) != 44:  # Base64 encoded 32 bytes = 44 chars
        key = base64.urlsafe_b64encode(key[:32].ljust(32, b'0'))
    
    return Fernet(key)


def encrypt_token(token_data):
    """Encrypt Gmail token data"""
    cipher = get_cipher()
    if isinstance(token_data, str):
        token_bytes = token_data.encode()
    else:
        token_bytes = token_data
    
    encrypted = cipher.encrypt(token_bytes)
    return encrypted.decode()


def decrypt_token(encrypted_token):
    """Decrypt Gmail token data"""
    cipher = get_cipher()
    if isinstance(encrypted_token, str):
        encrypted_bytes = encrypted_token.encode()
    else:
        encrypted_bytes = encrypted_token
    
    decrypted = cipher.decrypt(encrypted_bytes)
    return decrypted.decode()

