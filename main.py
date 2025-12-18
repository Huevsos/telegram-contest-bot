import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Настройка базы данных (используем SQLite для простоты)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///referral.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)

# Модель пользователя
class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    referral_code = Column(String, unique=True)
    referred_by = Column(String, nullable=True)
    balance = Column(Integer, default=0)
    referrals_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# Создаем таблицы
Base.metadata.create_all(bind=engine)

# Конфигурация
REFERRAL_BONUS = 50  # Бонус за приглашение
WELCOME_BONUS = 10   # Бонус новому пользователю

def generate_referral_code(user_id: int) -> str:
    """Генерация уникального реферального кода"""
    import hashlib
    return hashlib.md5(f"referral_{user_id}_{datetime.now().timestamp()}".encode()).hexdigest()[:8]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_data = update.effective_user
    referral_code = None
    
    # Проверяем, есть ли реферальный код в аргументах
    if context.args:
        referral_code = context.args[0]
    
    db = SessionLocal()
    
    try:
        # Проверяем, есть ли пользователь в базе
        user = db.query(User).filter(User.telegram_id == user_data.id).first()
        
        if not user:
            # Создаем нового пользователя
            referral_code_new = generate_referral_code(user_data.id)
            user = User(
                telegram_id=user_data.id,
                username=user_data.username,
                first_name=user_data.first_name,
                last_name=user_data.last_name,
                referral_code=referral_code_new
            )
            
            # Если есть реферальный код, находим пригласившего
            if referral_code:
                referrer = db.query(User).filter(User.referral_code == referral_code).first()
                if referrer:
                    user.referred_by = referrer.telegram_id
                    referrer.balance += REFERRAL_BONUS
                    referrer.referrals_count += 1
                    user.balance += WELCOME_BONUS
            
            db.add(user)
            db.commit()
            
            welcome_text = f"""
👋 Привет, {user_data.first_name}!

🎉 Добро пожаловать в нашего бота!
💰 Твой баланс: {user.balance} баллов

📋 Доступные команды:
/start - Начало работы
/profile - Мой профиль
/referral - Моя реферальная ссылка
/balance - Мой баланс
            """
            
            if referral_code:
                welcome_text += f"\n✅ Ты зарегистрировался по реферальной ссылке!"
            
        else:
            welcome_text = f"""
👋 С возвращением, {user_data.first_name}!

📋 Доступные команды:
/profile - Мой профиль
/referral - Моя реферальная ссылка
/balance - Мой баланс
            """
        
        await update.message.reply_text(welcome_text)
        
    except Exception as e:
        logger.error(f"Error in start command: {e}")
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте позже.")
    finally:
        db.close()

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать профиль пользователя"""
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == update.effective_user.id).first()
    
    if user:
        profile_text = f"""
📊 Ваш профиль:

👤 Имя: {user.first_name} {user.last_name or ''}
🆔 ID: {user.telegram_id}
💰 Баланс: {user.balance} баллов
👥 Приглашено друзей: {user.referrals_count}
🔗 Реферальный код: {user.referral_code}
📅 Дата регистрации: {user.created_at.strftime('%d.%m.%Y')}
        """
        
        keyboard = [
            [InlineKeyboardButton("📢 Поделиться ссылкой", 
                                 switch_inline_query=f"Присоединяйся! Используй мой код: {user.referral_code}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(profile_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text("Пользователь не найден. Используйте /start")
    
    db.close()

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать реферальную ссылку"""
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == update.effective_user.id).first()
    
    if user:
        bot_username = (await context.bot.get_me()).username
        referral_link = f"https://t.me/{bot_username}?start={user.referral_code}"
        
        referral_text = f"""
🎯 Ваша реферальная система:

🔗 Ваша ссылка:
{referral_link}

🔢 Ваш код:
`{user.referral_code}`

💰 Награды:
• Вы получаете: {REFERRAL_BONUS} баллов за каждого приглашенного
• Друг получает: {WELCOME_BONUS} баллов при регистрации

📢 Поделитесь ссылкой с друзьями и получайте бонусы!
        """
        
        keyboard = [
            [InlineKeyboardButton("🔗 Поделиться ссылкой", url=f"tg://msg_url?url={referral_link}&text=Присоединяйся%20к%20нам!")],
            [InlineKeyboardButton("📋 Мой профиль", callback_data="profile")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(referral_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text("Пользователь не найден. Используйте /start")
    
    db.close()

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать баланс"""
    db = SessionLocal()
    user = db.query(User).filter(User.telegram_id == update.effective_user.id).first()
    
    if user:
        balance_text = f"""
💰 Ваш баланс: {user.balance} баллов

🎁 Вы пригласили: {user.referrals_count} друзей
📈 Всего заработано: {user.referrals_count * REFERRAL_BONUS} баллов

💡 Приглашайте друзей и получайте бонусы!
        """
        await update.message.reply_text(balance_text)
    else:
        await update.message.reply_text("Пользователь не найден. Используйте /start")
    
    db.close()

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "profile":
        await profile(update, context)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика (только для админа)"""
    admin_id = os.getenv("ADMIN_ID")
    if not admin_id or str(update.effective_user.id) != admin_id:
        await update.message.reply_text("Эта команда доступна только администратору.")
        return
    
    db = SessionLocal()
    total_users = db.query(User).count()
    total_referrals = db.query(User).filter(User.referrals_count > 0).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    
    stats_text = f"""
📊 Статистика бота:

👥 Всего пользователей: {total_users}
✅ Активных пользователей: {active_users}
👥 Пользователей с рефералами: {total_referrals}
📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}
        """
    
    await update.message.reply_text(stats_text)
    db.close()

def main():
    """Запуск бота"""
    # Получаем токен из переменных окружения
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        raise ValueError("Не установлен TELEGRAM_BOT_TOKEN")
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("referral", referral))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Запускаем бота
    port = int(os.getenv("PORT", 8443))
    
    if os.getenv("RAILWAY_ENVIRONMENT"):
        # На Railway
        webhook_url = os.getenv("RAILWAY_STATIC_URL", "")
        if webhook_url:
            application.run_webhook(
                listen="0.0.0.0",
                port=port,
                url_path=TOKEN,
                webhook_url=f"{webhook_url}/{TOKEN}"
            )
        else:
            application.run_polling()
    else:
        # Локально
        application.run_polling()

if __name__ == '__main__':
    main()
