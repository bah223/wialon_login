from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.db_utils import add_token_history, get_user_by_username
from app.wialon_api import check_token, create_token
from app.models import MasterToken
import datetime

import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile
from app.scraper import wialon_login_and_get_url, make_api_request
from app.utils import logger, get_env_variable, get_bool_env_variable, is_user_allowed
from app.database import AsyncSessionLocal, check_db_connection
from app.db_utils import create_or_update_user, get_all_user_tokens, get_user_by_username
from app.bot_utils import (
    choose_check_mode, get_tor_choice_keyboard, get_manual_token_keyboard, get_confirm_delete_all_keyboard, get_connection_choice_keyboard, get_saved_creds_connection_keyboard,
    handle_check_token_manual, handle_token_input, handle_check_specific_token, handle_check_mode_choice
)
from app.handlers_login import router as login_router
from app.handlers_history import router as history_router
from app.handlers_delete import router as delete_router
from app.states import GetTokenStates  # <--- Добавлен импорт GetTokenStates
from sqlalchemy import select  # <-- добавлен импорт select для работы с запросами в БД

# Получаем токен бота из переменных окружения
bot = Bot(token=get_env_variable("BOT_TOKEN"))
dp = Dispatcher(storage=MemoryStorage())

# --- Регистрация нового handler для логина ---
dp.include_router(login_router)

# --- Регистрация нового handler для истории операций ---
dp.include_router(history_router)

# --- Регистрация нового handler для удаления токенов ---
dp.include_router(delete_router)

@dp.message(Command(commands=['start', 'help']))
async def start_command(message: types.Message):
    """Обработчик команды /start и /help."""
    if not is_user_allowed(message.from_user.id):
        await message.reply("Доступ запрещен. Обратитесь к администратору.")
        return

    help_text = """
🤖 Wialon Token Bot

Доступные команды:
/get_token - Получить токен через OAuth (браузер)
/check_token - Проверить Access Token и получить данные сессии
/help - Показать это сообщение
    """
    await message.reply(help_text, parse_mode=ParseMode.HTML)

@dp.message(Command(commands=['check_token']))
async def check_token_command(message: types.Message, state: FSMContext):
    """
    Команда для проверки токена: выбор сохраненного или ручной ввод.
    Теперь токены ищутся по username (логину Wialon), а не по Telegram ID.
    """
    data = await state.get_data()
    username = data.get("username")
    if not username:
        # Показываем меню команд, если логин не получен через get_token
        await message.reply("Пожалуйста, сначала получите токен через /get_token, чтобы использовать эту команду.")
        return
    # Получаем токены по username
    async with AsyncSessionLocal() as session:
        from app.db_utils import get_user_by_username
        from app.models import MasterToken
        user = await get_user_by_username(session, username)
        user_tokens = []
        if user:
            master_tokens = await session.execute(select(MasterToken).where(MasterToken.user_id == user.id))
            master_tokens = master_tokens.scalars().all()
            for mt in master_tokens:
                user_tokens.append({
                    "token": mt.token,
                    "user_name": user.username
                })
    keyboard = get_manual_token_keyboard()
    await message.reply("Выберите действие:", reply_markup=keyboard, parse_mode=ParseMode.HTML)

@dp.callback_query(lambda c: c.data == "check_token_manual")
async def process_check_token_manual(callback_query: types.CallbackQuery, state: FSMContext):
    await handle_check_token_manual(callback_query, state)

@dp.callback_query(lambda c: c.data.startswith("check_token:"))
async def process_check_specific_token(callback_query: types.CallbackQuery, state: FSMContext):
    await handle_check_specific_token(callback_query, state, choose_check_mode)

@dp.callback_query(lambda c: c.data.startswith("check_tor:"))
async def process_check_mode_choice(callback_query: types.CallbackQuery, state: FSMContext):
    await handle_check_mode_choice(callback_query, state, check_token_process)

