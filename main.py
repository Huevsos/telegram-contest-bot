import asyncio
import logging
import os
from datetime import datetime
from typing import Optional
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, URLInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import asyncpg

from config import Config

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=Config.BOT_TOKEN)
dp = Dispatcher()

# ========== СОСТОЯНИЯ ДЛЯ FSM ==========

class WithdrawalStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_skin_photo = State()
    waiting_for_market_link = State()
    confirm_withdrawal = State()

class AdminStates(StatesGroup):
    waiting_for_referral_reward = State()
    waiting_for_join_reward = State()
    waiting_for_min_withdrawal = State()

# ========== БАЗА ДАННЫХ ==========

async def init_db():
    """Инициализация базы данных"""
    conn = await asyncpg.connect(Config.DATABASE_URL)
    
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            referrals INTEGER DEFAULT 0,
            gold INTEGER DEFAULT 0,
            referrer_id BIGINT,
            is_subscribed BOOLEAN DEFAULT FALSE,
            last_check TIMESTAMP,
            FOREIGN KEY (referrer_id) REFERENCES users(user_id)
        )
    ''')
    
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS referral_stats (
            id SERIAL PRIMARY KEY,
            referrer_id BIGINT,
            referred_id BIGINT,
            referred_username TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            gold_awarded INTEGER DEFAULT 300,
            FOREIGN KEY (referrer_id) REFERENCES users(user_id),
            FOREIGN KEY (referred_id) REFERENCES users(user_id)
        )
    ''')
    
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            username TEXT,
            amount INTEGER,
            commission INTEGER DEFAULT 15,
            final_amount INTEGER,
            skin_photo TEXT,
            market_link TEXT,
            status TEXT DEFAULT 'pending',
            request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_date TIMESTAMP,
            admin_id BIGINT,
            admin_comment TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS reward_settings (
            id SERIAL PRIMARY KEY,
            referral_reward INTEGER DEFAULT 300,
            join_reward INTEGER DEFAULT 200,
            min_withdrawal INTEGER DEFAULT 5000,
            updated_by BIGINT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    settings = await conn.fetchrow('SELECT * FROM reward_settings LIMIT 1')
    if not settings:
        await conn.execute('''
            INSERT INTO reward_settings (referral_reward, join_reward, min_withdrawal, updated_by)
            VALUES ($1, $2, $3, $4)
        ''', Config.REFERRAL_REWARD, Config.JOIN_REWARD, Config.MIN_WITHDRAWAL, Config.OWNER_ID)
    
    await conn.close()
    logger.info("База данных инициализирована")

async def get_db():
    """Получение соединения с БД"""
    return await asyncpg.connect(Config.DATABASE_URL)

async def get_reward_settings():
    """Получение текущих настроек наград"""
    conn = await get_db()
    settings = await conn.fetchrow('SELECT * FROM reward_settings ORDER BY id DESC LIMIT 1')
    await conn.close()
    return settings

async def check_subscription(user_id: int) -> bool:
    """Проверка подписки на канал"""
    try:
        member = await bot.get_chat_member(Config.CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return False

async def get_or_create_user(user_id, username=None, full_name=None, referrer_id=None):
    """Получение или создание пользователя"""
    conn = await get_db()
    
    settings = await get_reward_settings()
    
    user = await conn.fetchrow(
        'SELECT * FROM users WHERE user_id = $1',
        user_id
    )
    
    if not user:
        is_subscribed = await check_subscription(user_id)
        
        await conn.execute('''
            INSERT INTO users (user_id, username, full_name, referrer_id, is_subscribed)
            VALUES ($1, $2, $3, $4, $5)
        ''', user_id, username, full_name, referrer_id, is_subscribed)
        
        if referrer_id and referrer_id != user_id and is_subscribed:
            await conn.execute('''
                UPDATE users 
                SET referrals = referrals + 1, 
                    gold = gold + $1
                WHERE user_id = $2
            ''', settings['referral_reward'], referrer_id)
            
            await conn.execute('''
                INSERT INTO referral_stats (referrer_id, referred_id, referred_username, gold_awarded)
                VALUES ($1, $2, $3, $4)
            ''', referrer_id, user_id, username, settings['referral_reward'])
            
            await conn.execute('''
                UPDATE users 
                SET gold = gold + $1
                WHERE user_id = $2
            ''', settings['join_reward'], user_id)
    
    user = await conn.fetchrow(
        'SELECT * FROM users WHERE user_id = $1',
        user_id
    )
    
    await conn.close()
    return user

async def update_user_subscription(user_id, status):
    """Обновление статуса подписки"""
    conn = await get_db()
    await conn.execute(
        'UPDATE users SET is_subscribed = $1, last_check = CURRENT_TIMESTAMP WHERE user_id = $2',
        status, user_id
    )
    await conn.close()

async def get_user_referrals(user_id):
    """Получение рефералов пользователя"""
    conn = await get_db()
    referrals = await conn.fetch(
        '''
        SELECT rs.*, u.username, u.full_name 
        FROM referral_stats rs
        LEFT JOIN users u ON rs.referred_id = u.user_id
        WHERE rs.referrer_id = $1
        ORDER BY rs.date DESC
        ''',
        user_id
    )
    await conn.close()
    return referrals

async def get_pending_withdrawals():
    """Получение ожидающих выводов"""
    conn = await get_db()
    withdrawals = await conn.fetch(
        '''
        SELECT w.*, u.username, u.full_name 
        FROM withdrawals w
        LEFT JOIN users u ON w.user_id = u.user_id
        WHERE w.status = 'pending'
        ORDER BY w.request_date
        '''
    )
    await conn.close()
    return withdrawals

async def update_withdrawal_status(withdrawal_id, status, admin_id=None, comment=None):
    """Обновление статуса вывода"""
    conn = await get_db()
    
    if status == 'approved':
        await conn.execute('''
            UPDATE withdrawals 
            SET status = $1, processed_date = CURRENT_TIMESTAMP, 
                admin_id = $2, admin_comment = $3
            WHERE id = $4
        ''', status, admin_id, comment, withdrawal_id)
        
        withdrawal = await conn.fetchrow(
            'SELECT user_id, amount FROM withdrawals WHERE id = $1',
            withdrawal_id
        )
        
        if withdrawal:
            await conn.execute('''
                UPDATE users SET gold = gold - $1 WHERE user_id = $2
            ''', withdrawal['amount'], withdrawal['user_id'])
    
    elif status == 'rejected':
        await conn.execute('''
            UPDATE withdrawals 
            SET status = $1, processed_date = CURRENT_TIMESTAMP, 
                admin_id = $2, admin_comment = $3
            WHERE id = $4
        ''', status, admin_id, comment, withdrawal_id)
    
    await conn.close()
    return True

# ========== КЛАВИАТУРЫ ==========

def get_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👥 Мои рефералы", callback_data="my_referrals"),
        InlineKeyboardButton(text="💰 Баланс", callback_data="balance")
    )
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="stats"),
        InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")
    )
    builder.row(
        InlineKeyboardButton(text="🎁 Реф. ссылка", callback_data="ref_link"),
        InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_subscription")
    )
    return builder.as_markup()

