import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, URLInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncpg
import aiohttp

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

# ========== БАЗА ДАННЫХ + НАСТРОЙКИ НАГРАД ==========

async def init_db():
    """Инициализация базы данных"""
    conn = await asyncpg.connect(Config.DATABASE_URL)
    
    # Таблица пользователей
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
    
    # Таблица рефералов
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
    
    # Таблица настроек наград
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
    
    # Таблица выводов
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            amount INTEGER,
            status TEXT DEFAULT 'pending',
            request_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_date TIMESTAMP,
            wallet_details TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')
    
    # Инициализация настроек наград
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

async def update_reward_settings(referral_reward=None, join_reward=None, min_withdrawal=None, updated_by=Config.OWNER_ID):
    """Обновление настроек наград"""
    conn = await get_db()
    
    # Получаем текущие настройки
    current = await get_reward_settings()
    
    # Обновляем только указанные значения
    new_referral = referral_reward if referral_reward is not None else current['referral_reward']
    new_join = join_reward if join_reward is not None else current['join_reward']
    new_min = min_withdrawal if min_withdrawal is not None else current['min_withdrawal']
    
    await conn.execute('''
        INSERT INTO reward_settings (referral_reward, join_reward, min_withdrawal, updated_by)
        VALUES ($1, $2, $3, $4)
    ''', new_referral, new_join, new_min, updated_by)
    
    await conn.close()
    return True

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
    
    # Получаем текущие настройки наград
    settings = await get_reward_settings()
    
    # Проверяем существующего пользователя
    user = await conn.fetchrow(
        'SELECT * FROM users WHERE user_id = $1',
        user_id
    )
    
    if not user:
        # Проверяем подписку перед созданием
        is_subscribed = await check_subscription(user_id)
        
        # Создаем нового пользователя
        await conn.execute('''
            INSERT INTO users (user_id, username, full_name, referrer_id, is_subscribed)
            VALUES ($1, $2, $3, $4, $5)
        ''', user_id, username, full_name, referrer_id, is_subscribed)
        
        # Если есть реферер и пользователь подписан
        if referrer_id and referrer_id != user_id and is_subscribed:
            # Награда рефереру
            await conn.execute('''
                UPDATE users 
                SET referrals = referrals + 1, 
                    gold = gold + $1
                WHERE user_id = $2
            ''', settings['referral_reward'], referrer_id)
            
            # Записываем в статистику
            await conn.execute('''
                INSERT INTO referral_stats (referrer_id, referred_id, referred_username, gold_awarded)
                VALUES ($1, $2, $3, $4)
            ''', referrer_id, user_id, username, settings['referral_reward'])
            
            # Награда новому пользователю за переход по ссылке
            await conn.execute('''
                UPDATE users 
                SET gold = gold + $1
                WHERE user_id = $2
            ''', settings['join_reward'], user_id)
            
            logger.info(f"Пользователь {user_id} получил {settings['join_reward']} голды за переход по ссылке")
    
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

async def create_withdrawal(user_id, amount, wallet_details):
    """Создание заявки на вывод"""
    conn = await get_db()
    await conn.execute(
        '''
        INSERT INTO withdrawals (user_id, amount, wallet_details)
        VALUES ($1, $2, $3)
        ''',
        user_id, amount, wallet_details
    )
    await conn.close()

# ========== КЛАВИАТУРЫ ==========

def get_main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👥 Мои рефералы", callback_data="my_referrals"),
        InlineKeyboardButton(text="💰 Баланс", callback_data="balance")
    )
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="stats"),
        InlineKeyboardButton(text="🎁 Реф. ссылка", callback_data="ref_link")
    )
    builder.row(
        InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_subscription")
    )
    return builder.as_markup()

def get_withdrawal_keyboard(user_gold, min_withdrawal):
    builder = InlineKeyboardBuilder()
    if user_gold >= min_withdrawal:
        builder.row(
            InlineKeyboardButton(text="💳 Вывести от 5000 голды", callback_data="withdraw")
        )
    builder.row(
        InlineKeyboardButton(text="👥 Рефералы", callback_data="my_referrals"),
        InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")
    )
    return builder.as_markup()

