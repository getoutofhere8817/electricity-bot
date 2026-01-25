#!/usr/bin/env python3

# -*- coding: utf-8 -*-

“””
Телеграм-бот для відстеження відключень світла у Рівному
“””

import asyncio
import logging
import os
import re
from datetime import datetime, time
from typing import Dict, List, Optional
import aiohttp
from aiohttp import web
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
Application,
CommandHandler,
CallbackQueryHandler,
ContextTypes,
)

# Налаштування логування

logging.basicConfig(
format=’%(asctime)s - %(name)s - %(levelname)s - %(message)s’,
level=logging.INFO
)
logger = logging.getLogger(**name**)

# URL сайту з графіком відключень

DISCONNECTIONS_URL = “https://www.roe.vsei.ua/disconnections”

# Збереження даних користувачів

user_data_storage: Dict[int, Dict] = {}

# Збереження попереднього графіку для відстеження змін

previous_schedule: Dict = {}

class ElectricityScheduleParser:
“”“Клас для парсингу графіку відключень”””

```
@staticmethod
async def fetch_schedule() -> Optional[Dict]:
    """Отримує графік відключень з сайту"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(DISCONNECTIONS_URL) as response:
                if response.status != 200:
                    logger.error(f"Помилка отримання даних: {response.status}")
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                # Шукаємо таблицю з графіком
                schedule_data = ElectricityScheduleParser._parse_table(soup)
                return schedule_data
                
    except Exception as e:
        logger.error(f"Помилка парсингу: {e}")
        return None

@staticmethod
def _parse_table(soup: BeautifulSoup) -> Dict:
    """Парсить таблицю з графіком відключень"""
    schedule = {}
    
    try:
        # Знаходимо таблицю
        table = soup.find('table')
        if not table:
            logger.warning("Таблиця не знайдена")
            return schedule
        
        rows = table.find_all('tr')
        
        # Перша строка - заголовки черг
        headers = []
        header_row = rows[0] if rows else None
        if header_row:
            cells = header_row.find_all(['td', 'th'])
            for cell in cells:
                text = cell.get_text(strip=True)
                if 'Черга' in text or 'Підчерга' in text:
                    headers.append(text)
        
        # Обробляємо дати
        for row in rows[1:]:
            cells = row.find_all(['td', 'th'])
            if not cells:
                continue
            
            # Перша клітинка - дата
            date_cell = cells[0].get_text(strip=True)
            
            # Перевіряємо чи це дата
            if re.match(r'\d{2}\.\d{2}\.\d{4}', date_cell):
                schedule[date_cell] = {}
                
                # Обробляємо черги
                for i, cell in enumerate(cells[1:], 1):
                    time_slots = cell.get_text(separator='  ', strip=True)  # Додаємо пробіли між періодами
                    # Очищаємо множинні пробіли
                    time_slots = ' '.join(time_slots.split())
                    
                    if time_slots and time_slots != 'Очікується':
                        queue_num = f"Черга {(i + 1) // 2}"
                        subqueue = f"{(i + 1) // 2}.{1 if i % 2 == 1 else 2}"
                        
                        if queue_num not in schedule[date_cell]:
                            schedule[date_cell][queue_num] = {}
                        
                        schedule[date_cell][queue_num][subqueue] = time_slots
        
        return schedule
        
    except Exception as e:
        logger.error(f"Помилка парсингу таблиці: {e}")
        return {}
```

async def check_schedule_changes(context: ContextTypes.DEFAULT_TYPE, new_schedule: Dict, date: str) -> None:
“”“Перевіряє зміни в графіку та надсилає сповіщення”””
global previous_schedule

