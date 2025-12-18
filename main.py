import os
import logging
import asyncio
from typing import Dict, List, Optional
from datetime import datetime

from telegram import (
    Update, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    ChatMember,
    InputMediaPhoto
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    ContextTypes, 
    filters
)
from telegram.constants import ParseMode

import psycopg2
from psycopg2.extras import RealDictCursor

# ========== КОНФИГУРАЦИЯ ==========
TOKEN = "8126450707:AAHmAGcyS76RImXRQ6WJBgMxF3JPPl4sduY"
BOT_USERNAME = "@elon_ref_bot"
OWNER_ID = 7433757951
CHANNEL_USERNAME = "@cosinxx_prime"
CHANNEL_LINK = "https://t.me/cosinxx_prime"

# Настройки золота
GOLD_PER_REFERRAL = 300
GOLD_PER_JOIN = 200
MIN_WITHDRAWAL = 5000

# Настройки базы данных (для Railway)
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/referral_bot')

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== БАЗА ДАННЫХ ==========
def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_database():
    """Инициализация таблиц в базе данных"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Таблица пользователей
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username VARCHAR(255),
            first_name VARCHAR(255),
            last_name VARCHAR(255),
            referrer_id BIGINT,
            gold INTEGER DEFAULT 0,
            total_earned INTEGER DEFAULT 0,
            referrals_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            joined_channel BOOLEAN DEFAULT FALSE
        )
    ''')
    
    # Таблица транзакций
    cur.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            amount INTEGER,
            type VARCHAR(50),
            description VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица выводов
    cur.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            amount INTEGER,
            status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица настроек (для админа)
    cur.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key VARCHAR(50) PRIMARY KEY,
            value VARCHAR(255)
        )
    ''')
    
    # Начальные настройки
    cur.execute('''
        INSERT INTO settings (key, value) 
        VALUES ('gold_per_referral', %s)
        ON CONFLICT (key) DO NOTHING
    ''', (str(GOLD_PER_REFERRAL),))
    
    cur.execute('''
        INSERT INTO settings (key, value) 
        VALUES ('gold_per_join', %s)
        ON CONFLICT (key) DO NOTHING
    ''', (str(GOLD_PER_JOIN),))
    
    conn.commit()
    cur.close()
    conn.close()

# ========== ФУНКЦИИ БАЗЫ ДАННЫХ ==========
def get_user(user_id: int):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

def create_user(user_id: int, username: str, first_name: str, last_name: str, referrer_id: Optional[int] = None):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO users (user_id, username, first_name, last_name, referrer_id) 
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
        username = EXCLUDED.username,
        first_name = EXCLUDED.first_name,
        last_name = EXCLUDED.last_name
    ''', (user_id, username, first_name, last_name, referrer_id))
    conn.commit()
    cur.close()
    conn.close()

def add_gold(user_id: int, amount: int, transaction_type: str, description: str):
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Обновляем баланс
    cur.execute('''
        UPDATE users 
        SET gold = gold + %s, total_earned = total_earned + %s 
        WHERE user_id = %s
    ''', (amount, amount if amount > 0 else 0, user_id))
    
    # Записываем транзакцию
    cur.execute('''
        INSERT INTO transactions (user_id, amount, type, description)
        VALUES (%s, %s, %s, %s)
    ''', (user_id, amount, transaction_type, description))
    
    conn.commit()
    cur.close()
    conn.close()

def update_referrals_count(user_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        UPDATE users 
        SET referrals_count = referrals_count + 1 
        WHERE user_id = %s
    ''', (user_id,))
    conn.commit()
    cur.close()
    conn.close()

def set_joined_channel(user_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('UPDATE users SET joined_channel = TRUE WHERE user_id = %s', (user_id,))
    conn.commit()
    cur.close()
    conn.close()

def create_withdrawal(user_id: int, amount: int):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO withdrawals (user_id, amount) VALUES (%s, %s)', (user_id, amount))
    conn.commit()
    cur.close()
    conn.close()

def get_settings():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM settings')
    settings = {row['key']: row['value'] for row in cur.fetchall()}
    cur.close()
    conn.close()
    return settings

def update_setting(key: str, value: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO settings (key, value) 
        VALUES (%s, %s)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
    ''', (key, value))
    conn.commit()
    cur.close()
    conn.close()

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("👥 Пригласить друзей", callback_data="invite")],
        [InlineKeyboardButton("💰 Вывести голду", callback_data="withdraw")],
        [InlineKeyboardButton("📊 Топ рефералов", callback_data="top")],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_invite_keyboard(user_id: int) -> InlineKeyboardMarkup:
    referral_link = f"https://t.me/{BOT_USERNAME[1:]}?start={user_id}"
    keyboard = [
        [InlineKeyboardButton("📢 Поделиться ссылкой", 
         url=f"https://t.me/share/url?url={referral_link}&text=Присоединяйся%20к%20моему%20проекту%20и%20зарабатывай%20голду!")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_withdraw_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(f"💳 Вывести от {MIN_WITHDRAWAL} голды", callback_data=f"withdraw_{MIN_WITHDRAWAL}")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("⚙️ Настройки", callback_data="admin_settings")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("◀️ Назад", callback_data="back")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_settings_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("✏️ Голда за реферала", callback_data="set_referral")],
        [InlineKeyboardButton("✏️ Голда за вступление", callback_data="set_join")],
        [InlineKeyboardButton("◀️ Назад к админке", callback_data="admin_back")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    user_id = user.id
    
    # Получаем параметр реферала
    args = context.args
    referrer_id = int(args[0]) if args else None
    
    # Проверяем подписку на канал
    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        has_subscription = member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except:
        has_subscription = False
    
    # Создаем или обновляем пользователя
    create_user(user_id, user.username, user.first_name, user.last_name, referrer_id)
    
    # Если есть реферал и пользователь новый (впервые запускает бота)
    if referrer_id and referrer_id != user_id:
        referrer = get_user(referrer_id)
        if referrer:
            # Начисляем голду рефереру
            settings = get_settings()
            gold_amount = int(settings.get('gold_per_referral', GOLD_PER_REFERRAL))
            
            add_gold(referrer_id, gold_amount, "referral", f"Реферал: {user.username or user_id}")
            update_referrals_count(referrer_id)
            
            # Уведомляем реферера
            try:
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text=f"🎉 Новый реферал!\n"
                         f"Пользователь @{user.username or user.first_name} присоединился по вашей ссылке.\n"
                         f"📈 Начислено: +{gold_amount} голды"
                )
            except:
                pass
    
    # Начисляем голду за вступление в канал
    if has_subscription:
        db_user = get_user(user_id)
        if not db_user['joined_channel']:
            settings = get_settings()
            join_gold = int(settings.get('gold_per_join', GOLD_PER_JOIN))
            
            add_gold(user_id, join_gold, "channel_join", "Вступление в канал")
            set_joined_channel(user_id)
    
    # Отправляем основное сообщение с фотографией
    caption = f"👋 Привет, {user.first_name}!\n\n"
    
    if not has_subscription:
        caption += f"⚠️ Для доступа к боту необходимо подписаться на канал: {CHANNEL_LINK}\n\n"
        caption += "После подписки нажмите /start"
        
        keyboard = [[InlineKeyboardButton("📢 Подписаться на канал", url=CHANNEL_LINK)]]
        await update.message.reply_photo(
            photo="https://disk.yandex.ru/i/JT8xfr8dWFmVmw",
            caption=caption,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Если подписка есть, показываем основной интерфейс
    db_user = get_user(user_id)
    
    caption += f"💰 Баланс: {db_user['gold']} голды\n"
    caption += f"👥 Рефералов: {db_user['referrals_count']}\n"
    caption += f"🎯 Всего заработано: {db_user['total_earned']} голды\n\n"
    caption += "Используй кнопки ниже для управления:"
    
    await update.message.reply_photo(
        photo="https://disk.yandex.ru/i/JT8xfr8dWFmVmw",
        caption=caption,
        reply_markup=get_main_keyboard()
    )

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает баланс пользователя"""
    user = update.effective_user
    db_user = get_user(user.id)
    
    if not db_user:
        await update.message.reply_text("Сначала используйте /start")
        return
    
    text = f"💰 Ваш баланс: {db_user['gold']} голды\n"
    text += f"👥 Приглашено друзей: {db_user['referrals_count']}\n"
    text += f"🎯 Всего заработано: {db_user['total_earned']} голды\n\n"
    
    if db_user['gold'] >= MIN_WITHDRAWAL:
        text += f"✅ Вы можете вывести от {MIN_WITHDRAWAL} голды"
    else:
        text += f"❌ Для вывода необходимо минимум {MIN_WITHDRAWAL} голды"
    
    await update.message.reply_text(text, reply_markup=get_withdraw_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда помощи"""
    text = "📚 *Помощь по боту*\n\n"
    text += "🎯 *Как зарабатывать голду?*\n"
    text += "1. Приглашайте друзей по реферальной ссылке\n"
    text += "2. Каждый приглашенный друг принесет вам голду\n"
    text += "3. Новые пользователи также получают голду за вступление в канал\n\n"
    text += "💰 *Вывод голды*\n"
    text += f"- Минимальная сумма вывода: {MIN_WITHDRAWAL} голды\n"
    text += "- Вывод осуществляется на указанные реквизиты\n\n"
    text += "⚡ *Быстрые команды:*\n"
    text += "/start - Запустить бота\n"
    text += "/balance - Показать баланс\n"
    text += "/help - Эта справка"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

# ========== ADMIN COMMANDS ==========
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ панель"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ У вас нет доступа к этой команде")
        return
    
    text = "⚡ *Админ панель*\n\n"
    text += "Выберите действие:"
    
    await update.message.reply_text(
        text, 
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_admin_keyboard()
    )

async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика бота для админа"""
    if update.effective_user.id != OWNER_ID:
        return
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Общая статистика
    cur.execute('SELECT COUNT(*) as total_users FROM users')
    total_users = cur.fetchone()['total_users']
    
    cur.execute('SELECT SUM(gold) as total_gold FROM users')
    total_gold = cur.fetchone()['total_gold'] or 0
    
    cur.execute('SELECT SUM(total_earned) as total_earned FROM users')
    total_earned = cur.fetchone()['total_earned'] or 0
    
    # Топ рефералов
    cur.execute('''
        SELECT username, referrals_count, total_earned 
        FROM users 
        WHERE referrals_count > 0 
        ORDER BY referrals_count DESC 
        LIMIT 10
    ''')
    top_referrers = cur.fetchall()
    
    cur.close()
    conn.close()
    
    # Формируем сообщение
    text = f"📊 *Статистика бота*\n\n"
    text += f"👥 Всего пользователей: {total_users}\n"
    text += f"💰 Всего голды в системе: {total_gold}\n"
    text += f"🎯 Всего выдано голды: {total_earned}\n\n"
    
    if top_referrers:
        text += "🏆 *Топ 10 рефералов:*\n"
        for i, user in enumerate(top_referrers, 1):
            username = user['username'] or f"ID:{user['user_id']}"
            text += f"{i}. @{username} - {user['referrals_count']} реф. ({user['total_earned']} голды)\n"
    
    await update.callback_query.message.edit_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]])
    )