# ========== КОМАНДЫ С ПРОВЕРКОЙ ПОДПИСКИ ==========

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
        
        text = """
⚠️ <b>Требуется подписка!</b>

Для использования бота необходимо подписаться на канал:
{}

После подписки нажмите кнопку "✅ Я подписался"
        """.format(Config.REQUIRED_CHANNEL)
        
        if message:
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard.as_markup())
        elif callback:
            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard.as_markup())
        
        # Обновляем статус в БД
        await update_user_subscription(user_id, False)
        return False
    
    # Обновляем статус в БД
    await update_user_subscription(user_id, True)
    return True

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    
    # Регистрируем пользователя
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
    
    # Проверяем подписку
    if not await check_subscription_middleware(user_id, message=message):
        return
    
    # Если пользователь перешел по реферальной ссылке
    settings = await get_reward_settings()
    if referrer_id and referrer_id != user_id and user['is_subscribed']:
        welcome_bonus_text = f"""
🎉 Вы перешли по реферальной ссылке!
➕ Получено: {settings['join_reward']} голды 🥇
👤 Пригласивший: @{message.from_user.username or 'Пользователь'} получает {settings['referral_reward']} голды
        """
        await message.answer(welcome_bonus_text, parse_mode="HTML")
    
    # Главное меню
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

@dp.callback_query(lambda c: c.data == "balance")
async def callback_balance(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # Проверяем подписку
    if not await check_subscription_middleware(user_id, callback=callback):
        await callback.answer()
        return
    
    user = await get_or_create_user(user_id)
    settings = await get_reward_settings()
    
    # Отправляем изображение баланса
    try:
        photo = URLInputFile(Config.BALANCE_IMAGE)
        await bot.send_photo(
            chat_id=callback.message.chat.id,
            photo=photo,
            caption=f"""
💰 <b>Ваш баланс:</b> {user['gold']} голды 🥇

💳 <b>Доступно для вывода:</b> {user['gold']} голды 🥇
🎯 <b>Минимальный вывод:</b> {settings['min_withdrawal']} голды 🥇
            """,
            parse_mode="HTML",
            reply_markup=get_withdrawal_keyboard(user['gold'], settings['min_withdrawal'])
        )
        await callback.message.delete()
    except Exception as e:
        logger.error(f"Ошибка загрузки изображения: {e}")
        # Если изображение не загрузилось, показываем текстовый вариант
        text = f"""
💰 <b>Ваш баланс:</b> {user['gold']} голды 🥇

💳 <b>Доступно для вывода:</b> {user['gold']} голды 🥇
🎯 <b>Минимальный вывод:</b> {settings['min_withdrawal']} голды 🥇
        """
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_withdrawal_keyboard(user['gold'], settings['min_withdrawal']))
    
    await callback.answer()

# ========== АДМИН КОМАНДЫ ДЛЯ НАСТРОЙКИ НАГРАД ==========

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    user_id = message.from_user.id
    
    if user_id != Config.OWNER_ID:
        await message.answer("⛔ Нет доступа!")
        return
    
    conn = await get_db()
    
    # Получаем статистику
    total_users = await conn.fetchval('SELECT COUNT(*) FROM users')
    total_referrals = await conn.fetchval('SELECT SUM(referrals) FROM users')
    total_gold = await conn.fetchval('SELECT SUM(gold) FROM users')
    
    # Получаем текущие настройки
    settings = await get_reward_settings()
    
    text = f"""
🛠️ <b>Админ панель</b>

📊 <b>Статистика:</b>
• Пользователей: {total_users}
• Рефералов: {total_referrals}
• Всего голды: {total_gold} 🥇

⚙️ <b>Текущие настройки наград:</b>
• За реферала: {settings['referral_reward']} голды
• За переход по ссылке: {settings['join_reward']} голды
• Минимальный вывод: {settings['min_withdrawal']} голды
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⚙️ Изменить награды", callback_data="admin_change_rewards"),
        InlineKeyboardButton(text="📊 Полная статистика", callback_data="admin_stats")
    )
    builder.row(
        InlineKeyboardButton(text="📣 Рассылка", callback_data="admin_broadcast"),
        InlineKeyboardButton(text="✅ Управление выплатами", callback_data="admin_withdrawals")
    )
    
    await conn.close()
    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())

@dp.callback_query(lambda c: c.data == "admin_change_rewards")
async def callback_admin_change_rewards(callback: types.CallbackQuery):
    """Меню изменения наград"""
    settings = await get_reward_settings()
    
    text = f"""
