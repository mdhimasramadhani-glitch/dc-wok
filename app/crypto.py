import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

# Generate once via: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FERNET_KEY = os.getenv("FERNET_KEY", Fernet.generate_key().decode())
cipher = Fernet(FERNET_KEY.encode())

def encrypt_token(raw_token: str) -> str:
    return cipher.encrypt(raw_token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    return cipher.decrypt(encrypted_token.encode()).decode()