def get_withdrawal_keyboard(user_gold, min_withdrawal):
    builder = InlineKeyboardBuilder()
    if user_gold >= min_withdrawal:
        builder.row(
            InlineKeyboardButton(text="💳 Вывести от 5000 голды", callback_data="withdraw_start")
        )
    builder.row(
        InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
        InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")
    )
    return builder.as_markup()

def get_admin_withdrawal_keyboard(withdrawal_id):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"admin_approve_{withdrawal_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_reject_{withdrawal_id}")
    )
    builder.row(
        InlineKeyboardButton(text="📋 Все заявки", callback_data="admin_withdrawals")
    )
    return builder.as_markup()

# ========== ПРОВЕРКА ПОДПИСКИ ==========

async def check_subscription_middleware(user_id, message=None, callback=None):
    """Проверка подписки перед выполнением действий"""
    is_subscribed = await check_subscription(user_id)
    
    if not is_subscribed:
        keyboard = InlineKeyboardBuilder()
        keyboard.row(
            InlineKeyboardButton(
                text="📢 Подписаться на канал",
                url=f"https://t.me/{Config.REQUIRED_CHANNEL.replace('@', '')}"
            )
        )
        keyboard.row(
            InlineKeyboardButton(text="✅ Я подписался", callback_data="check_subscription")
        )
        
        text = f"""
⚠️ <b>Требуется подписка!</b>

Для использования бота необходимо подписаться на канал:
{Config.REQUIRED_CHANNEL}

После подписки нажмите кнопку "✅ Я подписался"
        """
        
        if message:
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard.as_markup())
        elif callback:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard.as_markup())
        
        await update_user_subscription(user_id, False)
        return False
    
    await update_user_subscription(user_id, True)
    return True

