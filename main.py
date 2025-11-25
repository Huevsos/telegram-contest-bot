import requests
import random
import time
import json
import os
import hashlib
from datetime import datetime, timedelta
import logging
from functools import lru_cache

# ========== НАСТРОЙКИ БЕЗОПАСНОСТИ ==========
BOT_TOKEN = os.getenv('BOT_TOKEN', '8221020339:AAE5kzsWTl6nlK9kmVecq9FVjrUMWTn95kU')
ADMIN_USERNAME = "@cosinxx"
ADMIN_ID = 7433757951
BOT_USERNAME = "cosinxx_casino_bot"
SUPPORT_CHAT_ID = ADMIN_ID
URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"

# ========== НАСТРОЙКИ CRYPTOBOT ==========
CRYPTOBOT_TOKEN = "488620:AAxsbXNvS1DbiO4PwxMPsx0lxO3SP7c86PK"
CRYPTOBOT_URL = f"https://pay.crypt.bot/api/"
CRYPTOBOT_HEADERS = {
    "Crypto-Pay-API-Token": CRYPTOBOT_TOKEN,
    "Content-Type": "application/json"
}
DEPOSIT_COMMISSION = 0.05  # 5% комиссия на пополнение

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('casino.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# ========== КЛАССЫ ДЛЯ УЛУЧШЕНИЙ ==========

class CasinoException(Exception):
    """Базовое исключение казино"""
    pass

class InsufficientFundsException(CasinoException):
    pass

class RateLimitException(CasinoException):
    pass

class ValidationException(CasinoException):
    pass

class DataCache:
    """Кэширование данных для производительности"""
    def __init__(self):
        self._cache = {}
        self._timestamps = {}
    
    def get(self, key, ttl=300):
        if key in self._cache and time.time() - self._timestamps.get(key, 0) < ttl:
            return self._cache[key]
        return None
    
    def set(self, key, value):
        self._cache[key] = value
        self._timestamps[key] = time.time()
    
    def clear(self, key=None):
        if key:
            self._cache.pop(key, None)
            self._timestamps.pop(key, None)
        else:
            self._cache.clear()
            self._timestamps.clear()

class AutoSaver:
    """Автоматическое сохранение данных с интервалами"""
    def __init__(self, save_interval=60):
        self.last_save = time.time()
        self.save_interval = save_interval
        self.unsaved_changes = False
    
    def mark_changed(self):
        self.unsaved_changes = True
        if time.time() - self.last_save >= self.save_interval:
            self.force_save()
    
    def force_save(self):
        if self.unsaved_changes:
            save_data()
            self.unsaved_changes = False
            self.last_save = time.time()

class Player:
    """Класс для работы с пользователем"""
    def __init__(self, user_id):
        self.user_id = user_id
        self.data = get_user_balance(user_id)
    
    def update_balance(self, amount, currency="usdt"):
        self.data[currency] += amount
        auto_saver.mark_changed()
        return self.data[currency]
    
    def can_afford(self, amount, currency="usdt"):
        return self.data[currency] >= amount
    
    def get_stats(self):
        return get_personal_stats(self.user_id)
    
    def add_game_played(self, game_type):
        self.data["games_played"] = self.data.get("games_played", 0) + 1
        self.data["last_activity"] = time.time()
        auto_saver.mark_changed()
    
    def add_win(self, amount):
        self.data["games_won"] = self.data.get("games_won", 0) + 1
        self.data["total_winnings"] = self.data.get("total_winnings", 0) + amount
        self.data["current_win_streak"] = self.data.get("current_win_streak", 0) + 1
        
        if self.data["current_win_streak"] > self.data.get("max_win_streak", 0):
            self.data["max_win_streak"] = self.data["current_win_streak"]
        
        auto_saver.mark_changed()
    
    def add_loss(self):
        self.data["current_win_streak"] = 0
        auto_saver.mark_changed()

# ========== ИНИЦИАЛИЗАЦИЯ УЛУЧШЕННЫХ СИСТЕМ ==========

cache = DataCache()
auto_saver = AutoSaver(save_interval=60)

# ========== СУЩЕСТВУЮЩИЕ ХРАНИЛИЩА ДАННЫХ ==========
players = {}
active_invoices = {}
referral_codes = {}
user_states = {}
withdraw_requests = {}
mine_games = {}
crash_games = {}
game_results = {}
deposit_requests = {}
bonus_claims = {}
achievements = {}
support_tickets = {}
game_analytics = {
    "daily_stats": {},
    "game_popularity": {},
    "user_activity": {}
}

# НОВАЯ ИГРА - САНКИ 
sledge_games = {}
sledge_spins = {}

# ========== КЛАСС АНТИ-НАКРУТКИ ==========
class AntiCheat:
    def __init__(self):
        self.user_actions = {}
        self.suspicious_activity = {}
    
    def check_rate_limit(self, user_id, action_type):
        user_key = str(user_id)
        now = time.time()
        
        if user_key not in self.user_actions:
            self.user_actions[user_key] = {}
        
        if action_type not in self.user_actions[user_key]:
            self.user_actions[user_key][action_type] = []
        
        # Очищаем старые записи
        self.user_actions[user_key][action_type] = [
            t for t in self.user_actions[user_key][action_type] 
            if now - t < 60
        ]
        
        limits = {
            "bet": 15, "deposit": 5, "withdraw": 3, 
            "game": 30, "message": 20, "callback": 30
        }
        
        limit = limits.get(action_type, 10)
        
        if len(self.user_actions[user_key][action_type]) >= limit:
            if user_key not in self.suspicious_activity:
                self.suspicious_activity[user_key] = 0
            self.suspicious_activity[user_key] += 1
            return False
        
        self.user_actions[user_key][action_type].append(now)
        return True
    
    def get_suspicious_users(self):
        return {uid: count for uid, count in self.suspicious_activity.items() if count > 5}

anti_cheat = AntiCheat()

# ========== НАСТРОЙКИ КАЗИНО ==========
GAME_SETTINGS = {
    "min_bet_usdt": 1, "max_bet_usdt": 1000,
    "min_bet_coins": 10, "max_bet_coins": 10000,
    "house_edge": 0.05, "referral_bonus": 0.03, "welcome_bonus": 500,
    "min_deposit": 1, "min_withdraw": 10,
    "daily_bonus_min": 300, "daily_bonus_max": 500,
    "weekly_bonus_min": 1000, "weekly_bonus_max": 3000,
    "sledge_target_min": 50, "sledge_target_max": 200,
    "sledge_multiplier": 2.0
}

# ========== СИСТЕМА ДОСТИЖЕНИЙ ==========
ACHIEVEMENTS_CONFIG = {
    "first_deposit": {"name": "💰 Первое пополнение", "reward": 0.5, "description": "Пополните баланс впервые"},
    "first_win": {"name": "🎯 Первая победа", "reward": 0.5, "description": "Одержите первую победу в игре"},
    "high_roller": {"name": "🎰 Высокий роллер", "reward": 5, "description": "Сделайте ставку от 100 USDT"},
    "lucky_streak": {"name": "🔥 Полоса удачи", "reward": 1, "description": "Выиграйте 3 раза подряд"},
    "referral_master": {"name": "👥 Мастер рефералов", "reward": 2, "description": "Пригласите 5 друзей"},
    "veteran": {"name": "🏆 Ветеран", "reward": 5, "description": "Сыграйте 100 игр"},
    "big_winner": {"name": "💰 Крупный выигрыш", "reward": 20, "description": "Выиграйте 500 USDT за одну игру"},
    "deposit_king": {"name": "👑 Король пополнений", "reward": 30, "description": "Пополните на 1000 USDT в сумме"},
    "sledge_master": {"name": "🎿 Мастер саней", "reward": 3, "description": "Выиграйте 5 раз в игре Санки"},
}

# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С CRYPTOBOT ==========

def create_cryptobot_invoice(amount, user_id, description="Пополнение баланса"):
    """Создание инвойса в CryptoBot"""
    try:
        payload = {
            "amount": amount,
            "asset": "USDT",
            "description": description,
            "hidden_message": f"Пополнение для пользователя {user_id}",
            "paid_btn_name": "callback",
            "paid_btn_url": f"https://t.me/{BOT_USERNAME}",
            "payload": str(user_id),
            "allow_comments": False,
            "allow_anonymous": False
        }
        
        response = requests.post(
            f"{CRYPTOBOT_URL}createInvoice",
            json=payload,
            headers=CRYPTOBOT_HEADERS,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                invoice = result["result"]
                invoice_id = invoice["invoice_id"]
                
                # Сохраняем информацию о инвойсе
                active_invoices[invoice_id] = {
                    "user_id": user_id,
                    "amount": amount,
                    "amount_net": amount * (1 - DEPOSIT_COMMISSION),  # Сумма за вычетом комиссии
                    "status": "active",
                    "created_at": time.time(),
                    "invoice_url": invoice["pay_url"],
                    "description": description
                }
                
                return invoice
            else:
                logging.error(f"Ошибка CryptoBot: {result.get('error')}")
                return None
        else:
            logging.error(f"HTTP ошибка CryptoBot: {response.status_code}")
            return None
            
    except Exception as e:
        logging.error(f"Ошибка создания инвойса CryptoBot: {e}")
        return None

def get_cryptobot_invoice_status(invoice_id):
    """Проверка статуса инвойса в CryptoBot"""
    try:
        response = requests.get(
            f"{CRYPTOBOT_URL}getInvoices?invoice_ids={invoice_id}",
            headers=CRYPTOBOT_HEADERS,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("ok") and result["result"]["items"]:
                invoice = result["result"]["items"][0]
                return invoice.get("status", "active")
        
        return "active"
        
    except Exception as e:
        logging.error(f"Ошибка проверки статуса инвойса: {e}")
        return "active"

def process_cryptobot_payment(invoice_id):
    """Обработка оплаченного инвойса"""
    if invoice_id not in active_invoices:
        return False
    
    invoice = active_invoices[invoice_id]
    if invoice["status"] != "active":
        return False
    
    # Проверяем статус в CryptoBot
    status = get_cryptobot_invoice_status(invoice_id)
    
    if status == "paid":
        user_id = invoice["user_id"]
        amount_net = invoice["amount_net"]
        
        # Зачисляем средства пользователю
        player = Player(user_id)
        player.data["usdt"] += amount_net
        player.data["total_deposits"] += amount_net
        
        # Начисляем реферальный бонус
        if player.data.get("referrer_id"):
            referrer_id = player.data["referrer_id"]
            referrer = Player(referrer_id)
            referral_bonus = amount_net * GAME_SETTINGS["referral_bonus"]
            referrer.data["referral_balance"] += referral_bonus
            referrer.data["referral_earnings"] += referral_bonus
        
        # Обновляем статус инвойса
        invoice["status"] = "paid"
        invoice["paid_at"] = time.time()
        
        # Уведомляем пользователя
        send_message(user_id,
            f"✅ <b>Пополнение успешно!</b>\n\n"
            f"💰 Сумма: {invoice['amount']} USDT\n"
            f"💸 Комиссия: {DEPOSIT_COMMISSION*100}% ({invoice['amount'] * DEPOSIT_COMMISSION:.2f} USDT)\n"
            f"💎 Зачислено: {amount_net:.2f} USDT\n"
            f"🎯 Новый баланс: {player.data['usdt']:.2f} USDT\n\n"
            f"Спасибо за пополнение! 🎰"
        )
        
        auto_saver.mark_changed()
        return True
    
    return False

def check_pending_invoices():
    """Проверка ожидающих инвойсов"""
    try:
        for invoice_id, invoice in list(active_invoices.items()):
            if invoice["status"] == "active":
                if time.time() - invoice["created_at"] > 3600:  # 1 час
                    # Инвойс просрочен
                    invoice["status"] = "expired"
                    continue
                
                # Проверяем статус оплаты
                process_cryptobot_payment(invoice_id)
                
    except Exception as e:
        logging.error(f"Ошибка проверки инвойсов: {e}")

def create_cryptobot_withdraw(user_id, amount, wallet_address):
    """Создание запроса на вывод через CryptoBot"""
    try:
        payload = {
            "asset": "USDT",
            "amount": amount,
            "address": wallet_address,
            "comment": f"Вывод средств пользователя {user_id}"
        }
        
        response = requests.post(
            f"{CRYPTOBOT_URL}transfer",
            json=payload,
            headers=CRYPTOBOT_HEADERS,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("ok"):
                return True, result["result"]
            else:
                return False, result.get("error", "Неизвестная ошибка")
        else:
            return False, f"HTTP ошибка: {response.status_code}"
            
    except Exception as e:
        logging.error(f"Ошибка создания вывода CryptoBot: {e}")
        return False, str(e)

# ========== УТИЛИТЫ БЕЗОПАСНОСТИ ==========

def hash_user_id(user_id):
    return hashlib.sha256(f"casino_salt_{user_id}".encode()).hexdigest()

def get_bet_limits(currency):
    limits = {
        "coins": {"min": GAME_SETTINGS["min_bet_coins"], "max": GAME_SETTINGS["max_bet_coins"]},
        "usdt": {"min": GAME_SETTINGS["min_bet_usdt"], "max": GAME_SETTINGS["max_bet_usdt"]}
    }
    return limits.get(currency, limits["coins"])

def validate_bet_amount(user_id, amount, currency):
    player = Player(user_id)
    limits = get_bet_limits(currency)
    
    if amount < limits["min"]:
        return False, f"Минимальная ставка: {limits['min']}"
    if amount > limits["max"]:
        return False, f"Максимальная ставка: {limits['max']}"
    if not player.can_afford(amount, currency):
        return False, f"Недостаточно средств. Баланс: {player.data[currency]}"
    
    return True, "OK"

def validate_input(text, input_type="amount"):
    """Улучшенная валидация ввода"""
    if not text or not isinstance(text, str):
        return False
    
    validators = {
        "amount": lambda x: x.replace('.', '', 1).replace(',', '', 1).isdigit() and float(x.replace(',', '.')) > 0,
        "wallet": lambda x: x.startswith('T') and len(x) >= 20 and x[1:].isalnum(),
        "username": lambda x: 3 <= len(x) <= 32 and all(c.isalnum() or c in '_-' for c in x),
        "message": lambda x: 5 <= len(x) <= 1000
    }
    
    validator = validators.get(input_type, lambda x: True)
    return validator(text)

# ========== СИСТЕМА СОХРАНЕНИЯ ==========

def save_data():
    try:
        # Конвертируем sets в lists для сериализации JSON
        data_to_save = {
            'players': players, 'referral_codes': referral_codes,
            'active_invoices': active_invoices, 'withdraw_requests': withdraw_requests,
            'deposit_requests': deposit_requests, 'bonus_claims': bonus_claims,
            'achievements': achievements, 'support_tickets': support_tickets,
            'game_analytics': convert_game_analytics_for_save(), 'last_save': time.time(),
            'sledge_games': sledge_games, 'sledge_spins': sledge_spins
        }
        
        with open('casino_data.json', 'w') as f:
            json.dump(data_to_save, f, indent=2)
        
        if not os.path.exists('backups'):
            os.makedirs('backups')
        
        backup_file = f'backups/casino_backup_{int(time.time())}.json'
        with open(backup_file, 'w') as f:
            json.dump(data_to_save, f, indent=2)
            
        cache.clear()
        logging.info("Данные успешно сохранены")
        
    except Exception as e:
        logging.error(f"Ошибка сохранения данных: {e}")

def convert_game_analytics_for_save():
    """Конвертирует game_analytics для сохранения (заменяет sets на lists)"""
    converted = {
        "daily_stats": {},
        "game_popularity": game_analytics.get("game_popularity", {}).copy(),
        "user_activity": game_analytics.get("user_activity", {}).copy()
    }
    
    # Конвертируем daily_stats
    for date, stats in game_analytics.get("daily_stats", {}).items():
        converted["daily_stats"][date] = {
            "total_games": stats.get("total_games", 0),
            "total_bets": stats.get("total_bets", 0),
            "total_wins": stats.get("total_wins", 0),
            "unique_players": list(stats.get("unique_players", set())),  # Конвертируем set в list
            "games_played": stats.get("games_played", {}).copy()
        }
    
    return converted

def load_data():
    global players, referral_codes, active_invoices, withdraw_requests, deposit_requests
    global bonus_claims, achievements, support_tickets, game_analytics, sledge_games, sledge_spins
    
    try:
        for folder in ['backups', 'logs', 'analytics']:
            if not os.path.exists(folder):
                os.makedirs(folder)
        
        if os.path.exists('casino_data.json'):
            with open('casino_data.json', 'r') as f:
                data = json.load(f)
                players = data.get('players', {})
                referral_codes = data.get('referral_codes', {})
                active_invoices = data.get('active_invoices', {})
                withdraw_requests = data.get('withdraw_requests', {})
                deposit_requests = data.get('deposit_requests', {})
                bonus_claims = data.get('bonus_claims', {})
                achievements = data.get('achievements', {})
                support_tickets = data.get('support_tickets', {})
                game_analytics = convert_loaded_game_analytics(data.get('game_analytics', {
                    "daily_stats": {}, "game_popularity": {}, "user_activity": {}
                }))
                sledge_games = data.get('sledge_games', {})
                sledge_spins = data.get('sledge_spins', {})
            
            # Исправляем структуру данных для существующих пользователей
            for user_id, user_data in players.items():
                # Добавляем отсутствующие поля
                if "game_currency" not in user_data:
                    user_data["game_currency"] = "coins"
                if "total_bet" not in user_data:
                    user_data["total_bet"] = 0
                if "total_profit" not in user_data:
                    user_data["total_profit"] = 0
                if "total_deposits" not in user_data:
                    user_data["total_deposits"] = 0
                if "total_withdrawals" not in user_data:
                    user_data["total_withdrawals"] = 0
                if "current_win_streak" not in user_data:
                    user_data["current_win_streak"] = 0
                if "max_win_streak" not in user_data:
                    user_data["max_win_streak"] = 0
                if "favorite_game" not in user_data:
                    user_data["favorite_game"] = None
                if "last_bonus_claim" not in user_data:
                    user_data["last_bonus_claim"] = 0
                if "referral_balance" not in user_data:
                    user_data["referral_balance"] = 0.0
                if "referral_earnings" not in user_data:
                    user_data["referral_earnings"] = 0.0
                if "hashed_id" not in user_data:
                    user_data["hashed_id"] = hash_user_id(int(user_id))
            
            logging.info("Данные успешно загружены и исправлены")
            return
        
        if os.path.exists('backups'):
            backup_files = sorted([f for f in os.listdir('backups') if f.startswith('casino_backup_')])
            if backup_files:
                latest_backup = backup_files[-1]
                with open(os.path.join('backups', latest_backup), 'r') as f:
                    data = json.load(f)
                    players = data.get('players', {})
                    referral_codes = data.get('referral_codes', {})
                logging.info(f"Данные восстановлены из бэкапа: {latest_backup}")
                return
                
    except Exception as e:
        logging.error(f"Ошибка загрузки данных: {e}")
    
    players = {}
    referral_codes = {}
    active_invoices = {}
    withdraw_requests = {}
    deposit_requests = {}
    bonus_claims = {}
    achievements = {}
    support_tickets = {}
    game_analytics = {
        "daily_stats": {}, "game_popularity": {}, "user_activity": {}
    }
    sledge_games = {}
    sledge_spins = {}
    logging.info("Инициализированы новые данные")

def convert_loaded_game_analytics(loaded_data):
    """Конвертирует загруженные данные game_analytics (lists обратно в sets)"""
    converted = {
        "daily_stats": {},
        "game_popularity": loaded_data.get("game_popularity", {}),
        "user_activity": loaded_data.get("user_activity", {})
    }
    
    # Конвертируем daily_stats обратно
    for date, stats in loaded_data.get("daily_stats", {}).items():
        converted["daily_stats"][date] = {
            "total_games": stats.get("total_games", 0),
            "total_bets": stats.get("total_bets", 0),
            "total_wins": stats.get("total_wins", 0),
            "unique_players": set(stats.get("unique_players", [])),  # Конвертируем list обратно в set
            "games_played": stats.get("games_played", {})
        }
    
    return converted

# ========== ОТПРАВКА СООБЩЕНИЙ ==========

def send_message(chat_id, text, reply_markup=None, max_retries=3):
    """Отправка сообщений"""
    for attempt in range(max_retries):
        try:
            params = {
                "chat_id": chat_id, 
                "text": text, 
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
            
            if reply_markup:
                params["reply_markup"] = json.dumps(reply_markup)
                
            response = requests.post(URL + "sendMessage", json=params, timeout=25)
            
            if response.status_code == 200:
                return response
            else:
                logging.warning(f"Попытка {attempt + 1}: Ошибка HTTP {response.status_code}")
                if response.status_code == 400:
                    # Логируем детали ошибки 400
                    error_details = response.json()
                    logging.error(f"Ошибка 400 детали: {error_details}")
                
        except requests.exceptions.Timeout:
            logging.warning(f"Попытка {attempt + 1}: Таймаут")
        except requests.exceptions.ConnectionError:
            logging.warning(f"Попытка {attempt + 1}: Ошибка соединения")
        except Exception as e:
            logging.error(f"Попытка {attempt + 1}: {e}")
        
        if attempt < max_retries - 1:
            time.sleep(2)
    
    return None

def edit_message(chat_id, message_id, text, reply_markup=None, max_retries=3):
    """Редактирование существующего сообщения"""
    for attempt in range(max_retries):
        try:
            params = {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }
            
            if reply_markup:
                params["reply_markup"] = json.dumps(reply_markup)
                
            response = requests.post(URL + "editMessageText", json=params, timeout=25)
            
            if response.status_code == 200:
                return response
            else:
                logging.warning(f"Попытка {attempt + 1}: Ошибка HTTP {response.status_code}")
                if response.status_code == 400:
                    # Логируем детали ошибки 400
                    error_details = response.json()
                    logging.error(f"Ошибка 400 при редактировании: {error_details}")
                
        except requests.exceptions.Timeout:
            logging.warning(f"Попытка {attempt + 1}: Таймаут")
        except requests.exceptions.ConnectionError:
            logging.warning(f"Попытка {attempt + 1}: Ошибка соединения")
        except Exception as e:
            logging.error(f"Попытка {attempt + 1}: {e}")
        
        if attempt < max_retries - 1:
            time.sleep(2)
    
    return None

def send_dice(chat_id, emoji="🎲"):
    """Отправка анимации"""
    try:
        params = {"chat_id": chat_id, "emoji": emoji}
        response = requests.post(URL + "sendDice", json=params, timeout=25)
        
        if response.status_code == 200:
            result = response.json()
            message_id = result['result']['message_id']
            game_results[message_id] = {
                'chat_id': chat_id,
                'emoji': emoji,
                'value': result['result']['dice']['value'],
                'timestamp': time.time()
            }
            return result
        else:
            logging.error(f"Ошибка отправки кубика: {response.text}")
            return None
            
    except Exception as e:
        logging.error(f"Ошибка отправки кубика: {e}")
        return None

# ========== ФУНКЦИИ БАЛАНСА ==========

@lru_cache(maxsize=100)
def get_user_balance(user_id):
    """Получение баланса пользователя"""
    user_id_str = str(user_id)
    
    if user_id_str not in players:
        players[user_id_str] = {
            "usdt": 0.0, "coins": 100, "games_played": 0, "games_won": 0,
            "total_winnings": 0, "referral_code": None, "referrals": [],
            "referrer_id": None, "referral_earnings": 0.0, "username": "",
            "referral_balance": 0.0, "game_currency": "coins", "total_bet": 0,
            "total_profit": 0, "total_deposits": 0, "total_withdrawals": 0,
            "registration_date": time.time(), "last_activity": time.time(),
            "hashed_id": hash_user_id(user_id), "current_win_streak": 0,
            "max_win_streak": 0, "favorite_game": None, "last_bonus_claim": 0,
            "sledge_wins": 0
        }
    else:
        players[user_id_str]["last_activity"] = time.time()
        
        # Гарантируем, что все необходимые поля существуют
        required_fields = {
            "game_currency": "coins",
            "total_bet": 0, "total_profit": 0, "total_deposits": 0,
            "total_withdrawals": 0, "games_played": 0, "games_won": 0, 
            "total_winnings": 0, "current_win_streak": 0, "max_win_streak": 0,
            "favorite_game": None, "last_bonus_claim": 0,
            "referral_balance": 0.0, "referral_earnings": 0.0,
            "hashed_id": hash_user_id(user_id), "sledge_wins": 0
        }
        
        for field, default_value in required_fields.items():
            if field not in players[user_id_str]:
                players[user_id_str][field] = default_value
    
    return players[user_id_str]

def generate_referral_code(user_id):
    """Генерирует уникальный реферальный код"""
    code = f"REF{user_id}{random.randint(1000, 9999)}"
    referral_codes[code] = user_id
    auto_saver.mark_changed()
    return code

def get_top_players(limit=10):
    """Возвращает топ игроков по балансу"""
    sorted_players = sorted(players.items(), 
                          key=lambda x: x[1].get('total_profit', 0), 
                          reverse=True)
    return sorted_players[:limit]

def get_personal_stats(user_id):
    """Возвращает персональную статистику"""
    player = Player(user_id)
    user_data = player.data
    
    win_rate = (user_data["games_won"] / user_data["games_played"] * 100) if user_data["games_played"] > 0 else 0
    avg_bet = (user_data["total_bet"] / user_data["games_played"]) if user_data["games_played"] > 0 else 0
    
    return {
        "games_played": user_data["games_played"],
        "games_won": user_data["games_won"],
        "win_rate": win_rate,
        "total_bet": user_data["total_bet"],
        "total_winnings": user_data["total_winnings"],
        "total_profit": user_data["total_profit"],
        "current_streak": user_data["current_win_streak"],
        "max_streak": user_data["max_win_streak"],
        "favorite_game": user_data["favorite_game"],
        "registration_days": int((time.time() - user_data["registration_date"]) / 86400),
        "sledge_wins": user_data.get("sledge_wins", 0)
    }

# ========== НОВАЯ ИГРА "САНКИ"  ==========

def play_sledge_game(user_id, chat_id, bet_amount, currency):
    """Игра Санки """
    player = Player(user_id)
    currency_text = "виртуальных монет" if currency == "coins" else "USDT"
    
    if player.data[currency] < bet_amount:
        send_message(chat_id, f"❌ Недостаточно средств! Баланс: {player.data[currency]} {currency_text}")
        return
    
    # Генерируем целевое число
    target_number = random.randint(GAME_SETTINGS["sledge_target_min"], GAME_SETTINGS["sledge_target_max"])
    
    # Создаем игру
    game_id = f"sledge_{user_id}_{int(time.time())}"
    sledge_games[game_id] = {
        "user_id": user_id,
        "bet_amount": bet_amount,
        "currency": currency,
        "target_number": target_number,
        "current_spin": 0,
        "max_spins": 15,
        "status": "active",
        "start_time": time.time(),
        "chat_id": chat_id
    }
    
    # Списываем ставку
    player.data[currency] -= bet_amount
    player.data["games_played"] += 1
    player.data["total_bet"] += bet_amount
    auto_saver.mark_changed()
    
    # Отправляем начальное сообщение
    message = send_message(chat_id,
        f"🎿 <b>Санки</b>\n\n"
        f"👤 {player.data.get('username', 'Игрок')} ставит {bet_amount} {currency_text}\n\n"
        f"🎯 <b>Санки</b>\n"
        f"Должно выпасть число {target_number}\n\n"
        f"🎰 <i>Желаем удачи!</i>\n"
        f"🔄 15 Spins, 0:36\n\n"
        f"⏰ Игра началась...",
        sledge_game_keyboard(game_id)
    )


def start_sledge_animation(game_id):
    """Запускает анимацию спиннеров для игры Санки"""
    if game_id not in sledge_games:
        return
    
    game = sledge_games[game_id]
    user_id = game["user_id"]
    chat_id = game["chat_id"]
    message_id = game.get("message_id")
    
    player = Player(user_id)
    currency_text = "виртуальных монет" if game["currency"] == "coins" else "USDT"
    
    # Запускаем 15 спиннеров с интервалом
    for spin in range(1, 16):
        if game_id not in sledge_games or sledge_games[game_id]["status"] != "active":
            break
            
        current_time = 36 - (spin * 2.4)  # Уменьшаем время
        if current_time < 0:
            current_time = 0
        
        # Обновляем сообщение
        if message_id:
            try:
                edit_message(chat_id, message_id,
                    f"🎿 <b>Cанки</b>\n\n"
                    f"👤 {player.data.get('username', 'Игрок')} ставит {game['bet_amount']} {currency_text}\n\n"
                    f"🎯 <b>Санки</b>\n"
                    f"Должно выпасть число {game['target_number']}\n\n"
                    f"🎰 <i>Желаем удачи!</i>\n"
                    f"🔄 {spin}/15 Spins, 0:{current_time:02.0f}\n\n"
                    f"🎲 Крутим спиннеры...",
                    sledge_game_keyboard(game_id)
                )
            except:
                pass
        
        # Имитация спиннера - случайное число
        spin_result = random.randint(1, 1000)
        sledge_spins[f"{game_id}_spin_{spin}"] = {
            "number": spin_result,
            "is_win": spin_result == game["target_number"],
            "timestamp": time.time()
        }
        
        # Если выигрыш - завершаем игру
        if spin_result == game["target_number"]:
            sledge_games[game_id]["status"] = "won"
            sledge_games[game_id]["win_spin"] = spin
            sledge_games[game_id]["win_number"] = spin_result
            break
        
        time.sleep(2.4)  # Интервал между спиннерами
    
    # Завершаем игру
    finish_sledge_game(game_id)

def finish_sledge_game(game_id):
    """Завершает игру Санки и выдает результат"""
    if game_id not in sledge_games:
        return
    
    game = sledge_games[game_id]
    user_id = game["user_id"]
    chat_id = game["chat_id"]
    message_id = game.get("message_id")
    
    player = Player(user_id)
    currency_text = "виртуальных монет" if game["currency"] == "coins" else "USDT"
    
    if game["status"] == "won":
        # Выигрыш
        win_amount = int(game["bet_amount"] * GAME_SETTINGS["sledge_multiplier"])
        player.data[game["currency"]] += win_amount
        player.data["games_won"] += 1
        player.data["total_winnings"] += win_amount
        player.data["total_profit"] += (win_amount - game["bet_amount"])
        player.data["current_win_streak"] += 1
        player.data["sledge_wins"] = player.data.get("sledge_wins", 0) + 1
        
        if player.data["current_win_streak"] > player.data["max_win_streak"]:
            player.data["max_win_streak"] = player.data["current_win_streak"]
        
        result_text = (
            f"🎉 <b>ВЫИГРЫШ!</b>\n\n"
            f"🎯 Выпало число: {game['win_number']}\n"
            f"💰 Выигрыш: {win_amount} {currency_text}\n"
            f"🎰 Спин: {game['win_spin']}/15\n"
            f"💎 Новый баланс: {player.data[game['currency']]} {currency_text}"
        )
        
        # Проверяем достижение
        check_sledge_achievement(user_id)
        
    else:
        # Проигрыш
        player.data["total_profit"] -= game["bet_amount"]
        player.data["current_win_streak"] = 0
        
        result_text = (
            f"❌ <b>ПРОИГРЫШ</b>\n\n"
            f"🎯 Целевое число: {game['target_number']} не выпало\n"
            f"💸 Потеряно: {game['bet_amount']} {currency_text}\n"
            f"💎 Баланс: {player.data[game['currency']]} {currency_text}"
        )
    
    # Обновляем аналитику
    update_game_analytics("sledge", game["bet_amount"], win_amount if game["status"] == "won" else 0, user_id)
    
    # Обновляем сообщение с результатом
    if message_id:
        try:
            edit_message(chat_id, message_id,
                f"🎿 <b>Санки</b>\n\n"
                f"👤 {player.data.get('username', 'Игрок')} ставит {game['bet_amount']} {currency_text}\n\n"
                f"🎯 <b>Санки</b>\n"
                f"Должно выпасть число {game['target_number']}\n\n"
                f"{result_text}\n\n"
                f"🔄 Игра завершена",
                sledge_game_finished_keyboard()
            )
        except:
            # Если не удалось отредактировать, отправляем новое сообщение
            send_message(chat_id,
                f"🎿 <b>Санки - Результат</b>\n\n"
                f"{result_text}",
                sledge_game_finished_keyboard()
            )
    
    auto_saver.mark_changed()

def check_sledge_achievement(user_id):
    """Проверяет достижение для игры Санки"""
    player = Player(user_id)
    sledge_wins = player.data.get("sledge_wins", 0)
    
    if sledge_wins >= 5:
        achievement_id = "sledge_master"
        user_str = str(user_id)
        
        if user_str not in achievements:
            achievements[user_str] = {}
        
        if achievement_id not in achievements[user_str]:
            achievements[user_str][achievement_id] = {
                "achieved_at": time.time(),
                "reward_claimed": False
            }
            auto_saver.mark_changed()

# ========== НОВАЯ ИГРА В КОСТИ С ДВУМЯ КУБИКАМИ ==========

def play_dice_game_two_dice(user_id, chat_id, bet_type, bet_amount, currency):
    """Игра в кости с двумя кубиками для ставки 'Произведение > 18'"""
    player = Player(user_id)
    currency_text = "виртуальных монет" if currency == "coins" else "USDT"
    
    if player.data[currency] < bet_amount:
        send_message(chat_id, f"❌ Недостаточно средств! Баланс: {player.data[currency]} {currency_text}")
        return
    
    # Списываем ставку
    player.data[currency] -= bet_amount
    player.data["games_played"] += 1
    player.data["total_bet"] += bet_amount
    auto_saver.mark_changed()
    
    # Отправляем анимацию первого кубика
    send_message(chat_id, f"🎲 <b>Бросаем кубики...</b>\n💰 Ставка: {bet_amount} {currency_text}")
    time.sleep(1)
    
    # Бросаем первый кубик
    dice_result1 = send_dice(chat_id, "🎲")
    if not dice_result1:
        send_message(chat_id, "❌ Ошибка запуска игры. Попробуйте еще раз.", dice_game_keyboard())
        # Возвращаем ставку при ошибке
        player.data[currency] += bet_amount
        player.data["games_played"] -= 1
        player.data["total_bet"] -= bet_amount
        auto_saver.mark_changed()
        return
    
    # Ждем завершения первой анимации
    time.sleep(4)
    
    # Бросаем второй кубик
    dice_result2 = send_dice(chat_id, "🎲")
    if not dice_result2:
        send_message(chat_id, "❌ Ошибка запуска игры. Попробуйте еще раз.", dice_game_keyboard())
        # Возвращаем ставку при ошибке
        player.data[currency] += bet_amount
        player.data["games_played"] -= 1
        player.data["total_bet"] -= bet_amount
        auto_saver.mark_changed()
        return
    
    # Ждем завершения второй анимации
    time.sleep(4)
    
    # Получаем реальные результаты анимаций
    message_id1 = dice_result1['result']['message_id']
    message_id2 = dice_result2['result']['message_id']
    
    if message_id1 in game_results and message_id2 in game_results:
        dice_value1 = game_results[message_id1]['value']
        dice_value2 = game_results[message_id2]['value']
        product = dice_value1 * dice_value2
        
        # Проверяем выигрыш в зависимости от типа ставки
        if bet_type == "product":
            win = product > 18
            multiplier = 4.2
        else:
            win, multiplier = check_dice_bet_result(bet_type, dice_value1)
        
        result_text = get_dice_two_dice_result_text(bet_type, dice_value1, dice_value2, product, win, multiplier)
        
        if win:
            win_amount = int(bet_amount * multiplier)
            player.data[currency] += win_amount
            player.data["games_won"] += 1
            player.data["total_winnings"] += win_amount
            player.data["total_profit"] += (win_amount - bet_amount)
            
            # Обновляем серию побед
            player.data["current_win_streak"] += 1
            if player.data["current_win_streak"] > player.data["max_win_streak"]:
                player.data["max_win_streak"] = player.data["current_win_streak"]
            
            result_message = f"🎉 <b>ПОБЕДА!</b>\n{result_text}\n💰 Выигрыш: {win_amount} {currency_text}"
            
        else:
            player.data["total_profit"] -= bet_amount
            player.data["current_win_streak"] = 0
            result_message = f"❌ <b>ПРОИГРЫШ</b>\n{result_text}"
        
        # Обновляем аналитику
        update_game_analytics("dice_two", bet_amount, win_amount if win else 0, user_id)
        
        # Показываем результат
        send_message(chat_id,
            f"🎲 <b>Результат игры с двумя кубиками</b>\n\n"
            f"🎯 Ставка: <b>{get_bet_type_name(bet_type)}</b>\n"
            f"🎲 Первый кубик: <b>{dice_value1}</b>\n"
            f"🎲 Второй кубик: <b>{dice_value2}</b>\n"
            f"📊 Произведение: <b>{product}</b>\n\n"
            f"{result_message}\n"
            f"💎 Баланс: {player.data[currency]} {currency_text}",
            dice_game_keyboard()
        )
        
        # Очищаем результаты
        del game_results[message_id1]
        del game_results[message_id2]
        
    else:
        # Если не удалось получить результаты анимаций
        send_message(chat_id,
            f"🎲 <b>Игра завершена</b>\n\n"
            f"💰 Ставка: {bet_amount} {currency_text}\n"
            f"❌ Не удалось получить результаты\n"
            f"💎 Баланс: {player.data[currency]} {currency_text}",
            dice_game_keyboard()
        )
    
    auto_saver.mark_changed()

def get_dice_two_dice_result_text(bet_type, dice1, dice2, product, win, multiplier):
    """Генерирует текст результата для игры с двумя кубиками"""
    bet_names = {
        "product": "Произведение > 18"
    }
    
    bet_name = bet_names.get(bet_type, "Неизвестная ставка")
    
    if win:
        return f"✅ Ставка '{bet_name}' выиграла! (x{multiplier})"
    else:
        return f"❌ Ставка '{bet_name}' проиграла"

# ========== ИГРОВАЯ МЕХАНИКА ==========

def start_game_with_bet(user_id, chat_id, game_type, bet_amount, currency):
    """Запускает игру с ставкой"""
    player = Player(user_id)
    currency_text = "виртуальных монет" if currency == "coins" else "USDT"
    
    if player.data[currency] < bet_amount:
        send_message(chat_id, f"❌ Недостаточно средств! Баланс: {player.data[currency]} {currency_text}")
        return
    
    # Списываем ставку
    player.data[currency] -= bet_amount
    player.data["games_played"] += 1
    player.data["total_bet"] += bet_amount
    auto_saver.mark_changed()
    
    # Определяем эмодзи для игры
    emoji_map = {
        "slots": "🎰", "dice": "🎲", "darts": "🎯",
        "basketball": "🏀", "football": "⚽", "bowling": "🎳"
    }
    
    emoji = emoji_map.get(game_type, "🎲")
    
    # Отправляем анимацию
    send_message(chat_id, f"🎮 <b>Игра начинается!</b>\n💰 Ставка: {bet_amount} {currency_text}")
    time.sleep(1)
    
    dice_result = send_dice(chat_id, emoji)
    
    if not dice_result:
        send_message(chat_id, "❌ Ошибка запуска игры. Попробуйте еще раз.", games_menu_keyboard())
        # Возвращаем ставку при ошибке
        player.data[currency] += bet_amount
        player.data["games_played"] -= 1
        player.data["total_bet"] -= bet_amount
        auto_saver.mark_changed()
        return
    
    # Ждем завершения анимации
    time.sleep(4)
    
    # Получаем реальный результат анимации
    message_id = dice_result['result']['message_id']
    if message_id in game_results:
        dice_value = game_results[message_id]['value']
        
        # Анализируем реальный результат
        win, multiplier = analyze_dice_result(emoji, dice_value)
        result_text = get_dice_result_text(emoji, dice_value, win, multiplier)
        
        if win:
            win_amount = int(bet_amount * multiplier)
            player.data[currency] += win_amount
            player.data["games_won"] += 1
            player.data["total_winnings"] += win_amount
            player.data["total_profit"] += (win_amount - bet_amount)
            
            # Обновляем серию побед
            player.data["current_win_streak"] += 1
            if player.data["current_win_streak"] > player.data["max_win_streak"]:
                player.data["max_win_streak"] = player.data["current_win_streak"]
            
            result_message = f"🎉 <b>ПОБЕДА!</b>\n{result_text}\n💰 Выигрыш: {win_amount} {currency_text}"
            
        else:
            player.data["total_profit"] -= bet_amount
            player.data["current_win_streak"] = 0
            result_message = f"❌ <b>ПРОИГРЫШ</b>\n{result_text}"
        
        # Обновляем аналитику
        update_game_analytics(game_type, bet_amount, win_amount if win else 0, user_id)
        
        # Обновляем любимую игру
        if game_type not in player.data:
            player.data[game_type] = 0
        player.data[game_type] += 1
        
        # Определяем любимую игру
        game_counts = {game: player.data.get(game, 0) for game in emoji_map.keys()}
        player.data["favorite_game"] = max(game_counts, key=game_counts.get) if game_counts else None
        
        # Показываем результат
        send_message(chat_id,
            f"🎮 <b>Результат игры</b>\n\n"
            f"{result_message}\n"
            f"💎 Баланс: {player.data[currency]} {currency_text}",
            games_menu_keyboard()
        )
        
        # Очищаем результат
        del game_results[message_id]
        
    else:
        # Если не удалось получить результат анимации
        send_message(chat_id,
            f"🎮 <b>Игра завершена</b>\n\n"
            f"💰 Ставка: {bet_amount} {currency_text}\n"
            f"❌ Не удалось получить результат\n"
            f"💎 Баланс: {player.data[currency]} {currency_text}",
            games_menu_keyboard()
        )
    
    auto_saver.mark_changed()

def analyze_dice_result(emoji, dice_value):
    """Анализирует реальный результат анимации"""
    if emoji == "🎲":
        if dice_value >= 4:
            return True, dice_value * 0.5
        else:
            return False, 0
    elif emoji == "🎯":
        if dice_value == 6:
            return True, 2.0
        elif dice_value >= 4:
            return False, 0
        else:
            return False, 0
    elif emoji == "🏀":
        if dice_value >= 5:
            return True, 2.0
        elif dice_value >= 3:
            return False, 0
        else:
            return False, 0
    elif emoji == "⚽":
        if dice_value >= 5:
            return True, 2.0
        elif dice_value >= 3:
            return False, 0
        else:
            return False, 0
    elif emoji == "🎳":
        if dice_value == 6:
            return True, 1.5
        elif dice_value >= 4:
            return False, 0
        else:
            return False, 0
    elif emoji == "🎰":
        if dice_value == 1:
            return True, 10.0
        elif dice_value == 2:
            return True, 5.0
        elif dice_value == 3:
            return True, 3.0
        elif dice_value == 4:
            return True, 2.0
        elif dice_value == 5:
            return False, 0
        else:
            return False, 0
    return False, 0

def get_dice_result_text(emoji, dice_value, win, multiplier):
    """Генерирует текст результата"""
    if emoji == "🎲":
        if win:
            return f"🎯 Выпало: {dice_value} - Победа! (x{multiplier})"
        else:
            return f"❌ Выпало: {dice_value} - Проигрыш"
    elif emoji == "🎯":
        if dice_value == 6:
            return f"🎯 Прямо в цель! Буллсай! (x3.0)"
        elif dice_value >= 4:
            return f"❌ Промах! Мимо цели"
        else:
            return f"❌ Промах! Мимо цели"
    elif emoji == "🏀":
        if dice_value >= 5:
            return f"🏀 Трехочковый! Отличный бросок! (x1.2)"
        elif dice_value >= 3:
            return f"🏀 Попадание! Хороший бросок (x1.2)"
        else:
            return f"❌ Промах! Мяч не долетел"
    elif emoji == "⚽":
        if dice_value >= 5:
            return f"⚽ ГООООЛ! Отличный удар! (x2.5)"
        elif dice_value >= 3:
            return f"⚽ Попадание в створ! (x1.3)"
        else:
            return f"❌ Мимо ворот!"
    elif emoji == "🎳":
        if dice_value == 6:
            return f"🎳 СТРАЙК! Все кегли сбиты! (x3.0)"
        elif dice_value >= 4:
            return f"🎳 {dice_value} кеглей сбито! [х0]"
        else:
            return f"❌ Всего {dice_value} кеглей"
    elif emoji == "🎰":
        results = {
            1: "🎰 ДЖЕКПОТ! 777! (x10.0)",
            2: "🎰 Три бара! (x5.0)", 
            3: "🎰 Три лимона! (x3.0)",
            4: "🎰 Три вишни! (x2.0)",
            5: "❌ Повезет в следующий раз!",
            6: "❌ Повезет в следующий раз!"
        }
        return results.get(dice_value, "❌ Проигрыш")
    return "Неизвестный результат"

def play_dice_game(user_id, chat_id, bet_type, bet_amount, currency):
    """Игра в кости с новым интерфейсом"""
    # Если это ставка на произведение, используем два кубика
    if bet_type == "product":
        play_dice_game_two_dice(user_id, chat_id, bet_type, bet_amount, currency)
        return
    
    player = Player(user_id)
    currency_text = "виртуальных монет" if currency == "coins" else "USDT"
    
    if player.data[currency] < bet_amount:
        send_message(chat_id, f"❌ Недостаточно средств! Баланс: {player.data[currency]} {currency_text}")
        return
    
    # Списываем ставку
    player.data[currency] -= bet_amount
    player.data["games_played"] += 1
    player.data["total_bet"] += bet_amount
    auto_saver.mark_changed()
    
    # Отправляем анимацию кубика
    send_message(chat_id, f"🎲 <b>Бросаем кубик...</b>\n💰 Ставка: {bet_amount} {currency_text}")
    time.sleep(1)
    
    dice_result = send_dice(chat_id, "🎲")
    
    if not dice_result:
        send_message(chat_id, "❌ Ошибка запуска игры. Попробуйте еще раз.", dice_game_keyboard())
        # Возвращаем ставку при ошибке
        player.data[currency] += bet_amount
        player.data["games_played"] -= 1
        player.data["total_bet"] -= bet_amount
        auto_saver.mark_changed()
        return
    
    # Ждем завершения анимации
    time.sleep(4)
    
    # Получаем реальный результат анимации
    message_id = dice_result['result']['message_id']
    if message_id in game_results:
        dice_value = game_results[message_id]['value']
        
        # Проверяем выигрыш в зависимости от типа ставки
        win, multiplier = check_dice_bet_result(bet_type, dice_value)
        result_text = get_dice_bet_result_text(bet_type, dice_value, win, multiplier)
        
        if win:
            win_amount = int(bet_amount * multiplier)
            player.data[currency] += win_amount
            player.data["games_won"] += 1
            player.data["total_winnings"] += win_amount
            player.data["total_profit"] += (win_amount - bet_amount)
            
            # Обновляем серию побед
            player.data["current_win_streak"] += 1
            if player.data["current_win_streak"] > player.data["max_win_streak"]:
                player.data["max_win_streak"] = player.data["current_win_streak"]
            
            result_message = f"🎉 <b>ПОБЕДА!</b>\n{result_text}\n💰 Выигрыш: {win_amount} {currency_text}"
            
        else:
            player.data["total_profit"] -= bet_amount
            player.data["current_win_streak"] = 0
            result_message = f"❌ <b>ПРОИГРЫШ</b>\n{result_text}"
        
        # Обновляем аналитику
        update_game_analytics("dice", bet_amount, win_amount if win else 0, user_id)
        
        # Показываем результат
        send_message(chat_id,
            f"🎲 <b>Результат игры</b>\n\n"
            f"🎯 Ставка: <b>{get_bet_type_name(bet_type)}</b>\n"
            f"🎲 Выпало: <b>{dice_value}</b>\n\n"
            f"{result_message}\n"
            f"💎 Баланс: {player.data[currency]} {currency_text}",
            dice_game_keyboard()
        )
        
        # Очищаем результат
        del game_results[message_id]
        
    else:
        # Если не удалось получить результат анимации
        send_message(chat_id,
            f"🎲 <b>Игра завершена</b>\n\n"
            f"💰 Ставка: {bet_amount} {currency_text}\n"
            f"❌ Не удалось получить результат\n"
            f"💎 Баланс: {player.data[currency]} {currency_text}",
            dice_game_keyboard()
        )
    
    auto_saver.mark_changed()

def check_dice_bet_result(bet_type, dice_value):
    """Проверяет результат ставки в игре в кости"""
    bet_types = {
        "even": (dice_value % 2 == 0, 2.0),  # Чёт
        "odd": (dice_value % 2 == 1, 2.0),   # Нечёт
        "less": (dice_value < 4, 2.0),       # Меньше
        "more": (dice_value > 3, 2.0),       # Больше
        "one": (dice_value == 1, 6.0),       # 1
        "two": (dice_value == 2, 6.0),       # 2
        "three": (dice_value == 3, 6.0),     # 3
        "four": (dice_value == 4, 6.0),      # 4
        "five": (dice_value == 5, 6.0),      # 5
        "six": (dice_value == 6, 6.0),       # 6
        "ladder": (dice_value in [2, 3, 4, 5], 2.0)     # Лесенка
    }
    
    return bet_types.get(bet_type, (False, 0))

def get_dice_bet_result_text(bet_type, dice_value, win, multiplier):
    """Генерирует текст результата для игры в кости"""
    bet_names = {
        "even": "Чёт", "odd": "Нечёт", "less": "Меньше", "more": "Больше",
        "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
        "ladder": "Лесенка"
    }
    
    bet_name = bet_names.get(bet_type, "Неизвестная ставка")
    
    if win:
        return f"✅ Ставка '{bet_name}' выиграла! (x{multiplier})"
    else:
        return f"❌ Ставка '{bet_name}' проиграла"

def get_bet_type_name(bet_type):
    """Возвращает читаемое название типа ставки"""
    bet_names = {
        "even": "Чёт (x2)",
        "odd": "Нечёт (x2)", 
        "less": "Меньше (x2)",
        "more": "Больше (x2)",
        "one": "1 (x6)",
        "two": "2 (x6)", 
        "three": "3 (x6)",
        "four": "4 (x6)",
        "five": "5 (x6)",
        "six": "6 (x6)",
        "product": "Произведение > 18 (x4.2)",
        "ladder": "Лесенка (x2)"
    }
    return bet_names.get(bet_type, "Неизвестная ставка")

def update_game_analytics(game_type, bet_amount, win_amount, user_id):
    """Обновляет аналитику игр"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    if today not in game_analytics["daily_stats"]:
        game_analytics["daily_stats"][today] = {
            "total_games": 0, "total_bets": 0, "total_wins": 0,
            "unique_players": set(), "games_played": {}
        }
    
    daily_stats = game_analytics["daily_stats"][today]
    daily_stats["total_games"] += 1
    daily_stats["total_bets"] += bet_amount
    daily_stats["total_wins"] += win_amount
    daily_stats["unique_players"].add(user_id)
    
    if game_type not in daily_stats["games_played"]:
        daily_stats["games_played"][game_type] = 0
    daily_stats["games_played"][game_type] += 1
    
    if game_type not in game_analytics["game_popularity"]:
        game_analytics["game_popularity"][game_type] = 0
    game_analytics["game_popularity"][game_type] += 1
    
    user_str = str(user_id)
    if user_str not in game_analytics["user_activity"]:
        game_analytics["user_activity"][user_str] = {
            "last_activity": time.time(),
            "games_played": 0,
            "total_bets": 0
        }
    
    game_analytics["user_activity"][user_str]["last_activity"] = time.time()
    game_analytics["user_activity"][user_str]["games_played"] += 1
    game_analytics["user_activity"][user_str]["total_bets"] += bet_amount
    
    auto_saver.mark_changed()

# ========== КЛАВИАТУРЫ ==========

def main_menu_keyboard(user_id):
    keyboard = [
        [{"text": "👤 Профиль", "callback_data": "profile"}],
        [{"text": "🎮 Игры", "callback_data": "games"}],
        [{"text": "💳 Баланс", "callback_data": "balance"}],
        [{"text": "💰 Пополнить", "callback_data": "deposit"}, 
         {"text": "💸 Вывести", "callback_data": "withdraw"}],
        [{"text": "👥 Рефералы", "callback_data": "referral"},
         {"text": "💱 Валюта", "callback_data": "change_currency"}],
        [{"text": "🎁 Бонусы", "callback_data": "bonuses"},
         {"text": "🏆 Достижения", "callback_data": "achievements"}],
        [{"text": "📊 Статистика", "callback_data": "statistics"},
         {"text": "📞 Поддержка", "callback_data": "support"}],
        [{"text": "🏆 Топ игроков", "callback_data": "top_players"}]
    ]
    
    if user_id == ADMIN_ID:
        keyboard.append([{"text": "⚙️ Админ-панель", "callback_data": "admin_panel"}])
    
    return {"inline_keyboard": keyboard}

def profile_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📊 Статистика", "callback_data": "stats_personal"}],
            [{"text": "🏆 Достижения", "callback_data": "achievements"}],
            [{"text": "👥 Рефералы", "callback_data": "referral"}],
            [{"text": "⬅️ Главное меню", "callback_data": "main_menu"}]
        ]
    }

def games_menu_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "🎰 Слот-машина", "callback_data": "game_slots"}],
            [{"text": "🎲 Кости (новые)", "callback_data": "game_dice_new"}],
            [{"text": "🎯 Дартс", "callback_data": "game_darts"}],
            [{"text": "🏀 Баскетбол", "callback_data": "game_basketball"}],
            [{"text": "⚽ Футбол", "callback_data": "game_football"}],
            [{"text": "🎳 Боулинг", "callback_data": "game_bowling"}],
            [{"text": "🎿 Санки (RampageBET)", "callback_data": "game_sledge"}],
            [{"text": "⬅️ Назад", "callback_data": "main_menu"}]
        ]
    }

def sledge_game_keyboard(game_id):
    """Клавиатура для игры Санки во время анимации"""
    return {
        "inline_keyboard": [
            [{"text": "🔄 Обновить", "callback_data": f"sledge_refresh_{game_id}"}],
            [{"text": "❌ Отменить игру", "callback_data": f"sledge_cancel_{game_id}"}]
        ]
    }

def sledge_game_finished_keyboard():
    """Клавиатура после завершения игры Санки"""
    return {
        "inline_keyboard": [
            [{"text": "🎿 Играть снова", "callback_data": "game_sledge"}],
            [{"text": "⬅️ Назад к играм", "callback_data": "games"}]
        ]
    }

def sledge_bet_amount_keyboard():
    """Клавиатура выбора суммы ставки для игры Санки"""
    amounts = [10, 25, 50, 100, 200, 500]
    
    keyboard = []
    row = []
    for amount in amounts:
        row.append({"text": f"{amount}", "callback_data": f"sledge_amount_{amount}"})
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([{"text": "💵 Своя сумма", "callback_data": "sledge_amount_custom"}])
    keyboard.append([{"text": "⬅️ Назад", "callback_data": "games"}])
    
    return {"inline_keyboard": keyboard}

def dice_game_keyboard():
    """Клавиатура для новой игры в кости"""
    return {
        "inline_keyboard": [
            [
                {"text": "Чёт (x2)", "callback_data": "dice_bet_even"},
                {"text": "Нечёт (x2)", "callback_data": "dice_bet_odd"}
            ],
            [
                {"text": "Меньше (x2)", "callback_data": "dice_bet_less"},
                {"text": "Больше (x2)", "callback_data": "dice_bet_more"}
            ],
            [
                {"text": "1 (x6)", "callback_data": "dice_bet_one"},
                {"text": "2 (x6)", "callback_data": "dice_bet_two"},
                {"text": "3 (x6)", "callback_data": "dice_bet_three"}
            ],
            [
                {"text": "4 (x6)", "callback_data": "dice_bet_four"},
                {"text": "5 (x6)", "callback_data": "dice_bet_five"},
                {"text": "6 (x6)", "callback_data": "dice_bet_six"}
            ],
            [
                {"text": "Произведение > 18 (x4.2)", "callback_data": "dice_bet_product"}
            ],
            [
                {"text": "Лесенка (x2)", "callback_data": "dice_bet_ladder"}
            ],
            [
                {"text": "⬅️ Назад", "callback_data": "games"}
            ]
        ]
    }

def deposit_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "💵 USDT (через @CryptoBot)", "callback_data": "deposit_cryptobot"}],
            [{"text": "⬅️ Главное меню", "callback_data": "main_menu"}]
        ]
    }

def withdraw_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "💵 Вывести USDT", "callback_data": "withdraw_cryptobot"}],
            [{"text": "⬅️ Главное меню", "callback_data": "main_menu"}]
        ]
    }

def bonuses_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "🎁 Ежедневный бонус", "callback_data": "bonus_daily"}],
            [{"text": "📅 Недельный бонус", "callback_data": "bonus_weekly"}],
            [{"text": "⬅️ Назад", "callback_data": "main_menu"}]
        ]
    }

def achievements_keyboard(user_id):
    user_str = str(user_id)
    keyboard = []
    
    for achievement_id, achievement in ACHIEVEMENTS_CONFIG.items():
        if user_str in achievements and achievement_id in achievements[user_str]:
            status = "✅" if achievements[user_str][achievement_id]["reward_claimed"] else "💰"
            keyboard.append([{"text": f"{status} {achievement['name']}", "callback_data": f"achievement_{achievement_id}"}])
        else:
            keyboard.append([{"text": f"❌ {achievement['name']}", "callback_data": f"achievement_{achievement_id}"}])
    
    keyboard.append([{"text": "⬅️ Назад", "callback_data": "main_menu"}])
    return {"inline_keyboard": keyboard}

def statistics_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📈 Графики аналитики", "callback_data": "stats_analytics"}],
            [{"text": "🎮 Моя статистика", "callback_data": "stats_personal"}],
            [{"text": "📊 Общая статистика", "callback_data": "stats_global"}],
            [{"text": "⬅️ Назад", "callback_data": "main_menu"}]
        ]
    }

def support_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "💬 Создать тикет", "callback_data": "support_create"}],
            [{"text": "📋 Мои тикеты", "callback_data": "support_my_tickets"}],
            [{"text": "⬅️ Назад", "callback_data": "main_menu"}]
        ]
    }

def bet_amount_keyboard(game_type):
    amounts = [10, 25, 50, 100, 200]
    
    keyboard = []
    row = []
    for amount in amounts:
        row.append({"text": f"{amount}", "callback_data": f"bet_{game_type}_{amount}"})
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([{"text": "💵 Своя сумма", "callback_data": f"bet_{game_type}_custom"}])
    keyboard.append([{"text": "⬅️ Назад", "callback_data": "games"}])
    
    return {"inline_keyboard": keyboard}

def dice_bet_amount_keyboard(bet_type):
    """Клавиатура выбора суммы ставки для новой игры в кости"""
    amounts = [10, 25, 50, 100, 200]
    
    keyboard = []
    row = []
    for amount in amounts:
        row.append({"text": f"{amount}", "callback_data": f"dice_amount_{bet_type}_{amount}"})
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([{"text": "💵 Своя сумма", "callback_data": f"dice_amount_{bet_type}_custom"}])
    keyboard.append([{"text": "⬅️ Назад", "callback_data": "game_dice_new"}])
    
    return {"inline_keyboard": keyboard}

def back_to_main_keyboard():
    return {"inline_keyboard": [[{"text": "⬅️ Главное меню", "callback_data": "main_menu"}]]}

def cancel_operation_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "❌ Отменить операцию", "callback_data": "cancel_operation"}]
        ]
    }

def referral_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "👥 Моя реферальная ссылка", "callback_data": "my_referral_link"}],
            [{"text": "💰 Вывести реферальные", "callback_data": "withdraw_referral"}],
            [{"text": "📊 Статистика", "callback_data": "referral_stats"}],
            [{"text": "⬅️ Главное меню", "callback_data": "main_menu"}]
        ]
    }

def currency_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "💵 USDT", "callback_data": "currency_usdt"}],
            [{"text": "🪙 Виртуальные монеты", "callback_data": "currency_coins"}],
            [{"text": "⬅️ Главное меню", "callback_data": "main_menu"}]
        ]
    }

def admin_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📊 Статистика бота", "callback_data": "admin_stats"}],
            [{"text": "👤 Управление пользователями", "callback_data": "admin_users"}],
            [{"text": "💰 Выдать валюту", "callback_data": "admin_give_currency"}],
            [{"text": "💰 Запросы на пополнение", "callback_data": "admin_deposits_list"}],
            [{"text": "💸 Запросы на вывод", "callback_data": "admin_withdrawals_list"}],
            [{"text": "📞 Тикеты поддержки", "callback_data": "admin_support_tickets"}],
            [{"text": "📈 Аналитика", "callback_data": "admin_analytics"}],
            [{"text": "⚙️ Настройки", "callback_data": "admin_settings"}],
            [{"text": "💾 Сохранить данные", "callback_data": "admin_save"}],
            [{"text": "⬅️ Главное меню", "callback_data": "main_menu"}]
        ]
    }

def admin_give_currency_keyboard():
    """Клавиатура для выдачи валюты"""
    return {
        "inline_keyboard": [
            [{"text": "💵 Выдать USDT", "callback_data": "admin_give_usdt"}],
            [{"text": "🪙 Выдать монеты", "callback_data": "admin_give_coins"}],
            [{"text": "👥 Выдать реферальные", "callback_data": "admin_give_referral"}],
            [{"text": "⬅️ Назад", "callback_data": "admin_panel"}]
        ]
    }

def admin_users_list_keyboard():
    """Клавиатура списка пользователей"""
    user_list = list(players.items())[:10]
    
    keyboard = []
    for user_id, user_data in user_list:
        username = user_data.get("username", "Без имени")
        balance = user_data.get("usdt", 0)
        
        keyboard.append([
            {
                "text": f"👤 {username} - {balance:.2f} USDT", 
                "callback_data": f"admin_user_view_{user_id}"
            }
        ])
    
    keyboard.append([{"text": "🔄 Обновить", "callback_data": "admin_users"}])
    keyboard.append([{"text": "⬅️ Назад", "callback_data": "admin_panel"}])
    
    return {"inline_keyboard": keyboard}

def admin_user_details_keyboard(user_id):
    """Клавиатура действий для конкретного пользователя"""
    return {
        "inline_keyboard": [
            [
                {"text": "💰 Пополнить баланс", "callback_data": f"admin_user_add_{user_id}"},
                {"text": "💸 Снять баланс", "callback_data": f"admin_user_remove_{user_id}"}
            ],
            [
                {"text": "💵 Выдать USDT", "callback_data": f"admin_give_usdt_user_{user_id}"},
                {"text": "🪙 Выдать монеты", "callback_data": f"admin_give_coins_user_{user_id}"}
            ],
            [
                {"text": "📊 Статистика", "callback_data": f"admin_user_stats_{user_id}"},
                {"text": "⚙️ Сбросить", "callback_data": f"admin_user_reset_{user_id}"}
            ],
            [
                {"text": "⬅️ Назад к списку", "callback_data": "admin_users"}
            ]
        ]
    }

def admin_deposits_list_keyboard():
    """Клавиатура списка запросов на пополнение"""
    pending_deposits = [k for k, v in deposit_requests.items() if v.get("status") == "pending"]
    
    keyboard = []
    for deposit_id in pending_deposits[:10]:
        deposit = deposit_requests[deposit_id]
        amount = deposit["amount"]
        user_id = deposit["user_id"]
        user_data = get_user_balance(user_id)
        username = user_data.get("username", "Без имени")
        
        keyboard.append([
            {
                "text": f"💰 {username} - {amount} USDT", 
                "callback_data": f"admin_deposit_view_{deposit_id}"
            }
        ])
    
    if not keyboard:
        keyboard.append([{"text": "✅ Нет ожидающих запросов", "callback_data": "none"}])
    
    keyboard.append([{"text": "🔄 Обновить", "callback_data": "admin_deposits_list"}])
    keyboard.append([{"text": "⬅️ Назад", "callback_data": "admin_panel"}])
    
    return {"inline_keyboard": keyboard}

def admin_withdrawals_list_keyboard():
    """Клавиатура списка запросов на вывод"""
    pending_withdrawals = [k for k, v in withdraw_requests.items() if v.get("status") == "pending"]
    
    keyboard = []
    for withdraw_id in pending_withdrawals[:10]:
        withdraw = withdraw_requests[withdraw_id]
        amount = withdraw["amount"]
        user_id = withdraw["user_id"]
        user_data = get_user_balance(user_id)
        username = user_data.get("username", "Без имени")
        
        keyboard.append([
            {
                "text": f"💸 {username} - {amount} USDT", 
                "callback_data": f"admin_withdraw_view_{withdraw_id}"
            }
        ])
    
    if not keyboard:
        keyboard.append([{"text": "✅ Нет ожидающих запросов", "callback_data": "none"}])
    
    keyboard.append([{"text": "🔄 Обновить", "callback_data": "admin_withdrawals_list"}])
    keyboard.append([{"text": "⬅️ Назад", "callback_data": "admin_panel"}])
    
    return {"inline_keyboard": keyboard}

def admin_deposit_details_keyboard(deposit_id):
    """Клавиатура действий для конкретного пополнения"""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Подтвердить", "callback_data": f"admin_deposit_approve_{deposit_id}"},
                {"text": "❌ Отклонить", "callback_data": f"admin_deposit_reject_{deposit_id}"}
            ],
            [
                {"text": "⬅️ Назад к списку", "callback_data": "admin_deposits_list"}
            ]
        ]
    }

def admin_withdraw_details_keyboard(withdraw_id):
    """Клавиатура действий для конкретного вывода"""
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Подтвердить", "callback_data": f"admin_withdraw_approve_{withdraw_id}"},
                {"text": "❌ Отклонить", "callback_data": f"admin_withdraw_reject_{withdraw_id}"}
            ],
            [
                {"text": "⬅️ Назад к списку", "callback_data": "admin_withdrawals_list"}
            ]
        ]
    }

def admin_support_tickets_keyboard():
    """Клавиатура списка тикетов поддержки"""
    open_tickets = [k for k, v in support_tickets.items() if v.get("status") == "open"]
    
    keyboard = []
    for ticket_id in open_tickets[:10]:
        ticket = support_tickets[ticket_id]
        username = ticket.get("username", "Без имени")
        message_preview = ticket["message"][:30] + "..." if len(ticket["message"]) > 30 else ticket["message"]
        
        keyboard.append([
            {
                "text": f"📞 {username}: {message_preview}", 
                "callback_data": f"admin_ticket_view_{ticket_id}"
            }
        ])
    
    if not keyboard:
        keyboard.append([{"text": "✅ Нет открытых тикетов", "callback_data": "none"}])
    
    keyboard.append([{"text": "🔄 Обновить", "callback_data": "admin_support_tickets"}])
    keyboard.append([{"text": "⬅️ Назад", "callback_data": "admin_panel"}])
    
    return {"inline_keyboard": keyboard}

def admin_ticket_details_keyboard(ticket_id):
    """Клавиатура действий для тикета"""
    return {
        "inline_keyboard": [
            [
                {"text": "💬 Ответить", "callback_data": f"admin_ticket_reply_{ticket_id}"},
                {"text": "✅ Закрыть", "callback_data": f"admin_ticket_close_{ticket_id}"}
            ],
            [
                {"text": "⬅️ Назад к списку", "callback_data": "admin_support_tickets"}
            ]
        ]
    }

# ========== АДМИН ФУНКЦИИ ==========

def approve_deposit(deposit_id):
    """Подтверждение пополнения"""
    if deposit_id not in deposit_requests:
        return False, "Запрос не найден"
    
    deposit = deposit_requests[deposit_id]
    if deposit["status"] != "pending":
        return False, "Запрос уже обработан"
    
    user_id = deposit["user_id"]
    amount = deposit["amount"]
    
    # Зачисляем средства
    player = Player(user_id)
    player.data["usdt"] += amount
    player.data["total_deposits"] += amount
    
    # Начисляем реферальный бонус
    if player.data.get("referrer_id"):
        referrer_id = player.data["referrer_id"]
        referrer = Player(referrer_id)
        referral_bonus = amount * GAME_SETTINGS["referral_bonus"]
        referrer.data["referral_balance"] += referral_bonus
        referrer.data["referral_earnings"] += referral_bonus
    
    deposit["status"] = "approved"
    deposit["processed_at"] = time.time()
    
    auto_saver.mark_changed()
    return True, f"Пополнение на {amount} USDT подтверждено"

def reject_deposit(deposit_id):
    """Отклонение пополнения"""
    if deposit_id not in deposit_requests:
        return False, "Запрос не найден"
    
    deposit = deposit_requests[deposit_id]
    if deposit["status"] != "pending":
        return False, "Запрос уже обработан"
    
    deposit["status"] = "rejected"
    deposit["processed_at"] = time.time()
    
    auto_saver.mark_changed()
    return True, "Пополнение отклонено"

def approve_withdraw(withdraw_id):
    """Подтверждение вывода"""
    if withdraw_id not in withdraw_requests:
        return False, "Запрос не найден"
    
    withdraw = withdraw_requests[withdraw_id]
    if withdraw["status"] != "pending":
        return False, "Запрос уже обработан"
    
    user_id = withdraw["user_id"]
    amount = withdraw["amount"]
    
    # Проверяем баланс
    player = Player(user_id)
    if player.data["usdt"] < amount:
        return False, "Недостаточно средств у пользователя"
    
    # Списываем средства
    player.data["usdt"] -= amount
    player.data["total_withdrawals"] += amount
    
    withdraw["status"] = "approved"
    withdraw["processed_at"] = time.time()
    
    auto_saver.mark_changed()
    return True, f"Вывод на {amount} USDT подтвержден"

def reject_withdraw(withdraw_id):
    """Отклонение вывода"""
    if withdraw_id not in withdraw_requests:
        return False, "Запрос не найден"
    
    withdraw = withdraw_requests[withdraw_id]
    if withdraw["status"] != "pending":
        return False, "Запрос уже обработан"
    
    withdraw["status"] = "rejected"
    withdraw["processed_at"] = time.time()
    
    auto_saver.mark_changed()
    return True, "Вывод отклонен"

def admin_add_balance(user_id, amount):
    """Админ добавляет баланс пользователю"""
    player = Player(user_id)
    player.data["usdt"] += amount
    auto_saver.mark_changed()
    return True, f"Баланс пользователя пополнен на {amount} USDT"

def admin_remove_balance(user_id, amount):
    """Админ снимает баланс у пользователя"""
    player = Player(user_id)
    if player.data["usdt"] < amount:
        return False, "Недостаточно средств у пользователя"
    
    player.data["usdt"] -= amount
    auto_saver.mark_changed()
    return True, f"С пользователя списано {amount} USDT"

def admin_give_currency(user_id, currency_type, amount):
    """Админ выдает валюту пользователю"""
    player = Player(user_id)
    
    if currency_type == "usdt":
        player.data["usdt"] += amount
        message = f"💵 Пользователю выдано {amount} USDT"
    elif currency_type == "coins":
        player.data["coins"] += amount
        message = f"🪙 Пользователю выдано {amount} монет"
    elif currency_type == "referral":
        player.data["referral_balance"] += amount
        message = f"👥 Пользователю выдано {amount} USDT реферальных"
    else:
        return False, "Неизвестный тип валюты"
    
    auto_saver.mark_changed()
    return True, message

# ========== ОБРАБОТКА СООБЩЕНИЙ ==========

def handle_message(message):
    try:
        chat_id = message["chat"]["id"]
        user_id = message["from"]["id"]
        text = message.get("text", "")
        username = message["from"].get("username", "")
        
        if not anti_cheat.check_rate_limit(user_id, "message"):
            send_message(chat_id, "❌ Слишком много запросов! Подождите минуту.")
            return
        
        player = Player(user_id)
        player.data["username"] = username
        
        current_state = user_states.get(user_id, {})
        
        if "state" in current_state:
            state = current_state["state"]
            
            if state.startswith("waiting_bet_amount_"):
                game_type = state.replace("waiting_bet_amount_", "")
                try:
                    amount = float(text.replace(',', '.'))
                    currency = player.data["game_currency"]
                    
                    is_valid, error_msg = validate_bet_amount(user_id, amount, currency)
                    if not is_valid:
                        send_message(chat_id, f"❌ {error_msg}")
                        return
                    
                    if not anti_cheat.check_rate_limit(user_id, "bet"):
                        send_message(chat_id, "❌ Слишком много ставок! Подождите минуту.")
                        return
                    
                    user_states.pop(user_id, None)
                    start_game_with_bet(user_id, chat_id, game_type, amount, currency)
                    
                except ValueError:
                    send_message(chat_id, "❌ Введите корректную сумму (например: 50 или 100)")
                return
            
            elif state.startswith("waiting_dice_amount_"):
                bet_type = state.replace("waiting_dice_amount_", "")
                try:
                    amount = float(text.replace(',', '.'))
                    currency = player.data["game_currency"]
                    
                    is_valid, error_msg = validate_bet_amount(user_id, amount, currency)
                    if not is_valid:
                        send_message(chat_id, f"❌ {error_msg}")
                        return
                    
                    if not anti_cheat.check_rate_limit(user_id, "bet"):
                        send_message(chat_id, "❌ Слишком много ставок! Подождите минуту.")
                        return
                    
                    user_states.pop(user_id, None)
                    play_dice_game(user_id, chat_id, bet_type, amount, currency)
                    
                except ValueError:
                    send_message(chat_id, "❌ Введите корректную сумму (например: 50 или 100)")
                return
            
            # НОВОЕ СОСТОЯНИЕ ДЛЯ ИГРЫ САНКИ
            elif state == "waiting_sledge_amount":
                try:
                    amount = float(text.replace(',', '.'))
                    currency = player.data["game_currency"]
                    
                    is_valid, error_msg = validate_bet_amount(user_id, amount, currency)
                    if not is_valid:
                        send_message(chat_id, f"❌ {error_msg}")
                        return
                    
                    if not anti_cheat.check_rate_limit(user_id, "bet"):
                        send_message(chat_id, "❌ Слишком много ставок! Подождите минуту.")
                        return
                    
                    user_states.pop(user_id, None)
                    play_sledge_game(user_id, chat_id, amount, currency)
                    
                except ValueError:
                    send_message(chat_id, "❌ Введите корректную сумму (например: 50 или 100)")
                return
            
            elif state == "waiting_deposit_amount":
                if text == "/cancel":
                    user_states.pop(user_id, None)
                    send_message(chat_id, "❌ Операция отменена", main_menu_keyboard(user_id))
                    return
                    
                try:
                    amount = float(text.replace(',', '.'))
                    if amount < GAME_SETTINGS["min_deposit"]:
                        send_message(chat_id, f"❌ Минимальное пополнение: {GAME_SETTINGS['min_deposit']} USDT", cancel_operation_keyboard())
                        return
                    
                    user_states[user_id] = {
                        "state": "waiting_deposit_check",
                        "deposit_amount": amount
                    }
                    
                    send_message(chat_id,
                        f"💰 <b>Пополнение на {amount} USDT</b>\n\n"
                        f"📋 <b>Инструкция:</b>\n"
                        f"1. Перейдите в @CryptoBot\n"
                        f"2. Создайте чек на сумму {amount} USDT\n"
                        f"3. Укажите получателем: {ADMIN_USERNAME}\n"
                        f"4. Отправьте ссылку на чек в этот чат\n\n"
                        f"⚠️ <b>ВАЖНО:</b> Указывайте точную сумму {amount} USDT\n"
                        f"После проверки администратором средства будут зачислены.",
                        cancel_operation_keyboard()
                    )
                    
                except ValueError:
                    send_message(chat_id, "❌ Введите корректную сумму (например: 50 или 100)", cancel_operation_keyboard())
                return
            
            elif state == "waiting_deposit_check":
                if text == "/cancel":
                    user_states.pop(user_id, None)
                    send_message(chat_id, "❌ Операция отменена", main_menu_keyboard(user_id))
                    return
                    
                if text.startswith("https://t.me/CryptoBot") or "crypto" in text.lower():
                    amount = current_state["deposit_amount"]
                    deposit_id = f"DEP{int(time.time())}{user_id}"
                    deposit_requests[deposit_id] = {
                        "user_id": user_id,
                        "amount": amount,
                        "check_url": text,
                        "status": "pending",
                        "timestamp": time.time()
                    }
                    
                    send_message(chat_id,
                        f"✅ <b>Запрос на пополнение создан!</b>\n\n"
                        f"💰 Сумма: {amount} USDT\n"
                        f"📋 ID заявки: {deposit_id}\n"
                        f"🔗 Чек отправлен на проверку\n\n"
                        f"Администратор проверит заявку в ближайшее время.\n"
                        f"После подтверждения средства будут зачислены на ваш баланс.",
                        main_menu_keyboard(user_id)
                    )
                    
                    user_states.pop(user_id, None)
                else:
                    send_message(chat_id, 
                        "❌ Это не похоже на ссылку из @CryptoBot\n\n"
                        "Пожалуйста, отправьте корректную ссылку на чек.\n"
                        "Или введите /cancel для отмены операции.",
                        cancel_operation_keyboard()
                    )
                return
            
            elif state == "waiting_withdraw_amount":
                if text == "/cancel":
                    user_states.pop(user_id, None)
                    send_message(chat_id, "❌ Операция отменена", main_menu_keyboard(user_id))
                    return
                    
                try:
                    amount = float(text.replace(',', '.'))
                    if amount < GAME_SETTINGS["min_withdraw"]:
                        send_message(chat_id, f"❌ Минимальный вывод: {GAME_SETTINGS['min_withdraw']} USDT", cancel_operation_keyboard())
                        return
                    
                    if player.data["usdt"] < amount:
                        send_message(chat_id, f"❌ Недостаточно средств. Баланс: {player.data['usdt']:.2f} USDT", cancel_operation_keyboard())
                        return
                    
                    user_states[user_id] = {
                        "state": "waiting_withdraw_wallet",
                        "withdraw_amount": amount
                    }
                    
                    send_message(chat_id,
                        f"💸 <b>Вывод {amount} USDT</b>\n\n"
                        f"Введите адрес кошелька USDT (TRC20):\n\n"
                        f"Пример: <code>TBa1ysyFp7C5VqmoPxQrxd6F6S9b3Z2E4X</code>\n\n"
                        f"Или введите /cancel для отмены",
                        cancel_operation_keyboard()
                    )
                    
                except ValueError:
                    send_message(chat_id, "❌ Введите корректную сумму (например: 50 или 100)", cancel_operation_keyboard())
                return
            
            elif state == "waiting_withdraw_wallet":
                if text == "/cancel":
                    user_states.pop(user_id, None)
                    send_message(chat_id, "❌ Операция отменена", main_menu_keyboard(user_id))
                    return
                    
                wallet_address = text.strip()
                amount = current_state["withdraw_amount"]
                
                if len(wallet_address) < 20 or not wallet_address.startswith("T"):
                    send_message(chat_id, 
                        "❌ Неверный формат кошелька USDT\n\n"
                        "Пожалуйста, введите корректный адрес TRC20 (начинается с T)\n"
                        "Или введите /cancel для отмены",
                        cancel_operation_keyboard()
                    )
                    return
                
                withdraw_id = f"WD{int(time.time())}{user_id}"
                withdraw_requests[withdraw_id] = {
                    "user_id": user_id,
                    "amount": amount,
                    "wallet_address": wallet_address,
                    "status": "pending",
                    "timestamp": time.time()
                }
                
                send_message(chat_id,
                    f"✅ <b>Заявка на вывод создана!</b>\n\n"
                    f"💰 Сумма: {amount} USDT\n"
                    f"🏦 Кошелек: <code>{wallet_address}</code>\n"
                    f"📋 ID заявки: {withdraw_id}\n\n"
                    f"Администратор проверит заявку в ближайшее время.\n"
                    f"После подтверждения средства будут отправлены в течение 24 часов.",
                    main_menu_keyboard(user_id)
                )
                
                user_states.pop(user_id, None)
                return
            
            elif state == "waiting_support_message":
                if text == "/cancel":
                    user_states.pop(user_id, None)
                    send_message(chat_id, "❌ Создание тикета отменено", main_menu_keyboard(user_id))
                    return
                
                if len(text) < 5:
                    send_message(chat_id, "❌ Сообщение слишком короткое. Опишите проблему подробнее.", cancel_operation_keyboard())
                    return
                
                ticket_id = f"TICKET{int(time.time())}{user_id}"
                support_tickets[ticket_id] = {
                    "user_id": user_id,
                    "username": username,
                    "message": text,
                    "status": "open",
                    "created_at": time.time(),
                    "admin_response": None,
                    "response_time": None
                }
                
                send_message(user_id,
                    f"✅ <b>Тикет создан!</b>\n\n"
                    f"📋 ID: {ticket_id}\n"
                    f"💬 Ваше сообщение: {text}\n\n"
                    f"Администратор ответит в ближайшее время.",
                    main_menu_keyboard(user_id)
                )
                
                user_states.pop(user_id, None)
                return
            
            # Админские состояния
            elif state.startswith("admin_reply_ticket_"):
                ticket_id = state.replace("admin_reply_ticket_", "")
                if ticket_id in support_tickets:
                    support_tickets[ticket_id]["admin_response"] = text
                    support_tickets[ticket_id]["response_time"] = time.time()
                    support_tickets[ticket_id]["status"] = "answered"
                    
                    # Отправляем ответ пользователю
                    user_id = support_tickets[ticket_id]["user_id"]
                    send_message(user_id,
                        f"📞 <b>Ответ от поддержки</b>\n\n"
                        f"💬 Ваш тикет: {support_tickets[ticket_id]['message']}\n\n"
                        f"👨‍💼 <b>Ответ администратора:</b>\n"
                        f"{text}\n\n"
                        f"📋 ID тикета: {ticket_id}",
                        main_menu_keyboard(user_id)
                    )
                    
                    send_message(chat_id, f"✅ Ответ на тикет {ticket_id} отправлен пользователю", admin_keyboard())
                else:
                    send_message(chat_id, "❌ Тикет не найден", admin_keyboard())
                
                user_states.pop(user_id, None)
                return
            
            elif state.startswith("admin_add_balance_"):
                target_user_id = int(state.replace("admin_add_balance_", ""))
                try:
                    amount = float(text.replace(',', '.'))
                    success, message = admin_add_balance(target_user_id, amount)
                    send_message(chat_id, f"✅ {message}", admin_keyboard())
                except ValueError:
                    send_message(chat_id, "❌ Введите корректную сумму", admin_keyboard())
                
                user_states.pop(user_id, None)
                return
            
            elif state.startswith("admin_remove_balance_"):
                target_user_id = int(state.replace("admin_remove_balance_", ""))
                try:
                    amount = float(text.replace(',', '.'))
                    success, message = admin_remove_balance(target_user_id, amount)
                    send_message(chat_id, f"✅ {message}", admin_keyboard())
                except ValueError:
                    send_message(chat_id, "❌ Введите корректную сумму", admin_keyboard())
                
                user_states.pop(user_id, None)
                return
            
            # Новые состояния для выдачи валюты админом
            elif state.startswith("admin_give_usdt_"):
                try:
                    amount = float(text.replace(',', '.'))
                    if state == "admin_give_usdt_all":
                        # Выдача всем пользователям
                        for uid in players:
                            admin_give_currency(int(uid), "usdt", amount)
                        send_message(chat_id, f"✅ Всем пользователям выдано {amount} USDT", admin_keyboard())
                    else:
                        # Выдача конкретному пользователю
                        target_user_id = int(state.replace("admin_give_usdt_", "").replace("user_", ""))
                        success, message_text = admin_give_currency(target_user_id, "usdt", amount)
                        send_message(chat_id, f"✅ {message_text}", admin_keyboard())
                    
                    user_states.pop(user_id, None)
                except ValueError:
                    send_message(chat_id, "❌ Введите корректную сумму", admin_keyboard())
                return
            
            elif state.startswith("admin_give_coins_"):
                try:
                    amount = float(text.replace(',', '.'))
                    if state == "admin_give_coins_all":
                        # Выдача всем пользователям
                        for uid in players:
                            admin_give_currency(int(uid), "coins", amount)
                        send_message(chat_id, f"✅ Всем пользователям выдано {amount} монет", admin_keyboard())
                    else:
                        # Выдача конкретному пользователю
                        target_user_id = int(state.replace("admin_give_coins_", "").replace("user_", ""))
                        success, message_text = admin_give_currency(target_user_id, "coins", amount)
                        send_message(chat_id, f"✅ {message_text}", admin_keyboard())
                    
                    user_states.pop(user_id, None)
                except ValueError:
                    send_message(chat_id, "❌ Введите корректную сумму", admin_keyboard())
                return
            
            elif state.startswith("admin_give_referral_"):
                try:
                    amount = float(text.replace(',', '.'))
                    if state == "admin_give_referral_all":
                        # Выдача всем пользователям
                        for uid in players:
                            admin_give_currency(int(uid), "referral", amount)
                        send_message(chat_id, f"✅ Всем пользователям выдано {amount} USDT реферальных", admin_keyboard())
                    else:
                        # Выдача конкретному пользователю
                        target_user_id = int(state.replace("admin_give_referral_", "").replace("user_", ""))
                        success, message_text = admin_give_currency(target_user_id, "referral", amount)
                        send_message(chat_id, f"✅ {message_text}", admin_keyboard())
                    
                    user_states.pop(user_id, None)
                except ValueError:
                    send_message(chat_id, "❌ Введите корректную сумму", admin_keyboard())
                return
            
            # Новые состояния для CryptoBot
            elif state == "waiting_deposit_amount_cryptobot":
                if text == "/cancel":
                    user_states.pop(user_id, None)
                    send_message(chat_id, "❌ Операция отменена", main_menu_keyboard(user_id))
                    return
                    
                try:
                    amount = float(text.replace(',', '.'))
                    if amount < GAME_SETTINGS["min_deposit"]:
                        send_message(chat_id, f"❌ Минимальное пополнение: {GAME_SETTINGS['min_deposit']} USDT", cancel_operation_keyboard())
                        return
                    
                    # Создаем инвойс в CryptoBot
                    invoice = create_cryptobot_invoice(amount, user_id, f"Пополнение баланса на {amount} USDT")
                    
                    if invoice:
                        send_message(chat_id,
                            f"💰 <b>Счет для пополнения создан!</b>\n\n"
                            f"💵 Сумма: {amount} USDT\n"
                            f"💸 Комиссия: {DEPOSIT_COMMISSION*100}%\n"
                            f"🎯 К зачислению: {amount * (1 - DEPOSIT_COMMISSION):.2f} USDT\n\n"
                            f"🔗 <a href='{invoice['pay_url']}'>Оплатить через CryptoBot</a>\n\n"
                            f"📋 Инструкция:\n"
                            f"1. Нажмите на ссылку выше\n"
                            f"2. Оплатите счет в боте\n"
                            f"3. Средства будут зачислены автоматически\n\n"
                            f"⏳ Счет действителен 1 час",
                            back_to_main_keyboard()
                        )
                    else:
                        send_message(chat_id, "❌ Ошибка создания счета. Попробуйте позже.", main_menu_keyboard(user_id))
                    
                    user_states.pop(user_id, None)
                    
                except ValueError:
                    send_message(chat_id, "❌ Введите корректную сумму (например: 50 или 100)", cancel_operation_keyboard())
                return
            
            elif state == "waiting_withdraw_amount_cryptobot":
                if text == "/cancel":
                    user_states.pop(user_id, None)
                    send_message(chat_id, "❌ Операция отменена", main_menu_keyboard(user_id))
                    return
                    
                try:
                    amount = float(text.replace(',', '.'))
                    if amount < GAME_SETTINGS["min_withdraw"]:
                        send_message(chat_id, f"❌ Минимальный вывод: {GAME_SETTINGS['min_withdraw']} USDT", cancel_operation_keyboard())
                        return
                    
                    if player.data["usdt"] < amount:
                        send_message(chat_id, f"❌ Недостаточно средств. Баланс: {player.data['usdt']:.2f} USDT", cancel_operation_keyboard())
                        return
                    
                    user_states[user_id] = {
                        "state": "waiting_withdraw_wallet_cryptobot",
                        "withdraw_amount": amount
                    }
                    
                    send_message(chat_id,
                        f"💸 <b>Вывод {amount} USDT</b>\n\n"
                        f"Введите адрес кошелька USDT (TRC20):\n\n"
                        f"Пример: <code>TBa1ysyFp7C5VqmoPxQrxd6F6S9b3Z2E4X</code>\n\n"
                        f"Или введите /cancel для отмены",
                        cancel_operation_keyboard()
                    )
                    
                except ValueError:
                    send_message(chat_id, "❌ Введите корректную сумму (например: 50 или 100)", cancel_operation_keyboard())
                return
            
            elif state == "waiting_withdraw_wallet_cryptobot":
                if text == "/cancel":
                    user_states.pop(user_id, None)
                    send_message(chat_id, "❌ Операция отменена", main_menu_keyboard(user_id))
                    return
                    
                wallet_address = text.strip()
                amount = current_state["withdraw_amount"]
                
                if len(wallet_address) < 20 or not wallet_address.startswith("T"):
                    send_message(chat_id, 
                        "❌ Неверный формат кошелька USDT\n\n"
                        "Пожалуйста, введите корректный адрес TRC20 (начинается с T)\n"
                        "Или введите /cancel для отмены",
                        cancel_operation_keyboard()
                    )
                    return
                
                # Создаем вывод через CryptoBot
                success, result = create_cryptobot_withdraw(user_id, amount, wallet_address)
                
                if success:
                    # Списываем средства
                    player.data["usdt"] -= amount
                    player.data["total_withdrawals"] += amount
                    
                    send_message(chat_id,
                        f"✅ <b>Заявка на вывод создана!</b>\n\n"
                        f"💰 Сумма: {amount} USDT\n"
                        f"🏦 Кошелек: <code>{wallet_address}</code>\n"
                        f"📋 ID транзакции: {result.get('transfer_id', 'N/A')}\n\n"
                        f"💸 Средства будут отправлены в течение 24 часов.\n"
                        f"Спасибо за игру! 🎰",
                        main_menu_keyboard(user_id)
                    )
                else:
                    send_message(chat_id,
                        f"❌ <b>Ошибка вывода</b>\n\n"
                        f"💰 Сумма: {amount} USDT\n"
                        f"🏦 Кошелек: <code>{wallet_address}</code>\n"
                        f"📋 Ошибка: {result}\n\n"
                        f"Попробуйте позже или обратитесь в поддержку.",
                        main_menu_keyboard(user_id)
                    )
                
                user_states.pop(user_id, None)
                auto_saver.mark_changed()
                return
        
        if text.startswith("/start"):
            if len(text.split()) > 1:
                ref_code = text.split()[1]
                if ref_code in referral_codes and str(user_id) != str(referral_codes[ref_code]):
                    player.data["referrer_id"] = referral_codes[ref_code]
                    referrer_data = get_user_balance(referral_codes[ref_code])
                    referrer_data["referrals"].append(user_id)
            
            send_message(chat_id,
                f"🎰 Добро пожаловать в <b>Cosinxx Casino</b>!\n\n"
                f"💰 Ваш баланс:\n"
                f"  💵 <b>{player.data['usdt']:.2f} USDT</b>\n"
                f"  🪙 <b>{player.data['coins']} монет</b>\n"
                f"  👥 <b>{player.data['referral_balance']:.2f} USDT</b> (реферальные)\n\n"
                f"🎮 Реальные анимации с реальными результатами!\n"
                f"🎁 Ежедневные и недельные бонусы!\n"
                f"🏆 Система достижений и наград!\n\n"
                f"💡 <i>Используйте /help для справки</i>",
                main_menu_keyboard(user_id)
            )
            return
        
        elif text == "/profile":
            show_profile(user_id, chat_id)
            return
            
        elif text == "/cancel":
            if user_id in user_states:
                user_states.pop(user_id, None)
                send_message(chat_id, "✅ Текущая операция отменена", main_menu_keyboard(user_id))
            else:
                send_message(chat_id, "❌ Нет активных операций для отмены", main_menu_keyboard(user_id))
            return
        
        elif text == "/help":
            send_message(chat_id,
                f"🆘 <b>Помощь по боту</b>\n\n"
                f"🎮 <b>Игры:</b>\n"
                f"- Реальные анимации с реальными результатами\n"
                f"- 7 различных игр на выбор\n\n"
                f"💰 <b>Финансы:</b>\n"
                f"- Пополнение через @CryptoBot\n"
                f"- Вывод на USDT кошельки\n"
                f"- Минимальный вывод: {GAME_SETTINGS['min_withdraw']} USDT\n\n"
                f"🎁 <b>Бонусы:</b>\n"
                f"- Ежедневные бонусы: {GAME_SETTINGS['daily_bonus_min']}-{GAME_SETTINGS['daily_bonus_max']} монет\n"
                f"- Недельные бонусы: {GAME_SETTINGS['weekly_bonus_min']}-{GAME_SETTINGS['weekly_bonus_max']} монет\n\n"
                f"🏆 <b>Достижения:</b>\n"
                f"- 9 уникальных достижений с наградами\n"
                f"- Отслеживание вашего прогресса\n\n"
                f"👥 <b>Рефералы:</b>\n"
                f"- Получайте {GAME_SETTINGS['referral_bonus']*100}% от пополнений рефералов\n\n"
                f"📊 <b>Статистика:</b>\n"
                f"- Подробная аналитика и графики\n"
                f"- Персональная и общая статистика\n\n"
                f"⚡ <b>Команды:</b>\n"
                f"/start - Главное меню\n"
                f"/profile - Ваш профиль\n"
                f"/cancel - Отмена операции\n"
                f"/help - Эта справка\n\n"
                f"📞 <b>Поддержка:</b> {ADMIN_USERNAME}",
                main_menu_keyboard(user_id)
            )
            return
        
        else:
            send_message(chat_id,
                f"🎰 <b>Cosinxx Casino</b>\n"
                f"💵 {player.data['usdt']:.2f} USDT | 🪙 {player.data['coins']} монет\n"
                f"🎮 Реальные анимации!\n"
                f"🎁 Бонусы и достижения!\n\n"
                f"💡 Используйте /help для справки",
                main_menu_keyboard(user_id)
            )
    
    except Exception as e:
        logging.error(f"Ошибка в handle_message: {e}")
        send_message(chat_id, "❌ Произошла ошибка. Попробуйте еще раз.", main_menu_keyboard(user_id))

def show_profile(user_id, chat_id):
    """Показывает профиль пользователя"""
    player = Player(user_id)
    stats = get_personal_stats(user_id)
    
    profile_text = (
        f"👤 <b>Ваш профиль</b>\n\n"
        f"💼 Балансы:\n"
        f"💵 USDT: <b>{player.data['usdt']:.2f}</b>\n"
        f"🪙 Монеты: <b>{player.data['coins']}</b>\n"
        f"👥 Реферальные: <b>{player.data['referral_balance']:.2f} USDT</b>\n\n"
        f"🎮 Статистика:\n"
        f"🎯 Игр сыграно: <b>{stats['games_played']}</b>\n"
        f"🏆 Побед: <b>{stats['games_won']}</b>\n"
        f"📈 Винрейт: <b>{stats['win_rate']:.1f}%</b>\n"
        f"💰 Общий выигрыш: <b>{stats['total_winnings']}</b>\n"
        f"💵 Прибыль: <b>{stats['total_profit']}</b>\n"
        f"🔥 Текущая серия: <b>{stats['current_streak']}</b>\n"
        f"🏅 Макс. серия: <b>{stats['max_streak']}</b>\n"
        f"🎿 Побед в санках: <b>{stats['sledge_wins']}</b>\n\n"
        f"📅 С нами уже: <b>{stats['registration_days']} дней</b>"
    )
    
    send_message(chat_id, profile_text, profile_keyboard())

# ========== ОБРАБОТКА CALLBACK ==========

def handle_callback(callback_query):
    try:
        message = callback_query["message"]
        chat_id = message["chat"]["id"]
        message_id = message["message_id"]
        user_id = callback_query["from"]["id"]
        data = callback_query["data"]
        
        if not anti_cheat.check_rate_limit(user_id, "callback"):
            try:
                requests.post(URL + "answerCallbackQuery", 
                             json={"callback_query_id": callback_query["id"], 
                                   "text": "Слишком много запросов! Подождите."}, 
                             timeout=3)
            except:
                pass
            return
        
        player = Player(user_id)
        
        try:
            requests.post(URL + "answerCallbackQuery", 
                         json={"callback_query_id": callback_query["id"]}, 
                         timeout=3)
        except:
            pass
        
        # ОСНОВНЫЕ КНОПКИ - ОБНОВЛЕНИЕ СООБЩЕНИЙ
        if data == "main_menu":
            edit_message(chat_id, message_id,
                f"🎰 <b>Cosinxx Casino</b>\n"
                f"💵 {player.data['usdt']:.2f} USDT | 🪙 {player.data['coins']} монет\n"
                f"🎮 Реальные анимации!",
                main_menu_keyboard(user_id)
            )
        
        elif data == "profile":
            show_profile(user_id, chat_id)
        
        elif data == "games":
            edit_message(chat_id, message_id,
                "🎮 <b>Выберите игру</b>\n\n"
                f"💰 Текущая валюта: <b>{'💵 USDT' if player.data['game_currency'] == 'usdt' else '🪙 Виртуальные монеты'}</b>\n\n"
                f"🎯 <b>Реальные анимации с реальными результатами!</b>",
                games_menu_keyboard()
            )
        
        elif data.startswith("game_"):
            game_type = data.replace("game_", "")
            
            if game_type == "dice_new":
                # Новая игра в кости с интерфейсом как на картинке
                currency = player.data["game_currency"]
                currency_text = "виртуальных монет" if currency == "coins" else "USDT"
                
                edit_message(chat_id, message_id,
                    f"🎲 <b>Новая игра в кости</b>\n\n"
                    f"💰 Валюта: {currency_text}\n"
                    f"💎 Баланс: {player.data[currency]} {currency_text}\n\n"
                    f"🎯 <b>Выберите тип ставки:</b>\n"
                    f"• Чёт/Нечёт (x2)\n"
                    f"• Меньше/Больше (x2)\n"
                    f"• Конкретные числа (x6)\n"
                    f"• Произведение > 18 (x4.2)\n"
                    f"• Лесенка (x2)",
                    dice_game_keyboard()
                )
                return
            
            # НОВАЯ ИГРА - САНКИ
            elif game_type == "sledge":
                currency = player.data["game_currency"]
                currency_text = "виртуальных монет" if currency == "coins" else "USDT"
                
                edit_message(chat_id, message_id,
                    f"🎿 <b>Санки (RampageBET)</b>\n\n"
                    f"💰 Валюта: {currency_text}\n"
                    f"💎 Баланс: {player.data[currency]} {currency_text}\n\n"
                    f"🎯 <b>Правила игры:</b>\n"
                    f"• Выбирается целевое число от {GAME_SETTINGS['sledge_target_min']} до {GAME_SETTINGS['sledge_target_max']}\n"
                    f"• Запускается 15 спиннеров\n"
                    f"• Если выпадает целевое число - вы выигрываете x{GAME_SETTINGS['sledge_multiplier']}!\n"
                    f"• Время игры: 36 секунд\n\n"
                    f"🎰 <i>Удачи в игре!</i>",
                    sledge_bet_amount_keyboard()
                )
                return
            
            game_names = {
                "slots": "🎰 Слот-машина", "dice": "🎲 Кости", 
                "darts": "🎯 Дартс", "basketball": "🏀 Баскетбол",
                "football": "⚽ Футбол", "bowling": "🎳 Боулинг"
            }
            
            currency = player.data["game_currency"]
            currency_text = "виртуальных монет" if currency == "coins" else "USDT"
            
            edit_message(chat_id, message_id,
                f"🎮 <b>{game_names.get(game_type, 'Игра')}</b>\n\n"
                f"💰 Валюта: {currency_text}\n"
                f"💎 Баланс: {player.data[currency]} {currency_text}\n\n"
                f"🎯 <b>Реальная анимация определит результат!</b>",
                bet_amount_keyboard(game_type)
            )
        
        # НОВЫЕ CALLBACK ДЛЯ ИГРЫ САНКИ
        elif data.startswith("sledge_amount_"):
            amount = data.replace("sledge_amount_", "")
            
            if amount == "custom":
                user_states[user_id] = {"state": "waiting_sledge_amount"}
                currency = player.data["game_currency"]
                currency_text = "виртуальных монет" if currency == "coins" else "USDT"
                
                min_bet = GAME_SETTINGS["min_bet_coins"] if currency == "coins" else GAME_SETTINGS["min_bet_usdt"]
                max_bet = GAME_SETTINGS["max_bet_coins"] if currency == "coins" else GAME_SETTINGS["max_bet_usdt"]
                
                edit_message(chat_id, message_id,
                    f"💵 <b>Введите сумму ставки для игры Санки</b>\n\n"
                    f"💰 Минимум: {min_bet} {currency_text}\n"
                    f"💰 Максимум: {max_bet} {currency_text}\n"
                    f"💎 Ваш баланс: {player.data[currency]} {currency_text}\n\n"
                    f"Пример: <code>50</code> или <code>100</code>\n"
                    f"Или введите /cancel для отмены"
                )
            else:
                try:
                    bet_amount = int(amount)
                    currency = player.data["game_currency"]
                    play_sledge_game(user_id, chat_id, bet_amount, currency)
                except ValueError:
                    send_message(chat_id, "❌ Ошибка выбора ставки")
        
        elif data.startswith("sledge_refresh_"):
            game_id = data.replace("sledge_refresh_", "")
            if game_id in sledge_games:
                game = sledge_games[game_id]
                player = Player(user_id)
                currency_text = "виртуальных монет" if game["currency"] == "coins" else "USDT"
                
                current_spin = game.get("current_spin", 0)
                current_time = 36 - (current_spin * 2.4)
                if current_time < 0:
                    current_time = 0
                
                edit_message(chat_id, message_id,
                    f"🎿 <b>RampageBET</b>\n\n"
                    f"👤 {player.data.get('username', 'Игрок')} ставит {game['bet_amount']} {currency_text}\n\n"
                    f"🎯 <b>Санки</b>\n"
                    f"Должно выпасть число {game['target_number']}\n\n"
                    f"🎰 <i>Желаем удачи!</i>\n"
                    f"🔄 {current_spin}/15 Spins, 0:{current_time:02.0f}\n\n"
                    f"🎲 Игра в процессе...",
                    sledge_game_keyboard(game_id)
                )
        
        elif data.startswith("sledge_cancel_"):
            game_id = data.replace("sledge_cancel_", "")
            if game_id in sledge_games and sledge_games[game_id]["user_id"] == user_id:
                game = sledge_games[game_id]
                # Возвращаем ставку
                player = Player(user_id)
                player.data[game["currency"]] += game["bet_amount"]
                player.data["games_played"] -= 1
                player.data["total_bet"] -= game["bet_amount"]
                
                sledge_games[game_id]["status"] = "cancelled"
                
                send_message(chat_id,
                    f"❌ <b>Игра Санки отменена</b>\n\n"
                    f"💰 Возвращено: {game['bet_amount']} {'виртуальных монет' if game['currency'] == 'coins' else 'USDT'}\n"
                    f"💎 Баланс: {player.data[game['currency']]} {'виртуальных монет' if game['currency'] == 'coins' else 'USDT'}",
                    games_menu_keyboard()
                )
                auto_saver.mark_changed()
        
        elif data.startswith("bet_"):
            parts = data.split("_")
            if len(parts) >= 3:
                game_type = parts[1]
                amount = parts[2]
                
                if amount == "custom":
                    user_states[user_id] = {"state": f"waiting_bet_amount_{game_type}"}
                    currency = player.data["game_currency"]
                    currency_text = "виртуальных монет" if currency == "coins" else "USDT"
                    
                    min_bet = GAME_SETTINGS["min_bet_coins"] if currency == "coins" else GAME_SETTINGS["min_bet_usdt"]
                    max_bet = GAME_SETTINGS["max_bet_coins"] if currency == "coins" else GAME_SETTINGS["max_bet_usdt"]
                    
                    edit_message(chat_id, message_id,
                        f"💵 <b>Введите сумму ставки</b>\n\n"
                        f"💰 Минимум: {min_bet} {currency_text}\n"
                        f"💰 Максимум: {max_bet} {currency_text}\n"
                        f"💎 Ваш баланс: {player.data[currency]} {currency_text}\n\n"
                        f"Пример: <code>50</code> или <code>100</code>\n"
                        f"Или введите /cancel для отмены"
                    )
                else:
                    try:
                        bet_amount = int(amount)
                        currency = player.data["game_currency"]
                        start_game_with_bet(user_id, chat_id, game_type, bet_amount, currency)
                    except ValueError:
                        send_message(chat_id, "❌ Ошибка выбора ставки")
        
        # НОВАЯ ИГРА В КОСТИ - ОБРАБОТКА СТАВОК
        elif data.startswith("dice_bet_"):
            bet_type = data.replace("dice_bet_", "")
            currency = player.data["game_currency"]
            currency_text = "виртуальных монет" if currency == "coins" else "USDT"
            
            edit_message(chat_id, message_id,
                f"🎲 <b>Ставка: {get_bet_type_name(bet_type)}</b>\n\n"
                f"💰 Валюта: {currency_text}\n"
                f"💎 Баланс: {player.data[currency]} {currency_text}\n\n"
                f"Выберите сумму ставки:",
                dice_bet_amount_keyboard(bet_type)
            )
        
        elif data.startswith("dice_amount_"):
            parts = data.split("_")
            if len(parts) >= 3:
                bet_type = parts[2]
                amount = parts[3]
                
                if amount == "custom":
                    user_states[user_id] = {"state": f"waiting_dice_amount_{bet_type}"}
                    currency = player.data["game_currency"]
                    currency_text = "виртуальных монет" if currency == "coins" else "USDT"
                    
                    min_bet = GAME_SETTINGS["min_bet_coins"] if currency == "coins" else GAME_SETTINGS["min_bet_usdt"]
                    max_bet = GAME_SETTINGS["max_bet_coins"] if currency == "coins" else GAME_SETTINGS["max_bet_usdt"]
                    
                    edit_message(chat_id, message_id,
                        f"💵 <b>Введите сумму ставки</b>\n\n"
                        f"🎲 Ставка: {get_bet_type_name(bet_type)}\n"
                        f"💰 Минимум: {min_bet} {currency_text}\n"
                        f"💰 Максимум: {max_bet} {currency_text}\n"
                        f"💎 Ваш баланс: {player.data[currency]} {currency_text}\n\n"
                        f"Пример: <code>50</code> или <code>100</code>\n"
                        f"Или введите /cancel для отмены"
                    )
                else:
                    try:
                        bet_amount = int(amount)
                        currency = player.data["game_currency"]
                        play_dice_game(user_id, chat_id, bet_type, bet_amount, currency)
                    except ValueError:
                        send_message(chat_id, "❌ Ошибка выбора ставки")
        
        elif data == "balance":
            edit_message(chat_id, message_id,
                f"📊 <b>Ваш баланс:</b>\n\n"
                f"💵 USDT: <b>{player.data['usdt']:.2f}</b>\n"
                f"🪙 Виртуальные монеты: <b>{player.data['coins']}</b>\n"
                f"👥 Реферальные: <b>{player.data['referral_balance']:.2f} USDT</b>\n\n"
                f"🎮 Статистика:\n"
                f"🎯 Игр сыграно: {player.data.get('games_played', 0)}\n"
                f"🏆 Побед: {player.data.get('games_won', 0)}\n"
                f"💰 Выигрыш: {player.data.get('total_winnings', 0)} монет",
                back_to_main_keyboard()
            )
        
        elif data == "deposit":
            edit_message(chat_id, message_id,
                "💰 <b>Пополнение баланса</b>\n\n"
                "Выберите способ пополнения:",
                deposit_keyboard()
            )
        
        elif data == "deposit_cryptobot":
            user_states[user_id] = {"state": "waiting_deposit_amount_cryptobot"}
            edit_message(chat_id, message_id,
                "💵 <b>Пополнение USDT через @CryptoBot</b>\n\n"
                f"Введите сумму для пополнения (минимум {GAME_SETTINGS['min_deposit']} USDT):\n\n"
                f"💸 Комиссия: {DEPOSIT_COMMISSION*100}%\n"
                f"Пример: <code>50</code> или <code>100.5</code>\n\n"
                "Или введите /cancel для отмены операции",
                cancel_operation_keyboard()
            )
        
        elif data == "withdraw":
            edit_message(chat_id, message_id,
                "💸 <b>Вывод средств</b>\n\n"
                f"💵 Доступно для вывода: {player.data['usdt']:.2f} USDT\n"
                f"💰 Минимальный вывод: {GAME_SETTINGS['min_withdraw']} USDT\n\n"
                "Выберите способ вывода:",
                withdraw_keyboard()
            )
        
        elif data == "withdraw_cryptobot":
            user_states[user_id] = {"state": "waiting_withdraw_amount_cryptobot"}
            edit_message(chat_id, message_id,
                "💸 <b>Вывод USDT через @CryptoBot</b>\n\n"
                f"Введите сумму для вывода (минимум {GAME_SETTINGS['min_withdraw']} USDT):\n\n"
                "Пример: <code>50</code> или <code>100.5</code>\n\n"
                "Или введите /cancel для отмены операции",
                cancel_operation_keyboard()
            )
        
        elif data == "referral":
            if not player.data.get("referral_code"):
                player.data["referral_code"] = generate_referral_code(user_id)
            
            edit_message(chat_id, message_id,
                "👥 <b>Реферальная система</b>\n\n"
                f"🔗 Ваша реферальная ссылка:\n"
                f"<code>https://t.me/{BOT_USERNAME}?start={player.data['referral_code']}</code>\n\n"
                f"💰 Бонус за приглашение: {GAME_SETTINGS['referral_bonus']*100}% от пополнений\n"
                f"👥 Приглашено пользователей: {len(player.data.get('referrals', []))}\n"
                f"💵 Заработано: {player.data.get('referral_earnings', 0):.2f} USDT\n"
                f"💎 Доступно для вывода: {player.data.get('referral_balance', 0):.2f} USDT",
                referral_keyboard()
            )
        
        elif data == "my_referral_link":
            if not player.data.get("referral_code"):
                player.data["referral_code"] = generate_referral_code(user_id)
            
            edit_message(chat_id, message_id,
                f"🔗 <b>Ваша реферальная ссылка:</b>\n\n"
                f"<code>https://t.me/{BOT_USERNAME}?start={player.data['referral_code']}</code>\n\n"
                f"💰 Приглашайте друзей и получайте {GAME_SETTINGS['referral_bonus']*100}% от их пополнений!",
                referral_keyboard()
            )
        
        elif data == "withdraw_referral":
            ref_balance = player.data.get("referral_balance", 0)
            if ref_balance < 1:
                edit_message(chat_id, message_id, "❌ Минимальная сумма для вывода реферальных: 1 USDT", referral_keyboard())
                return
            
            player.data["usdt"] += ref_balance
            player.data["referral_balance"] = 0
            
            edit_message(chat_id, message_id,
                f"✅ <b>Реферальные средства переведены</b>\n\n"
                f"💵 Сумма: {ref_balance:.2f} USDT\n"
                f"💰 Теперь доступны для вывода в основном балансе",
                referral_keyboard()
            )
            auto_saver.mark_changed()
        
        elif data == "referral_stats":
            referrals_count = len(player.data.get("referrals", []))
            total_earnings = player.data.get("referral_earnings", 0)
            available_balance = player.data.get("referral_balance", 0)
            
            edit_message(chat_id, message_id,
                f"📊 <b>Реферальная статистика</b>\n\n"
                f"👥 Приглашено пользователей: {referrals_count}\n"
                f"💰 Всего заработано: {total_earnings:.2f} USDT\n"
                f"💵 Доступно для вывода: {available_balance:.2f} USDT\n"
                f"🎯 Бонус за приглашение: {GAME_SETTINGS['referral_bonus']*100}%",
                referral_keyboard()
            )
        
        elif data == "change_currency":
            edit_message(chat_id, message_id,
                f"💱 <b>Смена игровой валюты</b>\n\n"
                f"Текущая валюта: <b>{'💵 USDT' if player.data['game_currency'] == 'usdt' else '🪙 Виртуальные монеты'}</b>\n\n"
                f"Выберите новую валюту для игр:",
                currency_keyboard()
            )
        
        elif data == "currency_usdt":
            player.data["game_currency"] = "usdt"
            edit_message(chat_id, message_id,
                "✅ <b>Валюта изменена на USDT</b>\n\n"
                "Теперь все игры будут использовать реальные средства USDT",
                main_menu_keyboard(user_id)
            )
            auto_saver.mark_changed()
        
        elif data == "currency_coins":
            player.data["game_currency"] = "coins"
            edit_message(chat_id, message_id,
                "✅ <b>Валюта изменена на виртуальные монеты</b>\n\n"
                "Теперь все игры будут использовать виртуальные монеты",
                main_menu_keyboard(user_id)
            )
            auto_saver.mark_changed()
        
        elif data == "bonuses":
            edit_message(chat_id, message_id,
                "🎁 <b>Бонусная система</b>\n\n"
                f"💰 Ежедневный бонус: {GAME_SETTINGS['daily_bonus_min']}-{GAME_SETTINGS['daily_bonus_max']} монет\n"
                f"📅 Недельный бонус: {GAME_SETTINGS['weekly_bonus_min']}-{GAME_SETTINGS['weekly_bonus_max']} монет\n\n"
                f"Забирайте бонусы регулярно для увеличения баланса!",
                bonuses_keyboard()
            )
        
        elif data == "bonus_daily":
            user_str = str(user_id)
            now = time.time()
            
            if user_str not in bonus_claims:
                bonus_claims[user_str] = {}
            
            last_daily = bonus_claims[user_str].get("daily", 0)
            
            if now - last_daily < 86400:
                next_claim = last_daily + 86400
                wait_time = next_claim - now
                hours = int(wait_time // 3600)
                minutes = int((wait_time % 3600) // 60)
                edit_message(chat_id, message_id, f"❌ Следующий бонус через {hours}ч {minutes}м", bonuses_keyboard())
                return
            
            bonus_amount = random.randint(300, 500)
            player.data["coins"] += bonus_amount
            bonus_claims[user_str]["daily"] = now
            
            edit_message(chat_id, message_id,
                f"🎁 <b>ЕЖЕДНЕВНЫЙ БОНУС!</b>\n\n"
                f"💰 +{bonus_amount} монет\n"
                f"💎 Баланс: {player.data['coins']} монет\n\n"
                f"Возвращайтесь завтра за новым бонусом!",
                bonuses_keyboard()
            )
            auto_saver.mark_changed()
        
        elif data == "bonus_weekly":
            user_str = str(user_id)
            now = time.time()
            
            if user_str not in bonus_claims:
                bonus_claims[user_str] = {}
            
            last_weekly = bonus_claims[user_str].get("weekly", 0)
            
            if now - last_weekly < 604800:
                next_claim = last_weekly + 604800
                wait_time = next_claim - now
                days = int(wait_time // 86400)
                hours = int((wait_time % 86400) // 3600)
                edit_message(chat_id, message_id, f"❌ Следующий бонус через {days}д {hours}ч", bonuses_keyboard())
                return
            
            bonus_amount = random.randint(1000, 3000)
            player.data["coins"] += bonus_amount
            bonus_claims[user_str]["weekly"] = now
            
            edit_message(chat_id, message_id,
                f"🎁 <b>НЕДЕЛЬНЫЙ БОНУС!</b>\n\n"
                f"💰 +{bonus_amount} монет\n"
                f"💎 Баланс: {player.data['coins']} монет\n\n"
                f"Отличная неделя! Возвращайтесь через 7 дней.",
                bonuses_keyboard()
            )
            auto_saver.mark_changed()
        
        elif data == "achievements":
            user_achievements_count = len(achievements.get(str(user_id), {}))
            edit_message(chat_id, message_id,
                f"🏆 <b>Система достижений</b>\n\n"
                f"🎯 Получено достижений: {user_achievements_count}/{len(ACHIEVEMENTS_CONFIG)}\n"
                f"💰 Заберите награды за выполненные достижения!\n\n"
                f"Выберите достижение для просмотра:",
                achievements_keyboard(user_id)
            )
        
        elif data.startswith("achievement_"):
            achievement_id = data.replace("achievement_", "")
            achievement = ACHIEVEMENTS_CONFIG.get(achievement_id)
            
            if not achievement:
                edit_message(chat_id, message_id, "❌ Достижение не найдено", achievements_keyboard(user_id))
                return
            
            user_str = str(user_id)
            has_achievement = user_str in achievements and achievement_id in achievements[user_str]
            reward_claimed = has_achievement and achievements[user_str][achievement_id]["reward_claimed"]
            
            status = "✅ Получено" if has_achievement else "❌ Не получено"
            reward_status = "💰 Награда получена" if reward_claimed else "💰 Награда доступна" if has_achievement else ""
            
            message = (
                f"🏆 <b>{achievement['name']}</b>\n\n"
                f"📝 {achievement['description']}\n"
                f"🎁 Награда: {achievement['reward']} USDT\n"
                f"📊 Статус: {status}\n"
                f"{reward_status}"
            )
            
            keyboard = {"inline_keyboard": []}
            
            if has_achievement and not reward_claimed:
                keyboard["inline_keyboard"].append([{"text": "💰 Забрать награду", "callback_data": f"claim_{achievement_id}"}])
            
            keyboard["inline_keyboard"].append([{"text": "⬅️ Назад", "callback_data": "achievements"}])
            
            edit_message(chat_id, message_id, message, keyboard)
        
        elif data.startswith("claim_"):
            achievement_id = data.replace("claim_", "")
            user_str = str(user_id)
            
            if (user_str in achievements and 
                achievement_id in achievements[user_str] and 
                not achievements[user_str][achievement_id]["reward_claimed"]):
                
                achievement = ACHIEVEMENTS_CONFIG[achievement_id]
                reward = achievement["reward"]
                
                player.data["usdt"] += reward
                achievements[user_str][achievement_id]["reward_claimed"] = True
                
                edit_message(chat_id, message_id,
                    f"🎁 <b>Награда получена!</b>\n\n"
                    f"🏆 {achievement['name']}\n"
                    f"💰 +{reward} USDT\n"
                    f"💎 Новый баланс: {player.data['usdt']:.2f} USDT",
                    achievements_keyboard(user_id)
                )
                
                auto_saver.mark_changed()
            else:
                edit_message(chat_id, message_id, "❌ Не удалось получить награду", achievements_keyboard(user_id))
        
        elif data == "statistics":
            edit_message(chat_id, message_id,
                "📊 <b>Статистика и аналитика</b>\n\n"
                "Здесь вы можете посмотреть:\n"
                "• Графики активности казино\n"
                "• Вашу персональную статистику\n"
                "• Общую статистику бота\n\n"
                "Выберите раздел:",
                statistics_keyboard()
            )
        
        elif data == "stats_analytics":
            dates = sorted(game_analytics["daily_stats"].keys())[-7:]
            
            if not dates:
                edit_message(chat_id, message_id, "📊 <b>Аналитика казино</b>\n\nПока недостаточно данных для аналитики", statistics_keyboard())
                return
                
            analytics_text = "📊 <b>Аналитика казино</b>\n\n"
            analytics_text += "📈 <b>Статистика за последние 7 дней:</b>\n"
            
            for date in dates:
                stats = game_analytics["daily_stats"][date]
                analytics_text += f"📅 {date}:\n"
                analytics_text += f"   🎮 Игр: {stats['total_games']}\n"
                analytics_text += f"   💰 Ставок: {stats['total_bets']:.0f}\n"
                analytics_text += f"   🎯 Выигрышей: {stats['total_wins']:.0f}\n"
                analytics_text += f"   👥 Игроков: {len(stats['unique_players'])}\n\n"
            
            edit_message(chat_id, message_id, analytics_text, statistics_keyboard())
        
        elif data == "stats_personal":
            stats = get_personal_stats(user_id)
            game_names = {
                "slots": "🎰 Слоты", "dice": "🎲 Кости", 
                "darts": "🎯 Дартс", "basketball": "🏀 Баскетбол",
                "football": "⚽ Футбол", "bowling": "🎳 Боулинг",
                "sledge": "🎿 Санки"
            }
            favorite_game = game_names.get(stats["favorite_game"], "Не определена")
            
            edit_message(chat_id, message_id,
                f"👤 <b>Ваша статистика</b>\n\n"
                f"🎮 Игр сыграно: {stats['games_played']}\n"
                f"🏆 Побед: {stats['games_won']}\n"
                f"📈 Винрейт: {stats['win_rate']:.1f}%\n"
                f"💰 Общие ставки: {stats['total_bet']:.0f}\n"
                f"🎯 Общий выигрыш: {stats['total_winnings']:.0f}\n"
                f"💵 Прибыль: {stats['total_profit']:.0f}\n"
                f"🔥 Текущая серия: {stats['current_streak']}\n"
                f"🏅 Макс. серия: {stats['max_streak']}\n"
                f"🎿 Побед в санках: {stats['sledge_wins']}\n"
                f"❤️ Любимая игра: {favorite_game}\n"
                f"📅 Дней с нами: {stats['registration_days']}",
                statistics_keyboard()
            )
        
        elif data == "stats_global":
            total_players = len(players)
            total_games = sum(player.get("games_played", 0) for player in players.values())
            total_deposits = sum(player.get("total_deposits", 0) for player in players.values())
            total_withdrawals = sum(player.get("total_withdrawals", 0) for player in players.values())
            
            game_popularity = game_analytics.get("game_popularity", {})
            popular_games = sorted(game_popularity.items(), key=lambda x: x[1], reverse=True)[:3]
            popular_text = "\n".join([f"• {game}: {count}" for game, count in popular_games])
            
            edit_message(chat_id, message_id,
                f"🌍 <b>Общая статистика</b>\n\n"
                f"👥 Всего игроков: {total_players}\n"
                f"🎮 Сыграно игр: {total_games}\n"
                f"💰 Пополнений: {total_deposits:.2f} USDT\n"
                f"💸 Выводов: {total_withdrawals:.2f} USDT\n"
                f"📈 Прибыль казино: {total_deposits - total_withdrawals:.2f} USDT\n\n"
                f"🏆 <b>Популярные игры:</b>\n{popular_text}",
                statistics_keyboard()
            )
        
        elif data == "support":
            edit_message(chat_id, message_id,
                "📞 <b>Служба поддержки</b>\n\n"
                "Здесь вы можете:\n"
                "• Создать тикет с вопросом\n"
                "• Посмотреть свои тикеты\n"
                "• Получить помощь от администратора\n\n"
                "Администратор ответит в ближайшее время.",
                support_keyboard()
            )
        
        elif data == "support_create":
            user_states[user_id] = {"state": "waiting_support_message"}
            edit_message(chat_id, message_id,
                "💬 <b>Создание тикета поддержки</b>\n\n"
                "Опишите вашу проблему или вопрос:\n\n"
                "Пример: \"Не приходят средства после пополнения\"\n"
                "Или введите /cancel для отмены",
                cancel_operation_keyboard()
            )
        
        elif data == "support_my_tickets":
            user_tickets = {k: v for k, v in support_tickets.items() if v["user_id"] == user_id}
            
            if not user_tickets:
                edit_message(chat_id, message_id, "📋 У вас пока нет созданных тикетов", support_keyboard())
                return
            
            tickets_text = "📋 <b>Ваши тикеты:</b>\n\n"
            for ticket_id, ticket in list(user_tickets.items())[:5]:
                status_emoji = "🟢" if ticket["status"] == "open" else "🟡" if ticket["status"] == "answered" else "🔴"
                status_text = "Открыт" if ticket["status"] == "open" else "Отвечен" if ticket["status"] == "answered" else "Закрыт"
                tickets_text += f"{status_emoji} {ticket_id}: {ticket['message'][:50]}... ({status_text})\n\n"
            
            edit_message(chat_id, message_id, tickets_text, support_keyboard())
        
        elif data == "top_players":
            top_players = get_top_players(10)
            top_text = "🏆 <b>Топ игроков по прибыли</b>\n\n"
            
            for i, (player_id, player_data) in enumerate(top_players, 1):
                username = player_data.get("username", "Без имени")
                profit = player_data.get("total_profit", 0)
                top_text += f"{i}. {username}: {profit:.0f} монет\n"
            
            if not top_players:
                top_text += "Пока нет данных о игроках"
            
            edit_message(chat_id, message_id, top_text, back_to_main_keyboard())
        
        # АДМИН ПАНЕЛЬ - ОБНОВЛЕНИЕ СООБЩЕНИЙ
        elif data == "admin_panel" and user_id == ADMIN_ID:
            edit_message(chat_id, message_id,
                "⚙️ <b>Админ-панель</b>\n\n"
                "Выберите действие:",
                admin_keyboard()
            )
        
        elif data == "admin_stats" and user_id == ADMIN_ID:
            total_players = len(players)
            total_games = sum(player.get("games_played", 0) for player in players.values())
            total_deposits = sum(player.get("total_deposits", 0) for player in players.values())
            total_withdrawals = sum(player.get("total_withdrawals", 0) for player in players.values())
            
            pending_deposits = len([d for d in deposit_requests.items() if d[1].get("status") == "pending"])
            pending_withdrawals = len([w for w in withdraw_requests.items() if w[1].get("status") == "pending"])
            open_tickets = len([t for t in support_tickets.items() if t[1].get("status") == "open"])
            
            stats_text = (
                f"📊 <b>Статистика бота</b>\n\n"
                f"👥 Всего игроков: {total_players}\n"
                f"🎮 Сыграно игр: {total_games}\n"
                f"💰 Общие пополнения: {total_deposits:.2f} USDT\n"
                f"💸 Общие выводы: {total_withdrawals:.2f} USDT\n"
                f"📈 Прибыль казино: {total_deposits - total_withdrawals:.2f} USDT\n\n"
                f"🔄 Ожидают пополнения: {pending_deposits}\n"
                f"💸 Ожидают вывода: {pending_withdrawals}\n"
                f"📞 Открытые тикеты: {open_tickets}\n"
                f"⚠️ Подозрительные: {len(anti_cheat.get_suspicious_users())}"
            )
            
            edit_message(chat_id, message_id, stats_text, admin_keyboard())
        
        elif data == "admin_users" and user_id == ADMIN_ID:
            edit_message(chat_id, message_id,
                "👤 <b>Управление пользователями</b>\n\n"
                "Список пользователей:",
                admin_users_list_keyboard()
            )
        
        elif data.startswith("admin_user_view_") and user_id == ADMIN_ID:
            target_user_id = int(data.replace("admin_user_view_", ""))
            user_data = get_user_balance(target_user_id)
            username = user_data.get("username", "Без имени")
            
            user_info = (
                f"👤 <b>Информация о пользователе</b>\n\n"
                f"🆔 ID: {target_user_id}\n"
                f"👤 Имя: {username}\n"
                f"💵 Баланс USDT: {user_data['usdt']:.2f}\n"
                f"🪙 Баланс монет: {user_data['coins']}\n"
                f"👥 Реферальные: {user_data['referral_balance']:.2f} USDT\n\n"
                f"🎮 Статистика:\n"
                f"• Игр сыграно: {user_data['games_played']}\n"
                f"• Побед: {user_data['games_won']}\n"
                f"• Общий выигрыш: {user_data['total_winnings']}\n"
                f"• Прибыль: {user_data['total_profit']}\n"
                f"• Пополнений: {user_data['total_deposits']:.2f} USDT\n"
                f"• Выводов: {user_data['total_withdrawals']:.2f} USDT\n"
                f"• Побед в санках: {user_data.get('sledge_wins', 0)}\n\n"
                f"📅 Зарегистрирован: {datetime.fromtimestamp(user_data['registration_date']).strftime('%Y-%m-%d %H:%M')}"
            )
            
            edit_message(chat_id, message_id, user_info, admin_user_details_keyboard(target_user_id))
        
        elif data.startswith("admin_user_add_") and user_id == ADMIN_ID:
            target_user_id = int(data.replace("admin_user_add_", ""))
            user_states[user_id] = {"state": f"admin_add_balance_{target_user_id}"}
            edit_message(chat_id, message_id,
                f"💰 <b>Пополнение баланса пользователя</b>\n\n"
                f"Введите сумму для пополнения (USDT):\n\n"
                f"Пример: <code>100</code> или <code>50.5</code>\n"
                f"Или введите /cancel для отмены"
            )
        
        elif data.startswith("admin_user_remove_") and user_id == ADMIN_ID:
            target_user_id = int(data.replace("admin_user_remove_", ""))
            user_states[user_id] = {"state": f"admin_remove_balance_{target_user_id}"}
            edit_message(chat_id, message_id,
                f"💸 <b>Снятие баланса пользователя</b>\n\n"
                f"Введите сумму для снятия (USDT):\n\n"
                f"Пример: <code>100</code> или <code>50.5</code>\n"
                f"Или введите /cancel для отмены"
            )
        
        # НОВЫЕ АДМИН ФУНКЦИИ - ВЫДАЧА ВАЛЮТЫ
        elif data == "admin_give_currency" and user_id == ADMIN_ID:
            edit_message(chat_id, message_id,
                "💰 <b>Выдача валюты</b>\n\n"
                "Выберите тип валюты для выдачи:",
                admin_give_currency_keyboard()
            )
        
        elif data == "admin_give_usdt" and user_id == ADMIN_ID:
            user_states[user_id] = {"state": "admin_give_usdt_all"}
            edit_message(chat_id, message_id,
                "💵 <b>Выдача USDT всем пользователям</b>\n\n"
                "Введите сумму для выдачи:\n\n"
                "Пример: <code>100</code> или <code>50.5</code>\n"
                "Или введите /cancel для отмены"
            )
        
        elif data == "admin_give_coins" and user_id == ADMIN_ID:
            user_states[user_id] = {"state": "admin_give_coins_all"}
            edit_message(chat_id, message_id,
                "🪙 <b>Выдача монет всем пользователям</b>\n\n"
                "Введите сумму для выдачи:\n\n"
                "Пример: <code>1000</code> или <code>5000</code>\n"
                "Или введите /cancel для отмены"
            )
        
        elif data == "admin_give_referral" and user_id == ADMIN_ID:
            user_states[user_id] = {"state": "admin_give_referral_all"}
            edit_message(chat_id, message_id,
                "👥 <b>Выдача реферальных всем пользователям</b>\n\n"
                "Введите сумму для выдачи (USDT):\n\n"
                "Пример: <code>10</code> или <code>5.5</code>\n"
                "Или введите /cancel для отмены"
            )
        
        elif data.startswith("admin_give_usdt_user_") and user_id == ADMIN_ID:
            target_user_id = int(data.replace("admin_give_usdt_user_", ""))
            user_states[user_id] = {"state": f"admin_give_usdt_user_{target_user_id}"}
            edit_message(chat_id, message_id,
                f"💵 <b>Выдача USDT пользователю</b>\n\n"
                f"Введите сумму для выдачи:\n\n"
                f"Пример: <code>100</code> или <code>50.5</code>\n"
                f"Или введите /cancel для отмены"
            )
        
        elif data.startswith("admin_give_coins_user_") and user_id == ADMIN_ID:
            target_user_id = int(data.replace("admin_give_coins_user_", ""))
            user_states[user_id] = {"state": f"admin_give_coins_user_{target_user_id}"}
            edit_message(chat_id, message_id,
                f"🪙 <b>Выдача монет пользователю</b>\n\n"
                f"Введите сумму для выдачи:\n\n"
                f"Пример: <code>1000</code> или <code>5000</code>\n"
                f"Или введите /cancel для отмены"
            )
        
        elif data == "admin_deposits_list" and user_id == ADMIN_ID:
            pending_count = len([d for d in deposit_requests.items() if d[1].get("status") == "pending"])
            edit_message(chat_id, message_id,
                f"💰 <b>Запросы на пополнение</b>\n\n"
                f"⏳ Ожидают обработки: {pending_count}\n\n"
                f"Список запросов:",
                admin_deposits_list_keyboard()
            )
        
        elif data.startswith("admin_deposit_view_") and user_id == ADMIN_ID:
            deposit_id = data.replace("admin_deposit_view_", "")
            if deposit_id in deposit_requests:
                deposit = deposit_requests[deposit_id]
                user_data = get_user_balance(deposit["user_id"])
                username = user_data.get("username", "Без имени")
                
                deposit_info = (
                    f"💰 <b>Запрос на пополнение</b>\n\n"
                    f"📋 ID: {deposit_id}\n"
                    f"👤 Пользователь: {username} (ID: {deposit['user_id']})\n"
                    f"💵 Сумма: {deposit['amount']} USDT\n"
                    f"🔗 Чек: {deposit['check_url']}\n"
                    f"⏰ Время: {datetime.fromtimestamp(deposit['timestamp']).strftime('%Y-%m-%d %H:%M')}\n"
                    f"📊 Статус: ⏳ Ожидает"
                )
                
                edit_message(chat_id, message_id, deposit_info, admin_deposit_details_keyboard(deposit_id))
            else:
                edit_message(chat_id, message_id, "❌ Запрос не найден", admin_deposits_list_keyboard())
        
        elif data.startswith("admin_deposit_approve_") and user_id == ADMIN_ID:
            deposit_id = data.replace("admin_deposit_approve_", "")
            success, message = approve_deposit(deposit_id)
            
            if success:
                deposit = deposit_requests[deposit_id]
                user_id_deposit = deposit["user_id"]
                
                # Уведомляем пользователя
                send_message(user_id_deposit,
                    f"✅ <b>Ваше пополнение подтверждено!</b>\n\n"
                    f"💰 Сумма: {deposit['amount']} USDT\n"
                    f"📋 ID заявки: {deposit_id}\n"
                    f"💎 Новый баланс: {get_user_balance(user_id_deposit)['usdt']:.2f} USDT\n\n"
                    f"Спасибо за использование нашего казино! 🎰"
                )
            
            edit_message(chat_id, message_id, f"✅ {message}", admin_deposits_list_keyboard())
        
        elif data.startswith("admin_deposit_reject_") and user_id == ADMIN_ID:
            deposit_id = data.replace("admin_deposit_reject_", "")
            success, message = reject_deposit(deposit_id)
            
            if success:
                deposit = deposit_requests[deposit_id]
                user_id_deposit = deposit["user_id"]
                
                # Уведомляем пользователя
                send_message(user_id_deposit,
                    f"❌ <b>Ваше пополнение отклонено</b>\n\n"
                    f"💰 Сумма: {deposit['amount']} USDT\n"
                    f"📋 ID заявки: {deposit_id}\n\n"
                    f"ℹ️ Если вы считаете это ошибкой, обратитесь в поддержку."
                )
            
            edit_message(chat_id, message_id, f"✅ {message}", admin_deposits_list_keyboard())
        
        elif data == "admin_withdrawals_list" and user_id == ADMIN_ID:
            pending_count = len([w for w in withdraw_requests.items() if w[1].get("status") == "pending"])
            edit_message(chat_id, message_id,
                f"💸 <b>Запросы на вывод</b>\n\n"
                f"⏳ Ожидают обработки: {pending_count}\n\n"
                f"Список запросов:",
                admin_withdrawals_list_keyboard()
            )
        
        elif data.startswith("admin_withdraw_view_") and user_id == ADMIN_ID:
            withdraw_id = data.replace("admin_withdraw_view_", "")
            if withdraw_id in withdraw_requests:
                withdraw = withdraw_requests[withdraw_id]
                user_data = get_user_balance(withdraw["user_id"])
                username = user_data.get("username", "Без имени")
                
                withdraw_info = (
                    f"💸 <b>Запрос на вывод</b>\n\n"
                    f"📋 ID: {withdraw_id}\n"
                    f"👤 Пользователь: {username} (ID: {withdraw['user_id']})\n"
                    f"💵 Сумма: {withdraw['amount']} USDT\n"
                    f"🏦 Кошелек: <code>{withdraw['wallet_address']}</code>\n"
                    f"⏰ Время: {datetime.fromtimestamp(withdraw['timestamp']).strftime('%Y-%m-%d %H:%M')}\n"
                    f"📊 Статус: ⏳ Ожидает"
                )
                
                edit_message(chat_id, message_id, withdraw_info, admin_withdraw_details_keyboard(withdraw_id))
            else:
                edit_message(chat_id, message_id, "❌ Запрос не найден", admin_withdrawals_list_keyboard())
        
        elif data.startswith("admin_withdraw_approve_") and user_id == ADMIN_ID:
            withdraw_id = data.replace("admin_withdraw_approve_", "")
            success, message = approve_withdraw(withdraw_id)
            
            if success:
                withdraw = withdraw_requests[withdraw_id]
                user_id_withdraw = withdraw["user_id"]
                
                # Уведомляем пользователя
                send_message(user_id_withdraw,
                    f"✅ <b>Ваш вывод подтвержден!</b>\n\n"
                    f"💰 Сумма: {withdraw['amount']} USDT\n"
                    f"🏦 Кошелек: <code>{withdraw['wallet_address']}</code>\n"
                    f"📋 ID заявки: {withdraw_id}\n\n"
                    f"💸 Средства будут отправлены в течение 24 часов.\n"
                    f"Спасибо за игру! 🎰"
                )
            
            edit_message(chat_id, message_id, f"✅ {message}", admin_withdrawals_list_keyboard())
        
        elif data.startswith("admin_withdraw_reject_") and user_id == ADMIN_ID:
            withdraw_id = data.replace("admin_withdraw_reject_", "")
            success, message = reject_withdraw(withdraw_id)
            
            if success:
                withdraw = withdraw_requests[withdraw_id]
                user_id_withdraw = withdraw["user_id"]
                
                # Уведомляем пользователя
                send_message(user_id_withdraw,
                    f"❌ <b>Ваш вывод отклонен</b>\n\n"
                    f"💰 Сумма: {withdraw['amount']} USDT\n"
                    f"🏦 Кошелек: <code>{withdraw['wallet_address']}</code>\n"
                    f"📋 ID заявки: {withdraw_id}\n\n"
                    f"ℹ️ Если вы считаете это ошибкой, обратитесь в поддержку."
                )
            
            edit_message(chat_id, message_id, f"✅ {message}", admin_withdrawals_list_keyboard())
        
        elif data == "admin_support_tickets" and user_id == ADMIN_ID:
            open_count = len([t for t in support_tickets.items() if t[1].get("status") == "open"])
            edit_message(chat_id, message_id,
                f"📞 <b>Тикеты поддержки</b>\n\n"
                f"🟢 Открытых тикетов: {open_count}\n\n"
                f"Список тикетов:",
                admin_support_tickets_keyboard()
            )
        
        elif data.startswith("admin_ticket_view_") and user_id == ADMIN_ID:
            ticket_id = data.replace("admin_ticket_view_", "")
            if ticket_id in support_tickets:
                ticket = support_tickets[ticket_id]
                
                ticket_info = (
                    f"📞 <b>Тикет поддержки</b>\n\n"
                    f"📋 ID: {ticket_id}\n"
                    f"👤 Пользователь: {ticket['username']} (ID: {ticket['user_id']})\n"
                    f"⏰ Создан: {datetime.fromtimestamp(ticket['created_at']).strftime('%Y-%m-%d %H:%M')}\n"
                    f"📊 Статус: {'🟢 Открыт' if ticket['status'] == 'open' else '🟡 Отвечен' if ticket['status'] == 'answered' else '🔴 Закрыт'}\n\n"
                    f"💬 <b>Сообщение:</b>\n"
                    f"{ticket['message']}\n\n"
                )
                
                if ticket.get("admin_response"):
                    ticket_info += f"👨‍💼 <b>Ответ администратора:</b>\n{ticket['admin_response']}\n\n"
                
                edit_message(chat_id, message_id, ticket_info, admin_ticket_details_keyboard(ticket_id))
            else:
                edit_message(chat_id, message_id, "❌ Тикет не найден", admin_support_tickets_keyboard())
        
        elif data.startswith("admin_ticket_reply_") and user_id == ADMIN_ID:
            ticket_id = data.replace("admin_ticket_reply_", "")
            user_states[user_id] = {"state": f"admin_reply_ticket_{ticket_id}"}
            edit_message(chat_id, message_id,
                f"💬 <b>Ответ на тикет {ticket_id}</b>\n\n"
                f"Введите ваш ответ:\n\n"
                f"Или введите /cancel для отмены"
            )
        
        elif data.startswith("admin_ticket_close_") and user_id == ADMIN_ID:
            ticket_id = data.replace("admin_ticket_close_", "")
            if ticket_id in support_tickets:
                support_tickets[ticket_id]["status"] = "closed"
                edit_message(chat_id, message_id, f"✅ Тикет {ticket_id} закрыт", admin_support_tickets_keyboard())
            else:
                edit_message(chat_id, message_id, "❌ Тикет не найден", admin_support_tickets_keyboard())
        
        elif data == "admin_analytics" and user_id == ADMIN_ID:
            # Простая аналитика для админа
            total_players = len(players)
            active_today = len([p for p in players.values() if time.time() - p.get("last_activity", 0) < 86400])
            total_games = sum(player.get("games_played", 0) for player in players.values())
            
            game_stats = "\n".join([f"• {game}: {count}" for game, count in game_analytics.get("game_popularity", {}).items()])
            
            analytics_text = (
                f"📈 <b>Аналитика казино</b>\n\n"
                f"👥 Игроки:\n"
                f"• Всего: {total_players}\n"
                f"• Активных за сегодня: {active_today}\n\n"
                f"🎮 Игры:\n"
                f"• Всего сыграно: {total_games}\n"
                f"• Популярность игр:\n{game_stats}\n\n"
                f"💰 Финансы:\n"
                f"• Общие пополнения: {sum(p.get('total_deposits', 0) for p in players.values()):.2f} USDT\n"
                f"• Общие выводы: {sum(p.get('total_withdrawals', 0) for p in players.values()):.2f} USDT\n"
                f"• Прибыль: {sum(p.get('total_deposits', 0) for p in players.values()) - sum(p.get('total_withdrawals', 0) for p in players.values()):.2f} USDT"
            )
            
            edit_message(chat_id, message_id, analytics_text, admin_keyboard())
        
        elif data == "admin_settings" and user_id == ADMIN_ID:
            settings_text = (
                f"⚙️ <b>Настройки казино</b>\n\n"
                f"💰 Минимальная ставка USDT: {GAME_SETTINGS['min_bet_usdt']}\n"
                f"💰 Максимальная ставка USDT: {GAME_SETTINGS['max_bet_usdt']}\n"
                f"🪙 Минимальная ставка монет: {GAME_SETTINGS['min_bet_coins']}\n"
                f"🪙 Максимальная ставка монет: {GAME_SETTINGS['max_bet_coins']}\n"
                f"💵 Минимальное пополнение: {GAME_SETTINGS['min_deposit']} USDT\n"
                f"💸 Минимальный вывод: {GAME_SETTINGS['min_withdraw']} USDT\n"
                f"👥 Реферальный бонус: {GAME_SETTINGS['referral_bonus']*100}%\n"
                f"🎁 Ежедневный бонус: {GAME_SETTINGS['daily_bonus_min']}-{GAME_SETTINGS['daily_bonus_max']} монет\n"
                f"📅 Недельный бонус: {GAME_SETTINGS['weekly_bonus_min']}-{GAME_SETTINGS['weekly_bonus_max']} монет\n"
                f"🎿 Санки - мин. число: {GAME_SETTINGS['sledge_target_min']}\n"
                f"🎿 Санки - макс. число: {GAME_SETTINGS['sledge_target_max']}\n"
                f"🎿 Санки - множитель: x{GAME_SETTINGS['sledge_multiplier']}"
            )
            
            edit_message(chat_id, message_id, settings_text, admin_keyboard())
        
        elif data == "admin_save" and user_id == ADMIN_ID:
            save_data()
            edit_message(chat_id, message_id, "✅ Данные успешно сохранены", admin_keyboard())
        
        elif data == "cancel_operation":
            if user_id in user_states:
                user_states.pop(user_id, None)
                edit_message(chat_id, message_id, "✅ Операция отменена", main_menu_keyboard(user_id))
            else:
                edit_message(chat_id, message_id, "❌ Нет активных операций для отмены", main_menu_keyboard(user_id))
        
    except Exception as e:
        logging.error(f"Ошибка в handle_callback: {e}")

# ========== ОБРАБОТКА UPDATE ==========

def handle_update(update):
    """Обработка входящих updates от Telegram"""
    try:
        if "message" in update:
            handle_message(update["message"])
        elif "callback_query" in update:
            handle_callback(update["callback_query"])
    except Exception as e:
        logging.error(f"Ошибка обработки update: {e}")

# ========== ЗАПУСК БОТА ==========

def main():
    load_data()
    
    print("🎰 Cosinxx Casino Bot запущен!")
    print("🔥 Все кнопки работают!")
    print("✅ Главное меню с ПРОФИЛЕМ")
    print("✅ Игры (7 видов, включая новые Санки!)")
    print("✅ Новая игра САНКИ (RampageBET) с анимацией спиннеров!")
    print("✅ Игра в кости с ДВУМЯ кубиками для 'Произведение > 18'!")
    print("✅ Пополнение через @CryptoBot с комиссией 5%")
    print("✅ Вывод через @CryptoBot")
    print("✅ Админ-панель с ВЫДАЧЕЙ ВАЛЮТЫ")
    print("✅ Баланс и финансы")
    print("✅ Реферальная система")
    print("✅ Бонусы и достижения")
    print("✅ Статистика")
    print("✅ Поддержка")
    
    last_update_id = 0
    
    while True:
        try:
            # Проверяем ожидающие инвойсы
            check_pending_invoices()
            
            response = requests.post(URL + "getUpdates", 
                                   json={"offset": last_update_id + 1, "timeout": 50}, 
                                   timeout=55)
            
            if response.status_code == 200:
                data = response.json()
                if "result" in data:
                    for update in data["result"]:
                        last_update_id = update["update_id"]
                        handle_update(update)
                    
                    # Периодическое автосохранение
                    auto_saver.force_save()
            else:
                logging.warning(f"Ошибка HTTP запроса: {response.status_code}")
                time.sleep(5)
            
            time.sleep(0.5)
            
        except requests.exceptions.Timeout:
            logging.warning("Таймаут getUpdates, продолжаем...")
            continue
        except requests.exceptions.ConnectionError:
            logging.warning("Ошибка соединения, переподключаемся...")
            time.sleep(10)
            continue
        except Exception as e:
            logging.error(f"Общая ошибка в main: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