```
if date not in previous_schedule:
    return

old_schedule = previous_schedule[date]

# Перевіряємо кожного користувача
for user_id, user_info in user_data_storage.items():
    if not user_info.get('notifications_enabled'):
        continue
    
    queue = user_info.get('queue')
    subqueue = user_info.get('subqueue')
    
    if not queue or not subqueue:
        continue
    
    queue_key = f"Черга {queue}"
    subqueue_key = f"{queue}.{subqueue}"
    
    # Перевіряємо чи є ця черга в обох графіках
    old_time = None
    new_time = None
    
    if queue_key in old_schedule and subqueue_key in old_schedule[queue_key]:
        old_time = old_schedule[queue_key][subqueue_key]
    
    if queue_key in new_schedule[date] and subqueue_key in new_schedule[date][queue_key]:
        new_time = new_schedule[date][queue_key][subqueue_key]
    
    # Якщо графік змінився
    if old_time != new_time:
        try:
            change_message = f"🔄 *ОНОВЛЕННЯ ГРАФІКУ на {date}*\n\n"
            change_message += f"Ваша черга: *{queue}.{subqueue}*\n\n"
            
            if old_time and new_time:
                change_message += f"❌ Було: {old_time}\n"
                change_message += f"✅ Стало: {new_time}\n\n"
                change_message += "⚠️ Графік відключень змінився!"
            elif not old_time and new_time:
                change_message += f"✅ Додано відключення: {new_time}\n\n"
                change_message += "⚠️ Для вашої черги додано нові відключення!"
            elif old_time and not new_time:
                change_message += f"❌ Було: {old_time}\n\n"
                change_message += "🎉 Відключення скасовано для вашої черги!"
            
            await context.bot.send_message(
                chat_id=user_id,
                text=change_message,
                parse_mode='Markdown'
            )
            
            logger.info(f"Надіслано сповіщення про зміну графіку користувачу {user_id}")
            
        except Exception as e:
            logger.error(f"Помилка надсилання сповіщення про зміну: {e}")
```

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
“”“Обробник команди /start”””
user_id = update.effective_user.id