# ========== КОМАНДЫ ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    
    user_id = message.from_user.id
    args = message.text.split()
    
    referrer_id = None
    if len(args) > 1 and args[1].isdigit():
        referrer_id = int(args[1])
        logger.info(f"Пользователь {user_id} перешел по ссылке от {referrer_id}")
    
    user = await get_or_create_user(
        user_id=user_id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        referrer_id=referrer_id
    )
    
    if not await check_subscription_middleware(user_id, message=message):
        return
    
    settings = await get_reward_settings()
    if referrer_id and referrer_id != user_id and user['is_subscribed']:
        welcome_bonus_text = f"""
🎉 Вы перешли по реферальной ссылке!
➕ Получено: {settings['join_reward']} голды 🥇
👤 Пригласивший получает {settings['referral_reward']} голды
        """
        await message.answer(welcome_bonus_text, parse_mode="HTML")
    
    ref_link = f"https://t.me/{Config.BOT_USERNAME}?start={user_id}"
    
    welcome_text = f"""
🎉 Добро пожаловать, {message.from_user.full_name}!

🤖 <b>Elon Referral Bot</b>

📌 <b>Ваша реферальная ссылка:</b>
<code>{ref_link}</code>

💰 <b>Награды:</b>
• За реферала: {settings['referral_reward']} голды 🥇
• За переход по ссылке: {settings['join_reward']} голды 🥇
• Минимальный вывод: {settings['min_withdrawal']} голды 🥇

👇 <b>Используйте кнопки ниже:</b>
    """
    
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard())

@dp.message(Command("menu"))
async def cmd_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("📱 <b>Главное меню</b>", parse_mode="HTML", reply_markup=get_main_keyboard())

# ========== ОБРАБОТКА КНОПОК ==========

@dp.callback_query(F.data == "balance")
async def callback_balance(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if not await check_subscription_middleware(user_id, callback=callback):
        await callback.answer()
        return
    
    user = await get_or_create_user(user_id)
    settings = await get_reward_settings()
    
    try:
        photo = URLInputFile(Config.BALANCE_IMAGE)
        await bot.send_photo(
            chat_id=callback.message.chat.id,
            photo=photo,
            caption=f"""
💰 <b>Ваш баланс:</b> {user['gold']} голды 🥇

💳 <b>Доступно для вывода:</b> {user['gold']} голды 🥇
🎯 <b>Минимальный вывод:</b> {settings['min_withdrawal']} голды 🥇
📊 <b>Рефералов:</b> {user['referrals']}
            """,
            parse_mode="HTML",
            reply_markup=get_withdrawal_keyboard(user['gold'], settings['min_withdrawal'])
        )
    except Exception as e:
        logger.error(f"Ошибка загрузки изображения: {e}")
        text = f"""
💰 <b>Ваш баланс:</b> {user['gold']} голды 🥇

💳 <b>Доступно для вывода:</b> {user['gold']} голды 🥇
🎯 <b>Минимальный вывод:</b> {settings['min_withdrawal']} голды 🥇
📊 <b>Рефералов:</b> {user['referrals']}
        """
        await callback.message.answer(text, parse_mode="HTML", reply_markup=get_withdrawal_keyboard(user['gold'], settings['min_withdrawal']))
    
    await callback.answer()

@dp.callback_query(F.data == "stats")
async def callback_stats(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if not await check_subscription_middleware(user_id, callback=callback):
        await callback.answer()
        return
    
    user = await get_or_create_user(user_id)
    referrals = await get_user_referrals(user_id)
    settings = await get_reward_settings()
    
    text = f"""
📊 <b>Ваша статистика</b>

👤 <b>Профиль:</b>
• ID: {user_id}
• Имя: {user['full_name'] or 'Не указано'}
• Регистрация: {user['join_date'].strftime('%d.%m.%Y') if user['join_date'] else 'Неизвестно'}

💰 <b>Финансы:</b>
• Баланс: {user['gold']} голды 🥇
• Рефералов: {user['referrals']}
• Заработано на рефералах: {user['referrals'] * settings['referral_reward']} голды

👥 <b>Последние рефералы:</b>
"""
    
    if referrals:
        for i, ref in enumerate(referrals[:5], 1):
            username = f"@{ref['referred_username']}" if ref['referred_username'] else f"ID:{ref['referred_id']}"
            date = ref['date'].strftime("%d.%m") if ref['date'] else "??.??"
            text += f"{i}. {username} - {date} (+{ref['gold_awarded']} 🥇)\n"
    else:
        text += "\n<i>Рефералов пока нет</i>\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
        InlineKeyboardButton(text="👥 Рефералы", callback_data="my_referrals")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")
    )
    
    await callback.message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "help")
