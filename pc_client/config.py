
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