# ========== CALLBACK HANDLERS ==========
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик inline кнопок"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data
    
    # Проверяем подписку
    try:
        member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        has_subscription = member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]
    except:
        has_subscription = False
    
    if not has_subscription and not callback_data.startswith("admin"):
        await query.edit_message_caption(
            caption=f"⚠️ Для доступа к боту необходимо подписаться на канал: {CHANNEL_LINK}\n\nПосле подписки нажмите /start",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📢 Подписаться на канал", url=CHANNEL_LINK)]])
        )
        return
    
    if callback_data == "back":
        # Возврат в главное меню
        db_user = get_user(user_id)
        caption = f"💰 Баланс: {db_user['gold']} голды\n"
        caption += f"👥 Рефералов: {db_user['referrals_count']}\n"
        caption += f"🎯 Всего заработано: {db_user['total_earned']} голды\n\n"
        caption += "Используй кнопки ниже для управления:"
        
        await query.edit_message_caption(
            caption=caption,
            reply_markup=get_main_keyboard()
        )
    
    elif callback_data == "invite":
        # Приглашение друзей
        db_user = get_user(user_id)
        referral_link = f"https://t.me/{BOT_USERNAME[1:]}?start={user_id}"
        
        text = f"👥 *Пригласить друзей*\n\n"
        text += f"🔗 Ваша реферальная ссылка:\n`{referral_link}`\n\n"
        text += f"💰 За каждого приглашенного друга вы получите {GOLD_PER_REFERRAL} голды\n"
        text += f"🎁 Ваш друг получит {GOLD_PER_JOIN} голды за вступление в канал\n\n"
        text += f"👥 Приглашено: {db_user['referrals_count']} друзей\n"
        text += f"🎯 Заработано с рефералов: {db_user['total_earned']} голды"
        
        await query.edit_message_caption(
            caption=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_invite_keyboard(user_id)
        )
    
    elif callback_data == "withdraw":
        # Вывод голды
        db_user = get_user(user_id)
        
        text = f"💰 *Вывод голды*\n\n"
        text += f"📊 Ваш баланс: {db_user['gold']} голды\n"
        text += f"💳 Минимальная сумма вывода: {MIN_WITHDRAWAL} голды\n\n"
        
        if db_user['gold'] >= MIN_WITHDRAWAL:
            text += "✅ Вы можете вывести голду!\n"
            text += "📝 Для вывода напишите @cosinxx_prime"
        else:
            text += f"❌ Недостаточно голды для вывода\n"
            text += f"🔢 Необходимо еще {MIN_WITHDRAWAL - db_user['gold']} голды"
        
        await query.edit_message_caption(
            caption=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_withdraw_keyboard()
        )
    
    elif callback_data.startswith("withdraw_"):
        # Обработка вывода
        amount = int(callback_data.split("_")[1])
        db_user = get_user(user_id)
        
        if db_user['gold'] >= amount:
            # Создаем заявку на вывод
            create_withdrawal(user_id, amount)
            
            # Списание голды
            add_gold(user_id, -amount, "withdrawal", "Вывод голды")
            
            text = f"✅ Заявка на вывод {amount} голды создана!\n\n"
            text += "📞 Свяжитесь с @cosinxx_prime для получения средств"
            
            # Уведомляем админа
            try:
                await context.bot.send_message(
                    chat_id=OWNER_ID,
                    text=f"📤 Новая заявка на вывод!\n\n"
                         f"👤 Пользователь: @{query.from_user.username or query.from_user.id}\n"
                         f"💰 Сумма: {amount} голды\n"
                         f"📊 Баланс после: {db_user['gold'] - amount} голды"
                )
            except:
                pass
        else:
            text = f"❌ Недостаточно голды!\n"
            text += f"💰 Ваш баланс: {db_user['gold']} голды\n"
            text += f"🔢 Требуется: {amount} голды"
        
        await query.edit_message_caption(
            caption=text,
            reply_markup=get_withdraw_keyboard()
        )
    
    elif callback_data == "top":
        # Топ рефералов
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute('''
            SELECT username, referrals_count, total_earned 
            FROM users 
            WHERE referrals_count > 0 
            ORDER BY referrals_count DESC 
            LIMIT 10
        ''')
        top_users = cur.fetchall()
        
        cur.close()
        conn.close()
        
        text = "🏆 *Топ рефералов*\n\n"
        
        if top_users:
            for i, user in enumerate(top_users, 1):
                username = user['username'] or "Аноним"
                text += f"{i}. @{username}\n"
                text += f"   👥 {user['referrals_count']} реф. | 💰 {user['total_earned']} голды\n\n"
        else:
            text += "Пока нет активных рефералов\n"
            text += "Станьте первым!\n\n"
        
        text += "💡 *Как попасть в топ?*\n"
        text += "Приглашайте друзей и зарабатывайте голду!"
        
        await query.edit_message_caption(
            caption=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back")]])
        )
    
    elif callback_data == "help":
        # Помощь
        text = "📚 *Помощь по боту*\n\n"
        text += "🎯 *Как зарабатывать голду?*\n"
        text += "1. Приглашайте друзей по реферальной ссылке\n"
        text += "2. Каждый приглашенный друг принесет вам голду\n"
        text += "3. Новые пользователи также получают голду за вступление в канал\n\n"
        text += "💰 *Вывод голды*\n"
        text += f"- Минимальная сумма вывода: {MIN_WITHDRAWAL} голды\n"
        text += "- Вывод осуществляется на указанные реквизиты\n\n"
        text += "⚡ *Быстрые команды:*\n"
        text += "/start - Запустить бота\n"
        text += "/balance - Показать баланс\n"
        text += "/help - Эта справка"
        
        await query.edit_message_caption(
            caption=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back")]])
        )
    
    elif callback_data == "admin_settings":
        # Настройки админа
        if user_id != OWNER_ID:
            return
        
        settings = get_settings()
        
        text = "⚙️ *Настройки бота*\n\n"
        text += f"💰 Голда за реферала: {settings.get('gold_per_referral', GOLD_PER_REFERRAL)}\n"
        text += f"🎁 Голда за вступление: {settings.get('gold_per_join', GOLD_PER_JOIN)}\n"
        text += f"💳 Мин. вывод: {MIN_WITHDRAWAL}\n\n"
        text += "Выберите параметр для изменения:"
        
        await query.edit_message_caption(
            caption=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_settings_keyboard()
        )
    
    elif callback_data == "set_referral":
        # Изменение голды за реферала
        if user_id != OWNER_ID:
            return
        
        text = "✏️ *Изменение голды за реферала*\n\n"
        text += "Введите новое количество голды (только число):"
        
        await query.edit_message_caption(
            caption=text,
            parse_mode=ParseMode.MARKDOWN
        )
        context.user_data['awaiting_setting'] = 'gold_per_referral'
    
    elif callback_data == "set_join":
        # Изменение голды за вступление
        if user_id != OWNER_ID:
            return
        
        text = "✏️ *Изменение голды за вступление*\n\n"
        text += "Введите новое количество голды (только число):"
        
        await query.edit_message_caption(
            caption=text,
            parse_mode=ParseMode.MARKDOWN
        )
        context.user_data['awaiting_setting'] = 'gold_per_join'
    
    elif callback_data == "admin_back":
        # Назад в админ панель
        if user_id != OWNER_ID:
            return
        
        text = "⚡ *Админ панель*\n\n"
        text += "Выберите действие:"
        
        await query.edit_message_caption(
            caption=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_keyboard()
        )
    
    elif callback_data == "admin_stats":
        # Статистика админа
        await admin_stats_command(update, context)