async def callback_help(callback: types.CallbackQuery):
    settings = await get_reward_settings()
    
    text = f"""
ℹ️ <b>Помощь по боту</b>

🤖 <b>Как работает бот:</b>
1. Получите реферальную ссылку
2. Приглашайте друзей по ссылке
3. Получайте {settings['referral_reward']} голды за каждого реферала
4. Ваши друзья получают {settings['join_reward']} голды за регистрацию
5. Выводите голды

💰 <b>Вывод средств:</b>
• Минимальная сумма: {settings['min_withdrawal']} голды 🥇
• Комиссия рынка: {Config.MARKET_COMMISSION}%
• При выводе укажите скин и ссылку на рынок
• После одобрения админа ожидайте оплату

👥 <b>Реферальная система:</b>
• За каждого реферала: {settings['referral_reward']} 🥇
• За переход по ссылке: {settings['join_reward']} 🥇

⚠️ <b>Важно:</b>
• Обязательна подписка на канал {Config.REQUIRED_CHANNEL}
• Для вывода нужен активный баланс
• Заявки обрабатываются вручную администратором

📞 <b>Поддержка:</b>
По вопросам обращайтесь к @cosinxx_prime
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
        InlineKeyboardButton(text="🎁 Реф. ссылка", callback_data="ref_link")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")
    )
    
    await callback.message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "my_referrals")
async def callback_my_referrals(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if not await check_subscription_middleware(user_id, callback=callback):
        await callback.answer()
        return
    
    user = await get_or_create_user(user_id)
    referrals = await get_user_referrals(user_id)
    settings = await get_reward_settings()
    
    text = f"""
👥 <b>Мои рефералы</b>

📊 <b>Всего приглашено:</b> {user['referrals']}
💰 <b>Заработано:</b> {user['referrals'] * settings['referral_reward']} голды 🥇

📋 <b>Список рефералов:</b>
"""
    
    if referrals:
        for i, ref in enumerate(referrals, 1):
            username = f"@{ref['referred_username']}" if ref['referred_username'] else f"ID: {ref['referred_id']}"
            date = ref['date'].strftime("%d.%m.%Y") if ref['date'] else "??.??.????"
            text += f"{i}. {username} - {date}\n"
    else:
        text += "\n<i>У вас еще нет рефералов</i>\n"
    
    ref_link = f"https://t.me/{Config.BOT_USERNAME}?start={user_id}"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📢 Поделиться ссылкой",
            url=f"https://t.me/share/url?url={ref_link}&text=Присоединяйся%20к%20Elon%20Referral%20Bot!%20Зарабатывай%20голду!%20🥇"
        )
    )
    builder.row(
        InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
        InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")
    )
    
    await callback.message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "ref_link")
async def callback_ref_link(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    if not await check_subscription_middleware(user_id, callback=callback):
        await callback.answer()
        return
    
    user = await get_or_create_user(user_id)
    ref_link = f"https://t.me/{Config.BOT_USERNAME}?start={user_id}"
    
    text = f"""
