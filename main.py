import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Настройки бота
BOT_TOKEN = "8126450707:AAHmAGcyS76RImXRQ6WJBgMxF3JPPl4sduY"
BOT_USERNAME = "elon_ref_bot"
OWNER_ID = 7433757951

# Временное хранилище (в реальном проекте используйте БД)
users_db = {}
referral_stats = {}

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ========== ГЛАВНОЕ МЕНЮ ==========

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
        InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")
    )
    return builder.as_markup()

# ========== КОМАНДЫ ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    
    # Регистрация пользователя
    if user_id not in users_db:
        users_db[user_id] = {
            'username': message.from_user.username,
            'full_name': message.from_user.full_name,
            'join_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'referrals': 0,
            'gold': 0,
            'referrer_id': None
        }
        referral_stats[user_id] = []
    
    # Обработка реферальной ссылки
    referrer_id = None
    if len(args) > 1 and args[1].isdigit():
        referrer_id = int(args[1])
        if referrer_id != user_id and referrer_id in users_db:
            if users_db[user_id]['referrer_id'] is None:
                users_db[user_id]['referrer_id'] = referrer_id
                users_db[referrer_id]['referrals'] += 1
                users_db[referrer_id]['gold'] += 100
                referral_stats[referrer_id].append({
                    'user_id': user_id,
                    'username': message.from_user.username,
                    'date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'gold': 100
                })
    
    # Генерация реферальной ссылки
    ref_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    
    welcome_text = f"""
🎉 Добро пожаловать, {message.from_user.full_name}!

🤖 <b>Elon Referral Bot</b>

📌 <b>Ваша реферальная ссылка:</b>
<code>{ref_link}</code>

👥 <b>Приглашайте друзей и получайте:</b>
• 100 🥇 за каждого приглашенного
• 10% от их заработка

👇 <b>Используйте кнопки ниже:</b>
    """
    
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard())

@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    await message.answer("📱 <b>Главное меню</b>", parse_mode="HTML", reply_markup=get_main_keyboard())

# ========== КОЛБЭКИ ==========