@dp.callback_query(lambda c: c.data == "delete_all_tokens")
async def process_delete_all_tokens(callback_query: types.CallbackQuery):
    """Обработчик для удаления всех токенов пользователя."""
    await callback_query.answer()
    
    # Получаем ID пользователя
    user_id = callback_query.from_user.id
    
    # Создаем клавиатуру для подтверждения
    keyboard = get_confirm_delete_all_keyboard()
    
    # Запрашиваем подтверждение
    await callback_query.message.edit_text(
        "⚠️ <b>Внимание!</b> Вы уверены, что хотите удалить <b>ВСЕ</b> сохраненные токены?\n\n"
        "Это действие нельзя отменить.",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

@dp.callback_query(lambda c: c.data == "confirm_delete_all")
async def process_confirm_delete_all(callback_query: types.CallbackQuery):
    """Обработчик подтверждения удаления всех токенов."""
    await callback_query.answer()
    
    # Получаем ID пользователя
    user_id = callback_query.from_user.id
    
    async with AsyncSessionLocal() as session:
        await delete_token(session, user_id)
    
    # Сообщаем об успешном удалении
    await callback_query.message.edit_text(
        "✅ Все токены успешно удалены.",
        parse_mode=ParseMode.HTML
    )

@dp.callback_query(lambda c: c.data == "cancel_delete_all")
async def process_cancel_delete_all(callback_query: types.CallbackQuery):
    """Обработчик отмены удаления всех токенов."""
    await callback_query.answer()
    
    # Возвращаемся к списку токенов
    await token_list_command(callback_query.message)

@dp.callback_query(lambda c: c.data == "use_saved_credentials")
async def process_use_saved_credentials(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик для использования сохраненных учетных данных."""
    await callback_query.answer()
    
    # Получаем сохраненные учетные данные
    async with AsyncSessionLocal() as session:
        credentials = await get_credentials(session, callback_query.from_user.id)
    if not credentials:
        await callback_query.message.edit_text("❌ Сохраненные данные не найдены или повреждены.")
        return
    
    # Спрашиваем, какой режим подключения использовать
    keyboard = get_saved_creds_connection_keyboard()
    
    await callback_query.message.edit_text(
        f"Используем сохраненные данные для <b>{credentials['username']}</b>.\n\n"
        "Выберите режим подключения:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

@dp.callback_query(lambda c: c.data.startswith("saved_creds_tor:"))
async def process_saved_creds_connection(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик для выбора режима подключения с сохраненными данными."""
    await callback_query.answer()
    
    # Определяем, использовать ли Tor
    use_tor = callback_query.data.split(":")[1] == "yes"
    
    # Получаем сохраненные учетные данные
    async with AsyncSessionLocal() as session:
        credentials = await get_credentials(session, callback_query.from_user.id)
    if not credentials:
        await callback_query.message.edit_text("❌ Сохраненные данные не найдены или повреждены.")
        return
    
    # Отображаем сообщение о процессе
    status_message = await callback_query.message.edit_text(
        f"🔄 Получаем токен для <b>{credentials['username']}</b> {'через Tor' if use_tor else 'напрямую'}...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        logger.info(f"[process_saved_creds_connection] Начало получения токена для user_id={callback_query.from_user.id}, username={credentials['username']}, use_tor={use_tor}")
        # Получаем URL Wialon из переменных окружения
        try:
            wialon_url = get_env_variable("WIALON_BASE_URL")
        except Exception as e:
            logger.warning(f"[process_saved_creds_connection] Не удалось получить WIALON_BASE_URL: {e}")
            wialon_url = "https://hosting.wialon.com/login.html?duration=0"
            logger.info(f"[process_saved_creds_connection] Используется дефолтный URL: {wialon_url}")
            
        # Запускаем процесс авторизации с сохраненными данными
        result = await wialon_login_and_get_url(
            credentials['username'], 
            credentials['password'], 
            wialon_url,
            use_tor=use_tor
        )
        logger.info(f"[process_saved_creds_connection] Ответ от wialon_login_and_get_url: {str(result)[:300]}")
        
        # Проверяем, что получили строку (старый формат) или словарь (новый формат)
        if isinstance(result, dict):
            token = result.get("token", "")
            full_url = result.get("url", "")
        else:
            # Обратная совместимость
            token = extract_token_from_url(result)
            full_url = result
        logger.info(f"[process_saved_creds_connection] Извлечён токен: {token[:8]}... (длина {len(token)})")
        
        if token:
            async with AsyncSessionLocal() as session:
                await add_token(session, callback_query.from_user.id, token)
            
            # Сохраняем информацию о токене
            token_info = {
                "user_name": credentials['username'],
                "created_at": int(time.time()),
                "created_via": "saved_credentials"
            }
            async with AsyncSessionLocal() as session:
                await update_token_info(session, callback_query.from_user.id, token, token_info)
            
            # Формируем текст сообщения
            url_info = f"\n\n🌐 <b>URL:</b>\n<code>{full_url}</code>" if full_url else ""
            
            await status_message.edit_text(
                f"✅ Токен успешно получен и сохранен!\n\n"
                f"🔑 <code>{token}</code>"
                f"{url_info}",
                parse_mode=ParseMode.HTML
            )
            logger.info(f"[process_saved_creds_connection] Токен успешно сохранён для user_id={callback_query.from_user.id}")
        else:
            # В случае, если токен не был извлечен
            url_display = full_url if isinstance(full_url, str) else str(result)
            logger.warning(f"[process_saved_creds_connection] Не удалось извлечь токен. Ответ: {str(result)[:300]}")
            await status_message.edit_text(
                f"⚠️ Не удалось извлечь токен из полученного результата.\n\n"
                f"Результат: <code>{url_display}</code>",
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"[process_saved_creds_connection] Ошибка при получении токена: {e}", exc_info=True)
        await status_message.edit_text(
            f"❌ Ошибка при получении токена: {str(e)}",
            parse_mode=ParseMode.HTML
        )

async def check_token_process(message: types.Message, token: str, use_tor: bool = None, state: FSMContext = None):
    """
    Асинхронная проверка токена через Wialon API с выводом результата пользователю.
    """
    status_msg = await message.reply("⏳ Проверяю токен...")
    params = {
        "svc": "token/login",
        "params": json.dumps({"token": token, "fl": 1})
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(WIALON_API_URL, params=params) as resp:
                result = await resp.json()
        if "error" in result:
            await status_msg.edit_text(f"❌ Ошибка авторизации: {result.get('error')} {result.get('reason', '')}")
            return
        user = result.get("user", {})
        user_info = f"👤 <b>User:</b> {user.get('nm', 'N/A')} (ID: {user.get('id', 'N/A')})"
        expire_time = result.get("tm")
        expire_str = f"⏳ <b>Expires:</b> {datetime.datetime.fromtimestamp(expire_time).strftime('%Y-%m-%d %H:%M:%S') if expire_time else 'N/A'}"
        await status_msg.edit_text(f"✅ Токен валиден!\n{user_info}\n{expire_str}", parse_mode=ParseMode.HTML)
        # (Опционально) Запись в историю проверок можно добавить здесь
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка при проверке токена: {str(e)}")

async def start_telegram_bot():
    """Запускает Telegram бота."""
    logger.info("Starting Telegram bot...")
    await dp.start_polling(bot)

async def main():
    """Основная функция для запуска бота."""
    await start_telegram_bot()

if __name__ == '__main__':
    asyncio.run(main())

@dp.message(Command(commands=['my_logins']))
async def my_logins_command(message: types.Message):
    """Показать все сохранённые логины пользователя."""
    from app.database import AsyncSessionLocal
    from app.db_utils import get_user_by_username
    from app.models import User
    user_id = message.from_user.id
    username = None
    async with AsyncSessionLocal() as session:
        # Найти все логины, связанные с этим telegram id (если есть связь)
        result = await session.execute(
            """
            SELECT username FROM users
            """
        )
        usernames = [row[0] for row in result.fetchall()]
    if not usernames:
        await message.reply("У вас нет сохранённых логинов.")
        return
    text = "\n".join([f"👤 <b>{u}</b>" for u in usernames])
    await message.reply(f"Ваши сохранённые логины в системе:\n\n{text}", parse_mode=ParseMode.HTML)

@dp.message(Command(commands=['delete_login']))
async def delete_login_command(message: types.Message):
    """Удалить логин пользователя по названию."""
    args = message.get_args()
    if not args:
        await message.reply("Укажите логин для удаления: /delete_login <логин>")
        return
    login_to_delete = args.strip()
    from app.database import AsyncSessionLocal
    from app.models import User
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            f"DELETE FROM users WHERE username = :username RETURNING username",
            {"username": login_to_delete}
        )
        deleted = result.rowcount
        await session.commit()
    if deleted:
        await message.reply(f"✅ Логин <b>{login_to_delete}</b> удалён.", parse_mode=ParseMode.HTML)
    else:
        await message.reply(f"Логин <b>{login_to_delete}</b> не найден.", parse_mode=ParseMode.HTML)

from aiogram.fsm.state import State, StatesGroup

class CustomTokenStates(StatesGroup):
    waiting_for_access_rights = State()
    waiting_for_duration = State()

@dp.message(Command(commands=['token_create_custom']))
async def token_create_custom_command(message: types.Message, state: FSMContext):
    """Начать процесс создания кастомного токена с выбором прав и срока действия."""
    async with AsyncSessionLocal() as session:
        user_tokens = await get_all_user_tokens(session, message.from_user.id)
    keyboard = get_tor_choice_keyboard()
    keyboard.inline_keyboard.insert(0, [
        types.InlineKeyboardButton(
            text="✏️ Ввести токен вручную", 
            callback_data="api_create_token_manual"
        )
    ])
    if user_tokens:
        for i, token_data in enumerate(user_tokens[:5]):
            token = token_data["token"]
            user_info = f" ({token_data['user_name']})" if "user_name" in token_data else ""
            keyboard.inline_keyboard.insert(i, [
                types.InlineKeyboardButton(
                    text=f"🔑 Токен #{i+1}{user_info}", 
                    callback_data=f"api_create_token:{i}"
                )
            ])
        message_text = "Выберите токен, на основе которого будет создан новый токен (кастомные права):"
    else:
        message_text = "У вас нет сохраненных токенов. Введите токен для создания нового (кастомные права):"
    await message.reply(
        message_text,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )
    # Устанавливаем начальное состояние FSM
    await state.clear()

@dp.callback_query(lambda c: c.data.startswith("api_create_token:"))
async def process_api_create_token_custom(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    index = int(callback_query.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        user_tokens = await get_all_user_tokens(session, callback_query.from_user.id)
    token = user_tokens[index]["token"]
    await state.update_data(source_token=token)
    await callback_query.message.edit_text(
        "Введите маску прав доступа (uacl) для нового токена (например, 0xFFFFFFFF):",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(CustomTokenStates.waiting_for_access_rights)

@dp.message(CustomTokenStates.waiting_for_access_rights)
async def process_access_rights_input(message: types.Message, state: FSMContext):
    uacl = message.text.strip()
    await state.update_data(uacl=uacl)
    await message.reply("Введите длительность токена в секундах (например, 86400 для 1 дня):")
    await state.set_state(CustomTokenStates.waiting_for_duration)

@dp.message(CustomTokenStates.waiting_for_duration)
async def process_duration_input(message: types.Message, state: FSMContext):
    try:
        duration = int(message.text.strip())
        if duration <= 0:
            raise ValueError
    except Exception:
        await message.reply("Некорректная длительность. Введите положительное целое число (секунды):")
        return
    await state.update_data(duration=duration)
    data = await state.get_data()
    # Переходим к выбору режима подключения (Tor/напрямую)
    token = data.get("source_token")
    await show_api_connection_choice(message, state, token)

@dp.callback_query(lambda c: c.data.startswith("api_token_action:"))
async def process_api_token_action(callback_query: types.CallbackQuery, state: FSMContext):
    """Создание/обновление токена через API с поддержкой кастомных прав и срока действия."""
    try:
        await callback_query.answer()
        use_tor = callback_query.data.split(":")[1] == "yes"
        
        data = await state.get_data()
        source_token = data.get("source_token")
        api_operation = data.get("api_operation", "create")  # По умолчанию - создание
        token_to_update = data.get("token_to_update")  # Токен для обновления (только для операции update)
        uacl = data.get("uacl")
        duration = data.get("duration")
        
        if not source_token:
            await callback_query.message.edit_text("❌ Токен не найден")
            return
             
        # Проверяем наличие токена для обновления при операции update
        if api_operation == "update" and not token_to_update:
            await callback_query.message.edit_text("❌ Токен для обновления не найден")
            return
            
        # Очищаем токен от URL и других лишних данных
        if isinstance(source_token, str):
            if "access_token=" in source_token:
                source_token = source_token.split("access_token=")[1].split("&")[0]
            elif source_token.startswith("{") and "token" in source_token:
                try:
                    token_data = json.loads(source_token)
                    source_token = token_data.get("token", source_token)
                except:
                    pass
        
        # Также очищаем токен для обновления, если он есть
        if api_operation == "update" and isinstance(token_to_update, str):
            if "access_token=" in token_to_update:
                token_to_update = token_to_update.split("access_token=")[1].split("&")[0]
            elif token_to_update.startswith("{") and "token" in token_to_update:
                try:
                    token_data = json.loads(token_to_update)
                    token_to_update = token_data.get("token", token_to_update)
                except:
                    pass
        
        status_message = await callback_query.message.edit_text(
            f"🔄 {('Создаем' if api_operation=='create' else 'Обновляем')} токен {'через Tor' if use_tor else 'напрямую'}..."
        )
        
        # Получаем URL API
        wialon_api_url = get_env_variable("WIALON_API_URL", "https://hst-api.wialon.com/wialon/ajax.html")
        
        # 1. Логин через token/login
        login_params = {
            "svc": "token/login",
            "params": json.dumps({
                "token": source_token,
                "fl": 7
            })
        }
        
        logger.debug(f"Login params: {login_params}")
        login_result = await make_api_request(wialon_api_url, login_params, use_tor)
        logger.debug(f"Login result: {login_result}")
        
        if "error" in login_result:
            await status_message.edit_text(f"❌ Ошибка авторизации: {login_result.get('error')} {login_result.get('reason', '')}")
            return
             
        # Получаем eid из результата логина
        session_id = login_result.get("eid")
        if not session_id:
            await status_message.edit_text("❌ Не удалось получить ID сессии")
            return
        
        # Получаем user_id напрямую из ответа token/login
        user_id = login_result.get("user", {}).get("id")
        if not user_id:
            await status_message.edit_text("❌ Не удалось получить ID пользователя из ответа")
            return
        
        logger.debug(f"Полученный ID сессии: {session_id}")
        logger.debug(f"Полученный ID пользователя: {user_id}")
        
        # 2. Создание/обновление токена через token/update
        params = {
            "callMode": api_operation,
            "userId": str(user_id),
            "h": "TOKEN" if api_operation == "create" else token_to_update,
            "app": "Wialon Hosting – a platform for GPS monitoring",
            "at": 0,
            "dur": int(duration) if duration else 0,
            "fl": int(uacl, 0) if uacl else 512,
            "p": "{}",
            "items": []
        }
        
        create_params = {
            "svc": "token/update",
            "params": json.dumps(params),
            "sid": session_id
        }
        
        logger.debug(f"Create params: {create_params}")
        create_result = await make_api_request(wialon_api_url, create_params, use_tor)
        logger.debug(f"Create result: {create_result}")
        
        if "error" in create_result:
            await status_message.edit_text(f"❌ Ошибка {('создания' if api_operation=='create' else 'обновления')} токена: {create_result.get('reason', create_result.get('error'))}")
            return
             
        # Получаем новый токен из результата
        new_token = create_result.get("h")
        if not new_token:
            await status_message.edit_text(f"❌ Не удалось {('создать' if api_operation=='create' else 'обновить')} токен")
            return
             
        # Сохраняем новый токен как дочерний от исходного
        # Метод add_token в TokenStorage является синхронным
        if api_operation == "create":
            # При создании указываем исходный токен как родительский
            async with AsyncSessionLocal() as session:
                await add_token(session, callback_query.from_user.id, new_token, parent_token=source_token)
        else:
            # При обновлении сохраняем информацию об обоих токенах
            async with AsyncSessionLocal() as session:
                await add_token(session, callback_query.from_user.id, new_token, parent_token=token_to_update)
        
        # Сохраняем информацию о токене
        token_info = {
            "user_name": login_result.get("au"),
            "expire_time": login_result.get("tm"),
            "created_at": int(time.time()),
            "created_via": "api",
            "token_type": api_operation,
            "uacl": uacl,
            "duration": duration
        }
        async with AsyncSessionLocal() as session:
            await update_token_info(session, callback_query.from_user.id, new_token, token_info)
        
        await status_message.edit_text(
            f"✅ Токен успешно {('создан' if api_operation=='create' else 'обновлен')} через API!\n\n"
            f"🔑 <code>{new_token}</code>",
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logger.error(f"Error in API token operation: {e}")
        await callback_query.message.edit_text(f"❌ Произошла ошибка: {str(e)}")

@dp.message(Command(commands=["check_db"]))
async def check_db_command(message: types.Message):
    """
    Проверка подключения к базе данных.
    """
    await message.reply("⏳ Проверяю подключение к базе данных...")
    is_ok = await check_db_connection()
    if is_ok:
        await message.reply("✅ Подключение к базе данных установлено успешно!")
    else:
        await message.reply("❌ Ошибка подключения к базе данных! Проверьте настройки и логи.")

@dp.message(Command(commands=['get_token']))
async def get_token_command(message: types.Message, state: FSMContext):
    """
    Обработчик команды /get_token: если токен найден — вернуть, если нет — запустить FSM-сценарий получения логина/пароля/типа подключения.
    """
    async with AsyncSessionLocal() as session:
        # Получаем токены по username, если он уже был сохранён
        data = await state.get_data()
        username = data.get("username")
        user_tokens = []
        if username:
            from app.db_utils import get_user_by_username
            user = await get_user_by_username(session, username)
            if user:
                master_tokens = await session.execute(select(MasterToken).where(MasterToken.user_id == user.id))
                master_tokens = master_tokens.scalars().all()
                for mt in master_tokens:
                    user_tokens.append({
                        "token": mt.token,
                        "user_name": user.username
                    })
        if user_tokens:
            reply = "\n".join([
                f"🔑 <b>{t['user_name']}</b>: <code>{t['token'][:8]}...{t['token'][-4:]}</code>" for t in user_tokens
            ])
            await message.reply(f"Найдены ваши токены:\n{reply}", parse_mode=ParseMode.HTML)
            return
    # Если токенов нет — запустить FSM для получения логина/пароля
    await message.reply("\u274C Токен не найден. Давайте создадим новый!\n\nВведите логин Wialon:")
    await state.set_state(GetTokenStates.manual_input_username)

@dp.message(GetTokenStates.manual_input_username)
async def get_token_username(message: types.Message, state: FSMContext):
    await state.update_data(username=message.text.strip())
    await message.reply("Введите пароль Wialon:")
    await state.set_state(GetTokenStates.manual_input_password)

@dp.message(GetTokenStates.manual_input_password)
async def get_token_password(message: types.Message, state: FSMContext):
    await state.update_data(password=message.text.strip())
    keyboard = get_connection_choice_keyboard()
    await message.reply("Выберите способ подключения:", reply_markup=keyboard)
    await state.set_state(GetTokenStates.connection_mode_choice)

@dp.callback_query(GetTokenStates.connection_mode_choice)
async def get_token_connection_mode(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    use_tor = callback_query.data.split(":")[1] == "yes"
    data = await state.get_data()
    username = data.get("username")
    password = data.get("password")
    wialon_url = get_env_variable("WIALON_BASE_URL")
    result = await wialon_login_and_get_url(username, password, wialon_url, use_tor=use_tor)
    token = result.get("token")
    if token:
        # --- СОХРАНЯЕМ пользователя и мастер-токен по username ---
        from app.db_utils import create_or_update_user
        from app.models import MasterToken
        from app.database import AsyncSessionLocal
        import datetime
        async with AsyncSessionLocal() as session:
            user = await create_or_update_user(session, username, password)
            # Проверяем, есть ли уже такой токен у пользователя
            existing = await session.execute(select(MasterToken).where(MasterToken.user_id == user.id, MasterToken.token == token))
            if not existing.scalars().first():
                mt = MasterToken(
                    user_id=user.id,
                    token=token,
                    created_at=datetime.datetime.utcnow(),
                    creation_method="OAuth"
                )
                session.add(mt)
                await session.commit()
        await callback_query.message.edit_text(f"✅ Токен успешно получен!\n<code>{token}</code>", parse_mode=ParseMode.HTML)
    else:
        await callback_query.message.edit_text(f"❌ Не удалось получить токен. {result.get('error', '')}")
    await state.clear()