🎁 <b>Реферальная ссылка</b>

📌 <b>Ваша ссылка:</b>
<code>{ref_link}</code>

📊 <b>Статистика:</b>
• Приглашено: {user['referrals']}
• Баланс: {user['gold']} голды 🥇
• Заработано на рефералах: {user['referrals'] * 300} голды 🥇

📢 <b>Делитесь ссылкой и зарабатывайте!</b>
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📱 Поделиться",
            url=f"https://t.me/share/url?url={ref_link}&text=Присоединяйся%20к%20Elon%20Referral%20Bot!%20Зарабатывай%20голду!%20🥇"
        )
    )
    builder.row(
        InlineKeyboardButton(text="👥 Мои рефералы", callback_data="my_referrals"),
        InlineKeyboardButton(text="💰 Баланс", callback_data="balance")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")
    )
    
    await callback.message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(F.data == "check_subscription")
async def callback_check_subscription(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    is_subscribed = await check_subscription(user_id)
    
    if is_subscribed:
        await update_user_subscription(user_id, True)
        text = "✅ <b>Отлично! Вы подписаны на канал.</b>\n\nТеперь вы можете использовать все функции бота!"
        await callback.message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())
    else:
        keyboard = InlineKeyboardBuilder()
        keyboard.row(
            InlineKeyboardButton(
                text="📢 Подписаться на канал",
                url=f"https://t.me/{Config.REQUIRED_CHANNEL.replace('@', '')}"
            )
        )
        keyboard.row(
            InlineKeyboardButton(text="✅ Проверить снова", callback_data="check_subscription")
        )
        
        text = f"""
⚠️ <b>Подписка не найдена!</b>

Пожалуйста, подпишитесь на канал:
{Config.REQUIRED_CHANNEL}

Убедитесь, что вы нажали "JOIN"/"ПОДПИСАТЬСЯ"
        """
        
        await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard.as_markup())
    
    await callback.answer()

@dp.callback_query(F.data == "main_menu")
async def callback_main_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_or_create_user(callback.from_user.id)
    
    text = f"""
📱 <b>Главное меню</b>

👋 Привет, {user['full_name'] or 'Друг'}!

💰 Баланс: {user['gold']} голды 🥇
👥 Рефералов: {user['referrals']}

👇 <b>Выберите раздел:</b>
    """
    
    await callback.message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())
    await callback.answer()

# ========== ПРОЦЕСС ВЫВОДА ==========