# ========== ОБРАБОТЧИК СООБЩЕНИЙ ==========
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений"""
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # Проверяем, ожидаем ли мы настройку от админа
    if user_id == OWNER_ID and 'awaiting_setting' in context.user_data:
        setting_key = context.user_data.pop('awaiting_setting', None)
        
        if setting_key and message_text.isdigit():
            new_value = int(message_text)
            update_setting(setting_key, str(new_value))
            
            text = f"✅ Настройка обновлена!\n"
            
            if setting_key == 'gold_per_referral':
                text += f"Голда за реферала изменена на: {new_value}"
            elif setting_key == 'gold_per_join':
                text += f"Голда за вступление изменена на: {new_value}"
            
            await update.message.reply_text(
                text,
                reply_markup=get_settings_keyboard()
            )
            return
    
    # Обычное сообщение - перенаправляем в главное меню
    await start_command(update, context)

# ========== ОШИБКИ ==========
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")
    
    if update and update.effective_user:
        try:
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text="⚠️ Произошла ошибка. Пожалуйста, попробуйте еще раз."
            )
        except:
            pass

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
def main():
    """Запуск бота"""
    # Инициализация базы данных
    init_database()
    
    # Создание приложения
    app = Application.builder().token(TOKEN).build()
    
    # Регистрация обработчиков команд
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin_command))
    
    # Регистрация обработчиков кнопок
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # Регистрация обработчика сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Регистрация обработчика ошибок
    app.add_error_handler(error_handler)
    
    # Запуск бота
    print(f"🤖 Бот запущен: @{BOT_USERNAME[1:]}")
    print(f"👑 Владелец: {OWNER_ID}")
    print(f"📢 Канал: {CHANNEL_USERNAME}")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
