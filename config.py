import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    OWNER_ID = int(os.getenv("OWNER_ID"))
    BOT_USERNAME = os.getenv("BOT_USERNAME")
    DATABASE_URL = os.getenv("DATABASE_URL")
    REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL")
    CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1003408636061"))
    
    # Награды (настраиваются админом)
    REFERRAL_REWARD = 300  # Награда за реферала
    JOIN_REWARD = 200      # Награда за переход по ссылке
    MIN_WITHDRAWAL = 5000  # Минимальный вывод
    
    # Настройки изображений
    BALANCE_IMAGE = "https://disk.yandex.ru/i/JT8xfr8dWFmVmw"