@dp.callback_query(F.data == "withdraw_start")
async def callback_withdraw_start(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    
    if not await check_subscription_middleware(user_id, callback=callback):
        await callback.answer()
        return
    
    user = await get_or_create_user(user_id)
    settings = await get_reward_settings()
    
    if user['gold'] < settings['min_withdrawal']:
        text = f"""
❌ <b>Недостаточно средств!</b>

Ваш баланс: {user['gold']} голды 🥇
Минимальный вывод: {settings['min_withdrawal']} голды 🥇

Необходимо еще: {settings['min_withdrawal'] - user['gold']} голды
        """
        await callback.message.answer(text, parse_mode="HTML")
        await callback.answer()
        return
    
    await state.set_state(WithdrawalStates.waiting_for_amount)
    await state.update_data(user_id=user_id, username=callback.from_user.username)
    
    text = f"""
💳 <b>Заявка на вывод</b>

💰 Ваш баланс: {user['gold']} голды 🥇
🎯 Минимальный вывод: {settings['min_withdrawal']} голды 🥇
💸 Комиссия рынка: {Config.MARKET_COMMISSION}%

📝 <b>Введите сумму вывода (голды):</b>
Пример: 5000, 10000, 15000
        """
    
    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()

@dp.message(WithdrawalStates.waiting_for_amount)
async def process_withdrawal_amount(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    try:
        amount = int(message.text)
        data = await state.get_data()
        settings = await get_reward_settings()
        
        user = await get_or_create_user(user_id)
        
        if amount < settings['min_withdrawal']:
            await message.answer(f"❌ Минимальная сумма вывода: {settings['min_withdrawal']} голды\n\nВведите сумму еще раз:")
            return
        
        if amount > user['gold']:
            await message.answer(f"❌ Недостаточно средств! Ваш баланс: {user['gold']} голды\n\nВведите сумму еще раз:")
            return
        
        commission = int(amount * Config.MARKET_COMMISSION / 100)
        final_amount = amount - commission
        
        await state.update_data(
            amount=amount,
            commission=commission,
            final_amount=final_amount
        )
        
        await state.set_state(WithdrawalStates.waiting_for_skin_photo)
        
        text = f"""
✅ <b>Сумма принята:</b> {amount} голды

📊 <b>Расчет:</b>
• Сумма: {amount} голды
• Комиссия ({Config.MARKET_COMMISSION}%): {commission} голды
• К получению: {final_amount} голды

📸 <b>Теперь отправьте фото скина, который вы выставляете на рынок:</b>
(Отправьте фото как изображение)
        """
        
        await message.answer(text, parse_mode="HTML")
        
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число!\n\nВведите сумму вывода:")

@dp.message(WithdrawalStates.waiting_for_skin_photo, F.photo)
async def process_skin_photo(message: types.Message, state: FSMContext):
    photo = message.photo[-1]
    file_id = photo.file_id
    
    await state.update_data(skin_photo=file_id)
    await state.set_state(WithdrawalStates.waiting_for_market_link)
    
    text = """
✅ <b>Фото скина принято!</b>

🔗 <b>Теперь отправьте ссылку на скин на рынке:</b>
Пример: https://steamcommunity.com/market/listings/730/...

⚠️ <b>Важно:</b>
• Убедитесь, что скин выставлен на рынок
• Цена должна соответствовать {final_amount} голды
• После подтверждения ожидайте оплату
    """
    
    await message.answer(text, parse_mode="HTML")

@dp.message(WithdrawalStates.waiting_for_market_link)
async def process_market_link(message: types.Message, state: FSMContext):
    market_link = message.text
    
    if not market_link.startswith(('http://', 'https://')):
        await message.answer("❌ Пожалуйста, отправьте корректную ссылку!")
        return
    
    await state.update_data(market_link=market_link)
    await state.set_state(WithdrawalStates.confirm_withdrawal)
    
    data = await state.get_data()
    
    text = f"""
📋 <b>Подтверждение заявки на вывод</b>

💰 <b>Детали вывода:</b>
• Сумма: {data['amount']} голды
• Комиссия: {data['commission']} голды ({Config.MARKET_COMMISSION}%)
• К получению: {data['final_amount']} голды
• Скин: фото прикреплено
• Ссылка на рынок: {data['market_link']}

⚠️ <b>После подтверждения:</b>
1. Администратор проверит заявку
2. Вы получите уведомление
3. После одобрения ожидайте оплату
4. Не снимайте скин с рынка до оплаты

✅ <b>Все верно?</b>
        """
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить вывод", callback_data="confirm_withdrawal"),
        InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_withdrawal")
    )
    
    if 'skin_photo' in data:
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=data['skin_photo'],
            caption=text,
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "confirm_withdrawal")
async def callback_confirm_withdrawal(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    conn = await get_db()
    
    await conn.execute('''
        INSERT INTO withdrawals 
        (user_id, username, amount, commission, final_amount, skin_photo, market_link, status)
        VALUES ($1, $2, $3, $4, $5, $6, $7, 'pending')
    ''', 
    data['user_id'], data.get('username'), data['amount'], 
    data['commission'], data['final_amount'], data.get('skin_photo'), 
    data.get('market_link'))
    
    withdrawal_id = await conn.fetchval('SELECT lastval()')
    
    await conn.close()
    await state.clear()
    
    # Уведомление пользователю
    text = f"""
✅ <b>Заявка #{withdrawal_id} создана!</b>

💰 Сумма: {data['amount']} голды
📊 К получению: {data['final_amount']} голды
⏳ Статус: <b>ожидает одобрения</b>

📞 Администратор получил уведомление и скоро рассмотрит вашу заявку.
    """
    
    await callback.message.edit_caption(caption=text, parse_mode="HTML")
    
    # Уведомление админу
    admin_text = f"""
🚨 <b>Новая заявка на вывод #{withdrawal_id}</b>

👤 Пользователь: @{data.get('username', 'Без юзернейма')} (ID: {data['user_id']})
💰 Сумма: {data['amount']} голды
💸 Комиссия: {data['commission']} голды
🎯 К выплате: {data['final_amount']} голды
🔗 Ссылка на рынок: {data.get('market_link', 'Не указана')}

⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}
    """
    
    try:
        if 'skin_photo' in data:
            await bot.send_photo(
                chat_id=Config.OWNER_ID,
                photo=data['skin_photo'],
                caption=admin_text,
                parse_mode="HTML",
                reply_markup=get_admin_withdrawal_keyboard(withdrawal_id)
            )
        else:
            await bot.send_message(
                chat_id=Config.OWNER_ID,
                text=admin_text,
                parse_mode="HTML",
                reply_markup=get_admin_withdrawal_keyboard(withdrawal_id)
            )
    except Exception as e:
        logger.error(f"Ошибка отправки админу: {e}")
    
    await callback.answer()

@dp.callback_query(F.data == "cancel_withdrawal")
async def callback_cancel_withdrawal(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_caption(
        caption="❌ <b>Заявка на вывод отменена</b>",
        parse_mode="HTML"
    )
    await callback.answer()

# ========== АДМИН КОНТРОЛЬ ВЫВОДОВ ==========

@dp.callback_query(F.data.startswith("admin_approve_"))
async def callback_admin_approve(callback: types.CallbackQuery):
    if callback.from_user.id != Config.OWNER_ID:
        await callback.answer("⛔ Нет доступа!")
        return
    
    withdrawal_id = int(callback.data.replace("admin_approve_", ""))
    
    await update_withdrawal_status(withdrawal_id, "approved", callback.from_user.id, "Одобрено администратором")
    
    # Получаем информацию о выводе
    conn = await get_db()
    withdrawal = await conn.fetchrow(
        'SELECT * FROM withdrawals WHERE id = $1',
        withdrawal_id
    )
    
    if withdrawal:
        # Уведомление пользователю
        user_text = f"""
✅ <b>Заявка #{withdrawal_id} одобрена!</b>

💰 Сумма: {withdrawal['amount']} голды
💸 Комиссия: {withdrawal['commission']} голды
🎯 К получению: {withdrawal['final_amount']} голды

⚠️ <b>Ожидайте оплату!</b>
Не снимайте скин с рынка до получения оплаты.

⏰ Время обработки: {datetime.now().strftime('%d.%m.%Y %H:%M')}
        """
        
        try:
            await bot.send_message(
                chat_id=withdrawal['user_id'],
                text=user_text,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки пользователю: {e}")
    
    await conn.close()
    
    await callback.message.edit_caption(
        caption=f"✅ <b>Заявка #{withdrawal_id} одобрена!</b>\n\nПользователь уведомлен.",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("admin_reject_"))
async def callback_admin_reject(callback: types.CallbackQuery):
    if callback.from_user.id != Config.OWNER_ID:
        await callback.answer("⛔ Нет доступа!")
        return
    
    withdrawal_id = int(callback.data.replace("admin_reject_", ""))
    
    # Здесь можно добавить запрос причины отклонения
    # Для простоты просто отклоняем
    await update_withdrawal_status(withdrawal_id, "rejected", callback.from_user.id, "Отклонено администратором")
    
    # Получаем информацию о выводе
    conn = await get_db()
    withdrawal = await conn.fetchrow(
        'SELECT * FROM withdrawals WHERE id = $1',
        withdrawal_id
    )
    
    if withdrawal:
        # Уведомление пользователю
        user_text = f"""
❌ <b>Заявка #{withdrawal_id} отклонена!</b>

💰 Сумма: {withdrawal['amount']} голды

📞 <b>Причина:</b> отклонено администратором
🔄 Вы можете создать новую заявку

⏰ Время обработки: {datetime.now().strftime('%d.%m.%Y %H:%M')}
        """
        
        try:
            await bot.send_message(
                chat_id=withdrawal['user_id'],
                text=user_text,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки пользователю: {e}")
    
    await conn.close()
    
    await callback.message.edit_caption(
        caption=f"❌ <b>Заявка #{withdrawal_id} отклонена!</b>\n\nПользователь уведомлен.",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    user_id = message.from_user.id
    
    if user_id != Config.OWNER_ID:
        await message.answer("⛔ Нет доступа!")
        return
    
    conn = await get_db()
    
    total_users = await conn.fetchval('SELECT COUNT(*) FROM users')
    total_referrals = await conn.fetchval('SELECT SUM(referrals) FROM users')
    total_gold = await conn.fetchval('SELECT SUM(gold) FROM users')
    
    pending_withdrawals = await get_pending_withdrawals()
    
    settings = await get_reward_settings()
    
    text = f"""
🛠️ <b>Админ панель</b>

📊 <b>Статистика:</b>
• Пользователей: {total_users}
• Рефералов: {total_referrals}
• Всего голды: {total_gold} 🥇

⏳ <b>Ожидают вывода:</b> {len(pending_withdrawals)} заявок

⚙️ <b>Текущие настройки:</b>
• За реферала: {settings['referral_reward']} голды
• За переход: {settings['join_reward']} голды
• Мин. вывод: {settings['min_withdrawal']} голды
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📋 Управление выводами", callback_data="admin_withdrawals"),
        InlineKeyboardButton(text="⚙️ Настройки наград", callback_data="admin_settings")
    )
    builder.row(
        InlineKeyboardButton(text="📊 Полная статистика", callback_data="admin_full_stats"),
        InlineKeyboardButton(text="📣 Рассылка", callback_data="admin_broadcast")
    )
    
    await conn.close()
    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())

@dp.callback_query(F.data == "admin_withdrawals")
async def callback_admin_withdrawals(callback: types.CallbackQuery):
    if callback.from_user.id != Config.OWNER_ID:
        await callback.answer("⛔ Нет доступа!")
        return
    
    pending_withdrawals = await get_pending_withdrawals()
    
    if not pending_withdrawals:
        text = "✅ <b>Нет ожидающих заявок на вывод</b>"
        await callback.message.answer(text, parse_mode="HTML")
        await callback.answer()
        return
    
    text = f"""
📋 <b>Ожидающие заявки на вывод:</b>
Всего: {len(pending_withdrawals)} заявок
    """
    
    for wd in pending_withdrawals[:5]:  # Показываем первые 5
        text += f"\n──────────────\n"
        text += f"🆔 <b>Заявка #{wd['id']}</b>\n"
        text += f"👤 Пользователь: @{wd['username'] or 'Без юзернейма'}\n"
        text += f"💰 Сумма: {wd['amount']} голды\n"
        text += f"💸 Комиссия: {wd['commission']} голды\n"
        text += f"🎯 К выплате: {wd['final_amount']} голды\n"
        text += f"⏰ Дата: {wd['request_date'].strftime('%d.%m %H:%M')}\n"
        
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"admin_approve_{wd['id']}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_reject_{wd['id']}")
        )
        
        if wd['skin_photo']:
            await bot.send_photo(
                chat_id=callback.message.chat.id,
                photo=wd['skin_photo'],
                caption=text,
                parse_mode="HTML",
                reply_markup=builder.as_markup()
            )
        else:
            await callback.message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())
        text = ""  # Сбрасываем текст для следующего сообщения
    
    await callback.answer()

# ========== ЗАПУСК БОТА ==========

async def main():
    await init_db()
    logger.info(f"Бот запущен! @{Config.BOT_USERNAME}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