@dp.callback_query(lambda c: c.data == "my_referrals")
async def callback_my_referrals(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_data = users_db.get(user_id, {})
    referrals_count = user_data.get('referrals', 0)
    
    text = f"""
👥 <b>Мои рефералы</b>

📊 <b>Всего приглашено:</b> {referrals_count}
💰 <b>Заработано:</b> {referrals_count * 100} 🥇

📋 <b>Список рефералов:</b>
"""
    
    if user_id in referral_stats and referral_stats[user_id]:
        for i, ref in enumerate(referral_stats[user_id], 1):
            username = f"@{ref['username']}" if ref['username'] else f"ID: {ref['user_id']}"
            text += f"{i}. {username} - {ref['date'].split()[0]}\n"
    else:
        text += "\n<i>У вас еще нет рефералов</i>\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📢 Поделиться ссылкой", callback_data="share_link")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")
    )
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "balance")
async def callback_balance(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_data = users_db.get(user_id, {})
    gold = user_data.get('gold', 0)
    
    text = f"""
💰 <b>Ваш баланс</b>

💎 <b>Всего голды:</b> {gold} 🥇
💳 <b>Доступно для вывода:</b> {gold} 🥇
🎯 <b>Минимальный вывод:</b> 500 🥇

📊 <b>История начислений:</b>
"""
    
    if user_id in referral_stats and referral_stats[user_id]:
        for i, ref in enumerate(referral_stats[user_id][-5:], 1):
            username = f"@{ref['username']}" if ref['username'] else "Пользователь"
            text += f"{i}. {username} +{ref['gold']} 🥇\n"
    else:
        text += "\n<i>Начислений нет</i>\n"
    
    builder = InlineKeyboardBuilder()
    if gold >= 500:
        builder.row(
            InlineKeyboardButton(text="💳 Вывести голду", callback_data="withdraw")
        )
    builder.row(
        InlineKeyboardButton(text="👥 Мои рефералы", callback_data="my_referrals"),
        InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")
    )
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "stats")
async def callback_stats(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_data = users_db.get(user_id, {})
    
    text = f"""
📊 <b>Статистика</b>

👤 <b>Профиль:</b>
• ID: {user_id}
• Имя: {user_data.get('full_name', 'Не указано')}
• Регистрация: {user_data.get('join_date', 'Неизвестно')}

💎 <b>Финансы:</b>
• Заработано: {user_data.get('gold', 0)} 🥇
• Рефералов: {user_data.get('referrals', 0)}
• Доход с рефералов: {user_data.get('referrals', 0) * 100} 🥇
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
        InlineKeyboardButton(text="👥 Рефералы", callback_data="my_referrals")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")
    )
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "ref_link")
async def callback_ref_link(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ref_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    user_data = users_db.get(user_id, {})
    
    text = f"""
🎁 <b>Реферальная ссылка</b>

📌 <b>Ваша ссылка:</b>
<code>{ref_link}</code>

📊 <b>Статистика:</b>
• Приглашено: {user_data.get('referrals', 0)}
• Заработано: {user_data.get('gold', 0)} 🥇
• На рефералов: {user_data.get('referrals', 0) * 100} 🥇
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📱 Поделиться",
            url=f"https://t.me/share/url?url={ref_link}&text=Присоединяйся к Elon Referral Bot! Зарабатывай голду! 🥇"
        )
    )
    builder.row(
        InlineKeyboardButton(text="👥 Мои рефералы", callback_data="my_referrals"),
        InlineKeyboardButton(text="💰 Баланс", callback_data="balance")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")
    )
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "share_link")
async def callback_share_link(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ref_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📱 Отправить другу",
            url=f"https://t.me/share/url?url={ref_link}&text=Присоединяйся! Зарабатывай голду! 🥇"
        )
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="my_referrals")
    )
    
    text = "📢 <b>Поделиться ссылкой</b>\n\nНажмите кнопку ниже, чтобы отправить ссылку другу:"
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "help")
async def callback_help(callback: types.CallbackQuery):
    text = """
ℹ️ <b>Помощь</b>

🤖 <b>Как работает бот:</b>
1. Вы получаете реферальную ссылку
2. Делитесь ссылкой с друзьями
3. За каждого приглашенного получаете 100 🥇
4. Выводите голду

👥 <b>Реферальная система:</b>
• За каждого друга: 100 🥇
• 10% от заработка реферала

💰 <b>Вывод средств:</b>
• Минимум: 500 🥇
• Для вывода нажмите в разделе Баланс

📋 <b>Команды:</b>
/start - Запуск бота
/menu - Главное меню

📞 <b>Поддержка:</b>
По вопросам вывода обращайтесь к владельцу
    """
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
        InlineKeyboardButton(text="🎁 Реф. ссылка", callback_data="ref_link")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")
    )
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "withdraw")
async def callback_withdraw(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_data = users_db.get(user_id, {})
    gold = user_data.get('gold', 0)
    
    text = f"""
💳 <b>Вывод голды</b>

💰 <b>Ваш баланс:</b> {gold} 🥇
💎 <b>Доступно к выводу:</b> {gold} 🥇

📝 <b>Для вывода:</b>
1. Минимальная сумма: 500 🥇
2. Укажите сумму вывода
3. Напишите реквизиты (карта/кошелек)
4. Отправьте заявку владельцу

🔄 <b>Обработка заявки:</b>
• Рассмотрение: 1-24 часа
• Выплата: после одобрения
"""
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="📨 Отправить заявку",
            url=f"tg://user?id={OWNER_ID}"
        )
    )
    builder.row(
        InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
        InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")
    )
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "main_menu")
async def callback_main_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_data = users_db.get(user_id, {})
    
    text = f"""
📱 <b>Главное меню</b>

👋 Привет, {user_data.get('full_name', 'Друг')}!

💎 Баланс: {user_data.get('gold', 0)} 🥇
👥 Рефералов: {user_data.get('referrals', 0)}

👇 <b>Выберите раздел:</b>
    """
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_main_keyboard())
    await callback.answer()

# ========== АДМИН КОМАНДЫ ==========

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    user_id = message.from_user.id
    
    if user_id != OWNER_ID:
        await message.answer("⛔ Нет доступа!")
        return
    
    total_users = len(users_db)
    total_referrals = sum(user.get('referrals', 0) for user in users_db.values())
    total_gold = sum(user.get('gold', 0) for user in users_db.values())
    
    text = f"""
🛠️ <b>Админ панель</b>

📊 <b>Статистика:</b>
• Пользователей: {total_users}
• Рефералов: {total_referrals}
• Всего голды: {total_gold} 🥇

👥 <b>Топ по голде:</b>
"""
    
    sorted_users = sorted(users_db.items(), key=lambda x: x[1].get('gold', 0), reverse=True)[:5]
    
    for i, (uid, data) in enumerate(sorted_users, 1):
        username = f"@{data.get('username')}" if data.get('username') else f"ID:{uid}"
        text += f"{i}. {username}: {data.get('gold', 0)} 🥇 ({data.get('referrals', 0)} реф.)\n"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Добавить голду", callback_data="admin_add_gold"),
        InlineKeyboardButton(text="📣 Рассылка", callback_data="admin_broadcast")
    )
    builder.row(
        InlineKeyboardButton(text="📊 Полная статистика", callback_data="admin_full_stats")
    )
    
    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())

# ========== ЗАПУСК БОТА ==========

async def main():
    logger.info("Starting bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
