
from cryptography.fernet import Fernet

key = Fernet.generate_key()

print(f"YOUR_KEY: {key.decode()}")
