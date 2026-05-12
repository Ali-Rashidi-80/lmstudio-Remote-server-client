
import os

from pydantic_settings import BaseSettings, SettingsConfigDict

from typing import Optional



class Settings(BaseSettings):

    """

    مدیریت تنظیمات با استفاده از Pydantic.

    به صورت خودکار مقادیر را از فایل .env در ریشه پروژه می‌خواند.

    """

    # کلید رمزنگاری برای Fernet (باید ۳۲ کاراکتر Base64 باشد)

    ENCRYPTION_KEY: str

    

    # تنظیمات سرور

    HOST: str = "0.0.0.0"

    PORT: int = 8000

    

    # تنظیمات امنیتی

    DEBUG: bool = False

    

    # بارگذاری از فایل .env

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")



# ایجاد یک نمونه واحد (Singleton) برای استفاده در کل پروژه

try:

    settings = Settings()

except Exception as e:

    print(f"CRITICAL ERROR: Configuration loading failed. Check your .env file. Details: {e}")

    raise SystemExit(1)



# ابزار کمکی برای اطمینان از فرمت صحیح کلید

def get_encryption_key():

    return settings.ENCRYPTION_KEY.encode()


























# import os

# from cryptography.fernet import Fernet



# # برای تولید کلید: Fernet.generate_key()

# # در پروداکشن، این کلید را در Environment Variables قرار دهید

# ENCRYPTION_KEY = os.getenv("APP_ENCRYPTION_KEY", "your-secure-base64-key-here=")

# cipher_suite = Fernet(ENCRYPTION_KEY.encode())










# from cryptography.fernet import Fernet

# ایجاد این کلید: Fernet.generate_key()
# print(Fernet.generate_key().decode()) 


# آن را یکبار تولید کرده و همیشه در این فایل قرار دهید
# ENCRYPTION_KEY = b'S1SD50eXq-4vZYe3N-7p6ZlCDBU4e3iJfZpx5933PK8=' 


# import os

# import logging



# # تنظیمات لاگ برای امنیت بیشتر

# logging.basicConfig(level=logging.INFO)



# def get_encryption_key():

#     # خواندن کلید از متغیر محیطی (بهترین روش پروداکشن)

#     key = os.getenv("APP_ENCRYPTION_KEY")

    

#     if not key:

#         logging.warning("متغیر محیطی APP_ENCRYPTION_KEY یافت نشد! در حال استفاده از مقدار پیش‌فرض...")

#         # کلید ۳۲ بایتی برای AES-256 (حتماً در سرور اصلی تغییرش دهید)

#         return b'12345678901234567890123456789012'

    

#     return key.encode()



# KEY = get_encryption_key()




