```
# Ініціалізуємо дані користувача
if user_id not in user_data_storage:
    user_data_storage[user_id] = {
        'queue': None,
        'subqueue': None,
        'notifications_enabled': False
    }

welcome_message = (
    "🔌 Вітаю! Я бот для відстеження відключень світла у Рівному.\n\n"
    "📋 Доступні команди:\n"
    "/setqueue - Встановити вашу чергу відключень\n"
    "/schedule - Подивитись графік на сьогодні\n"
    "/notify - Увімкнути/вимкнути сповіщення\n"
    "/help - Допомога\n\n"
    "💡 Бот надсилає сповіщення:\n"
    "• За 10 хвилин до відключення\n"
    "• На початку відключення\n"
    "• За 10 хвилин до відновлення\n"
    "• При відновленні світла\n\n"
    "Почніть з команди /setqueue, щоб налаштувати ваші сповіщення!"
)

await update.message.reply_text(welcome_message)
```

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
“”“Обробник команди /help”””
help_text = (
“ℹ️ *Як користуватися ботом:*\n\n”
“1️⃣ Використайте /setqueue, щоб встановити вашу чергу\n”
“2️⃣ Увімкніть сповіщення командою /notify\n”
“3️⃣ Бот буде автоматично повідомляти вас про відключення\n\n”
“📊 /schedule - Переглянути графік\n”
“🔔 /notify - Керування сповіщеннями\n\n”
“Щоб дізнатись вашу чергу, відвідайте:\n”
“🌐 [Графік для міста Рівне](https://www.roe.vsei.ua/wp-content/uploads/2026/01/GPV_cherga_misto_Rivne.pdf)\n”
“🌐 [Графік для Рівненської області](https://www.roe.vsei.ua/wp-content/uploads/2026/01/GPV_cherga_Rivnenska_oblast-1.pdf)”
)

```
await update.message.reply_text(help_text, parse_mode='Markdown', disable_web_page_preview=True)
```

async def set_queue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
“”“Обробник команди /setqueue”””
keyboard = []

```
# Створюємо кнопки для черг 1-6
for queue in range(1, 7):
    row = [
        InlineKeyboardButton(f"Черга {queue}.1", callback_data=f"queue_{queue}_1"),
        InlineKeyboardButton(f"Черга {queue}.2", callback_data=f"queue_{queue}_2")
    ]
    keyboard.append(row)

reply_markup = InlineKeyboardMarkup(keyboard)

await update.message.reply_text(
    "🔢 Оберіть вашу чергу відключень:\n\n"
    "Ви можете дізнатись свою чергу на сайті Рівнеобленерго.",
    reply_markup=reply_markup
)
```

async def queue_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
“”“Обробник вибору черги”””
query = update.callback_query
await query.answer()

```
user_id = update.effective_user.id

# Парсимо дані callback
parts = query.data.split('_')
queue = int(parts[1])
subqueue = int(parts[2])

# Зберігаємо дані користувача
if user_id not in user_data_storage:
    user_data_storage[user_id] = {}

user_data_storage[user_id]['queue'] = queue
user_data_storage[user_id]['subqueue'] = subqueue

await query.edit_message_text(
    f"✅ Чергу встановлено: {queue}.{subqueue}\n\n"
    f"Тепер використайте /notify, щоб увімкнути сповіщення!"
)
```

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
“”“Обробник команди /schedule”””
await update.message.reply_text(“⏳ Завантажую графік…”)

```
schedule = await ElectricityScheduleParser.fetch_schedule()

if not schedule:
    await update.message.reply_text(
        "❌ Не вдалося отримати графік. Спробуйте пізніше."
    )
    return

user_id = update.effective_user.id
user_queue = user_data_storage.get(user_id, {}).get('queue')
user_subqueue = user_data_storage.get(user_id, {}).get('subqueue')

# Формуємо повідомлення
today = datetime.now().strftime('%d.%m.%Y')

# Якщо є дані на сьогодні - показуємо їх
if today in schedule:
    target_date = today
# Якщо немає - показуємо найближчу доступну дату
else:
    available_dates = sorted(schedule.keys())
    target_date = available_dates[0] if available_dates else None

if not target_date:
    await update.message.reply_text("ℹ️ Графік ще не опубліковано.")
    return

message = f"📅 *Графік відключень на {target_date}*\n\n"

if user_queue and user_subqueue:
    queue_key = f"Черга {user_queue}"
    subqueue_key = f"{user_queue}.{user_subqueue}"
    
    if queue_key in schedule[target_date] and subqueue_key in schedule[target_date][queue_key]:
        times = schedule[target_date][queue_key][subqueue_key]
        message += f"🔴 *Ваша черга {user_queue}.{user_subqueue}*:\n{times}\n\n"
    else:
        message += f"✅ Для вашої черги {user_queue}.{user_subqueue} відключень не заплановано!\n\n"

message += "📊 *Всі черги:*\n"
for queue, subqueues in schedule[target_date].items():
    message += f"\n*{queue}*\n"
    for subqueue, times in subqueues.items():
        message += f"  • {subqueue}: {times}\n"

await update.message.reply_text(message, parse_mode='Markdown')
```

async def notify_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
“”“Обробник команди /notify”””
user_id = update.effective_user.id

```
if user_id not in user_data_storage or not user_data_storage[user_id].get('queue'):
    await update.message.reply_text(
        "⚠️ Спочатку встановіть вашу чергу командою /setqueue"
    )
    return

current_status = user_data_storage[user_id].get('notifications_enabled', False)
new_status = not current_status

user_data_storage[user_id]['notifications_enabled'] = new_status

if new_status:
    message = (
        "🔔 Сповіщення *увімкнено*!\n\n"
        "Ви отримуватимете повідомлення:\n"
        "• За 10 хвилин до відключення\n"
        "• Коли розпочнеться відключення\n"
        "• За 10 хвилин до відновлення\n"
        "• Коли відновиться електропостачання"
    )
else:
    message = "🔕 Сповіщення *вимкнено*"

await update.message.reply_text(message, parse_mode='Markdown')
```

async def check_and_notify(context: ContextTypes.DEFAULT_TYPE) -> None:
“”“Перевіряє графік та надсилає сповіщення”””
global previous_schedule

```
schedule = await ElectricityScheduleParser.fetch_schedule()

if not schedule:
    return

today = datetime.now().strftime('%d.%m.%Y')
current_time = datetime.now().time()

# Перевірка на зміни графіку
if previous_schedule and today in schedule:
    await check_schedule_changes(context, schedule, today)

# Зберігаємо поточний графік для наступної перевірки
if today in schedule:
    previous_schedule[today] = schedule[today].copy()

if today not in schedule:
    return

# Перевіряємо кожного користувача
for user_id, user_info in user_data_storage.items():
    if not user_info.get('notifications_enabled'):
        continue
    
    queue = user_info.get('queue')
    subqueue = user_info.get('subqueue')
    
    if not queue or not subqueue:
        continue
    
    queue_key = f"Черга {queue}"
    subqueue_key = f"{queue}.{subqueue}"
    
    if queue_key not in schedule[today] or subqueue_key not in schedule[today][queue_key]:
        continue
    
    time_slots = schedule[today][queue_key][subqueue_key]
    
    # Парсимо часові проміжки
    slots = time_slots.split()
    
    for slot in slots:
        if '-' in slot:
            start_str, end_str = slot.split('-')
            
            try:
                start_hour, start_min = map(int, start_str.split(':'))
                start_time = time(start_hour, start_min)
                
                end_hour, end_min = map(int, end_str.split(':'))
                end_time = time(end_hour, end_min)
                
                # Сповіщення за 10 хвилин до ВІДКЛЮЧЕННЯ
                warning_10min_start = time(
                    start_hour if start_min >= 10 else (start_hour - 1) % 24,
                    (start_min - 10) % 60
                )
                
                if warning_10min_start.hour == current_time.hour and warning_10min_start.minute == current_time.minute:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"⚠️ Увага! Через 10 хвилин (о {start_str}) буде відключено світло.\n\n"
                             f"⏱ Можливі відхилення від графіку до 1 години."
                    )
                
                # Сповіщення на початку відключення
                if start_time.hour == current_time.hour and start_time.minute == current_time.minute:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"🔴 Зараз відключено світло. Повернеться о {end_str}.\n\n"
                             f"⏱ Можливі відхилення від графіку до 1 години."
                    )
                
                # Сповіщення за 10 хвилин до ВІДНОВЛЕННЯ
                warning_10min_end = time(
                    end_hour if end_min >= 10 else (end_hour - 1) % 24,
                    (end_min - 10) % 60
                )
                
                if warning_10min_end.hour == current_time.hour and warning_10min_end.minute == current_time.minute:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"⏰ Через 10 хвилин (о {end_str}) світло буде відновлено!\n\n"
                             f"⏱ Можливі відхилення від графіку до 1 години."
                    )
                
                # Сповіщення про відновлення світла
                if end_time.hour == current_time.hour and end_time.minute == current_time.minute:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=f"🟢 Світло відновлено!\n\n"
                             f"💡 Перевірте чи дійсно є електропостачання - можливі відхилення від графіку."
                    )
                    
            except Exception as e:
                logger.error(f"Помилка обробки часу: {e}")
```

async def health_check(request):
“”“Keep-alive endpoint для Render.com та інших хостингів”””
return web.Response(text=“✅ Bot is running!”)

async def start_web_server():
“”“Запуск простого веб-сервера для keep-alive”””
app = web.Application()
app.router.add_get(’/’, health_check)
app.router.add_get(’/health’, health_check)

```
# Використовуємо PORT з змінних середовища (для Render) або 8080 за замовчуванням
port = int(os.getenv('PORT', '8080'))

runner = web.AppRunner(app)
await runner.setup()
site = web.TCPSite(runner, '0.0.0.0', port)
await site.start()

logger.info(f"🌐 Keep-alive веб-сервер запущено на порту {port}")
```

def main() -> None:
“”“Головна функція запуску бота”””
# Отримуємо токен зі змінних середовища (для хмарного розгортання)
# або з коду (для локального запуску)
TOKEN = os.getenv(“BOT_TOKEN”, “YOUR_BOT_TOKEN_HERE”)

```
if TOKEN == "YOUR_BOT_TOKEN_HERE":
    print("❌ ПОМИЛКА: Вставте токен вашого бота")
    print("")
    print("Варіант 1 (локально):")
    print("  Відкрийте цей файл і вставте токен в рядок:")
    print("  TOKEN = os.getenv('BOT_TOKEN', 'ВАШ_ТОКЕН_ТУТ')")
    print("")
    print("Варіант 2 (на сервері):")
    print("  Додайте змінну середовища BOT_TOKEN зі значенням вашого токена")
    print("")
    print("Отримайте токен у @BotFather в Telegram")
    return

logger.info("🤖 Запуск бота...")

# Створюємо application
application = Application.builder().token(TOKEN).build()

# Реєструємо обробники команд
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CommandHandler("setqueue", set_queue))
application.add_handler(CommandHandler("schedule", schedule_command))
application.add_handler(CommandHandler("notify", notify_command))
application.add_handler(CallbackQueryHandler(queue_callback, pattern="^queue_"))

# Додаємо перевірку кожні 10 хвилин
job_queue = application.job_queue
job_queue.run_repeating(check_and_notify, interval=600, first=10)

# Запускаємо бота
logger.info("✅ Бот успішно запущено і працює!")
logger.info("🔍 Перевірка графіків кожні 10 хвилин...")
application.run_polling(allowed_updates=Update.ALL_TYPES)
```

if **name** == ‘**main**’:
main()