⚙️ <b>Изменение настроек наград</b>

Текущие настройки:
1. За реферала: {settings['referral_reward']} голды
2. За переход по ссылке: {settings['join_reward']} голды
3. Минимальный вывод: {settings['min_withdrawal']} голды

Выберите, что изменить:
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1. За реферала", callback_data="admin_set_referral"),
        InlineKeyboardButton(text="2. За переход", callback_data="admin_set_join")
    )
    builder.row(
        InlineKeyboardButton(text="3. Мин. вывод", callback_data="admin_set_min"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")
    )
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("admin_set_"))
async def callback_admin_set_reward(callback: types.CallbackQuery):
    """Настройка конкретной награды"""
    action = callback.data
    
    if action == "admin_set_referral":
        text = "Введите новое количество голды за реферала (число):"
        next_action = "admin_save_referral"
    elif action == "admin_set_join":
        text = "Введите новое количество голды за переход по ссылке (число):"
        next_action = "admin_save_join"
    elif action == "admin_set_min":
        text = "Введите новую минимальную сумму вывода (число):"
        next_action = "admin_save_min"
    else:
        await callback.answer("Неизвестное действие")
        return
    
    await callback.message.edit_text(
        f"⚙️ <b>{text}</b>\n\nВведите число в следующем сообщении:",
        parse_mode="HTML"
    )
    
    # Сохраняем состояние для следующего сообщения
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.state import State, StatesGroup
    
    class AdminStates(StatesGroup):
        waiting_for_reward_value = State()
        reward_type = State()
    
    # Здесь нужно реализовать FSM (Finite State Machine) для обработки ввода
    # Для простоты можно использовать глобальную переменную или БД
    await callback.answer(f"Введите значение в чат")

# ========== ОБРАБОТКА ПОДПИСКИ ==========

@dp.callback_query(lambda c: c.data == "check_subscription")
async def callback_check_subscription(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    is_subscribed = await check_subscription(user_id)
    
    if is_subscribed:
        await update_user_subscription(user_id, True)
        text = "✅ <b>Отлично! Вы подписаны на канал.</b>\n\nТеперь вы можете использовать все функции бота!"
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_main_keyboard())
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
{}

Убедитесь, что вы нажали "JOIN"/"ПОДПИСАТЬСЯ", а не просто зашли в канал.
        """.format(Config.REQUIRED_CHANNEL)
        
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard.as_markup())
    
    await callback.answer()

# ========== ВЫВОД СРЕДСТВ ==========

@dp.callback_query(lambda c: c.data == "withdraw")
async def callback_withdraw(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # Проверяем подписку
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
        await callback.message.edit_text(text, parse_mode="HTML")
        await callback.answer()
        return
    
    text = f"""
💳 <b>Заявка на вывод</b>

💰 Доступно: {user['gold']} голды 🥇
🎯 Минимум: {settings['min_withdrawal']} голды 🥇

📝 <b>Для оформления вывода:</b>
1. Укажите сумму вывода (от {settings['min_withdrawal']})
2. Отправьте реквизиты (карта/кошелек)
3. Напишите сообщение владельцу

👉 Нажмите кнопку ниже для связи:
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📨 Связаться с владельцем",
            url=f"tg://user?id={Config.OWNER_ID}"
        )
    )
    builder.row(
        InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
        InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")
    )
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

# ========== ЗАПУСК БОТА ==========

async def main():
    # Инициализация БД
    await init_db()
    
    # Запуск бота
    logger.info(f"Бот запущен! @{Config.BOT_USERNAME}")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
