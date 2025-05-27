from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.db_utils import add_token_history, get_user_by_username, save_token_chain, get_password_by_login
from app.wialon_api import check_token, create_token, get_available_objects
from app.models import MasterToken, User, WialonAccount, Token, TokenType
import datetime
import json

import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile
from app.scraper import wialon_login_and_get_url, make_api_request
from app.utils import logger, get_env_variable, get_bool_env_variable, is_user_allowed, encrypt_password, decrypt_password
from app.database import AsyncSessionLocal, check_db_connection
from app.db_utils import create_or_update_user, get_all_user_tokens, get_user_by_username
from app.bot_utils import (
    choose_check_mode, get_tor_choice_keyboard, get_manual_token_keyboard, get_confirm_delete_all_keyboard, get_connection_choice_keyboard, get_saved_creds_connection_keyboard,
    handle_check_token_manual, handle_token_input, handle_check_specific_token, handle_check_mode_choice
)
from app.handlers_login import router as login_router
from app.handlers_history import router as history_router
from app.handlers_delete import router as delete_router
from app.states import GetTokenStates, CustomTokenStates  # Обновлен импорт
from sqlalchemy import select
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.orm import selectinload

# Получаем токен бота из переменных окружения
bot = Bot(token=get_env_variable("BOT_TOKEN"))
dp = Dispatcher(storage=MemoryStorage())

# --- Регистрация нового handler для логина ---
dp.include_router(login_router)

# --- Регистрация нового handler для истории операций ---
dp.include_router(history_router)

# --- Регистрация нового handler для удаления токенов ---
dp.include_router(delete_router)

class TokenCreateStates(StatesGroup):
    choose_login = State()
    choose_master = State()
    choose_rights = State()
    rights_manual = State()
    choose_duration = State()
    duration_manual = State()
    choose_connection = State()

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
/token_create - Создать новый токен через API
/token_update - Обновить существующий токен
/check_token - Проверить Access Token и получить данные сессии
/my_tokens - Показать все ваши токены
/help - Показать это сообщение
    """
    await message.reply(help_text, parse_mode=ParseMode.HTML)

@dp.message(Command(commands=['token_create']))
async def token_create_command(message: types.Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        accounts = await session.execute(select(WialonAccount))
        accounts = accounts.scalars().all()
    if not accounts:
        await message.reply("Нет сохранённых логинов. Сначала добавьте логин через /get_token.")
        return
    buttons = [
        [types.InlineKeyboardButton(text=f"👤 {acc.username}", callback_data=f"create_token_login:{acc.username}")]
        for acc in accounts
    ]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.reply("Выберите логин для создания токена:", reply_markup=keyboard)
    await state.set_state(TokenCreateStates.choose_login)

@dp.callback_query(lambda c: c.data.startswith("create_token_login:"))
async def token_create_choose_login(callback_query: types.CallbackQuery, state: FSMContext):
    username = callback_query.data.split(":", 1)[1]
    async with AsyncSessionLocal() as session:
        account = await session.scalar(select(WialonAccount).where(WialonAccount.username == username))
        tokens = await session.execute(select(Token).where(Token.account_id == account.id, Token.token_type == TokenType.MASTER))
        master_tokens = tokens.scalars().all()
    if not master_tokens:
        await callback_query.message.edit_text(f"❌ Для логина <b>{username}</b> не найдено ни одного мастер-токена.", parse_mode="HTML")
        return
    buttons = [
        [types.InlineKeyboardButton(text=f"🔑 {t.token[:6]}...{t.token[-4:]}", callback_data=f"create_token_master:{t.id}")]
        for t in master_tokens
    ]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback_query.message.edit_text(f"Выберите мастер-токен для <b>{username}</b>:", reply_markup=keyboard, parse_mode="HTML")
    await state.update_data(username=username)
    await state.set_state(TokenCreateStates.choose_master)

@dp.callback_query(lambda c: c.data.startswith("create_token_master:"))
async def token_create_choose_master(callback_query: types.CallbackQuery, state: FSMContext):
    token_id = int(callback_query.data.split(":", 1)[1])
    async with AsyncSessionLocal() as session:
        token_obj = await session.get(Token, token_id)
    await state.update_data(master_token=token_obj.token)
    # Клавиатура выбора режима подключения
    buttons = [
        [types.InlineKeyboardButton(text="🧅 Через Tor", callback_data="create_token_conn:tor")],
        [types.InlineKeyboardButton(text="🚀 Напрямую", callback_data="create_token_conn:direct")]
    ]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback_query.message.edit_text("Выберите режим подключения:", reply_markup=keyboard)
    await state.set_state(TokenCreateStates.choose_connection)

@dp.callback_query(lambda c: c.data.startswith("create_token_conn:"))
async def token_create_choose_connection(callback_query: types.CallbackQuery, state: FSMContext):
    conn_type = callback_query.data.split(":", 1)[1]
    use_tor = conn_type == "tor"
    await state.update_data(use_tor=use_tor)
    # Далее — выбор прав доступа
    rights = [
        ("0xFFFFFFFF", "Все права"),
        ("0x1", "Только чтение"),
        ("0x7", "Чтение + базовые действия"),
        ("custom", "Ввести вручную")
    ]
    buttons = [[types.InlineKeyboardButton(text=f"{r[0]} — {r[1]}", callback_data=f"create_token_rights:{r[0]}")] for r in rights]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback_query.message.edit_text("Выберите права доступа для нового токена:", reply_markup=keyboard)
    await state.set_state(TokenCreateStates.choose_rights)

@dp.callback_query(lambda c: c.data.startswith("create_token_rights:"))
async def token_create_choose_rights(callback_query: types.CallbackQuery, state: FSMContext):
    uacl = callback_query.data.split(":", 1)[1]
    if uacl == "custom":
        await callback_query.message.edit_text("Введите маску прав доступа (например, 0xFFFFFFFF):")
        await state.set_state(TokenCreateStates.rights_manual)
        return
    await state.update_data(uacl=uacl)
    durations = [
        (86400, "1 день"),
        (604800, "7 дней"),
        (0, "Бессрочно"),
        ("custom", "Ввести вручную")
    ]
    buttons = [[types.InlineKeyboardButton(text=f"{d[1]}", callback_data=f"create_token_duration:{d[0]}")] for d in durations]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback_query.message.edit_text("Выберите длительность токена:", reply_markup=keyboard)
    await state.set_state(TokenCreateStates.choose_duration)

@dp.message(TokenCreateStates.rights_manual)
async def token_create_rights_manual(message: types.Message, state: FSMContext):
    uacl = message.text.strip()
    await state.update_data(uacl=uacl)
    durations = [
        (86400, "1 день"),
        (604800, "7 дней"),
        (0, "Бессрочно"),
        ("custom", "Ввести вручную")
    ]
    buttons = [[types.InlineKeyboardButton(text=f"{d[1]}", callback_data=f"create_token_duration:{d[0]}")] for d in durations]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.reply("Выберите длительность токена:", reply_markup=keyboard)
    await state.set_state(TokenCreateStates.choose_duration)

@dp.callback_query(lambda c: c.data.startswith("create_token_duration:"))
async def token_create_choose_duration(callback_query: types.CallbackQuery, state: FSMContext):
    duration = callback_query.data.split(":", 1)[1]
    if duration == "custom":
        await callback_query.message.edit_text("Введите длительность токена в секундах:")
        await state.set_state(TokenCreateStates.duration_manual)
        return
    await state.update_data(duration=int(duration))
    await create_token_api(callback_query.message, state)

@dp.message(TokenCreateStates.duration_manual)
async def token_create_duration_manual(message: types.Message, state: FSMContext):
    try:
        duration = int(message.text.strip())
        await state.update_data(duration=duration)
        await create_token_api(message, state)
    except Exception:
        await message.reply("Некорректная длительность. Введите число в секундах:")

# --- Функция для преобразования прав доступа ---
def parse_uacl(uacl: str) -> int:
    if uacl.lower() in ("0xffffffff", "-1"):
        return -1
    return int(uacl, 0)

# --- Исправленный create_token_api ---
async def create_token_api(message, state):
    data = await state.get_data()
    master_token = data.get("master_token")
    uacl = data.get("uacl", "0xFFFFFFFF")
    duration = data.get("duration", 0)
    username = data.get("username")
    use_tor = data.get("use_tor", True)
    fl_value = parse_uacl(uacl)
    logger.info(f"[create_token_api] Старт создания токена через API: master_token={master_token[:8]}..., uacl={uacl}, fl={fl_value}, duration={duration}, username={username}, use_tor={use_tor}")
    try:
        wialon_api_url = get_env_variable("WIALON_API_URL", "https://hst-api.wialon.com/wialon/ajax.html")
        # 1. Логин через token/login
        login_params = {
            "svc": "token/login",
            "params": json.dumps({"token": master_token, "fl": 7})
        }
        logger.info(f"[create_token_api] login_params: {login_params}")
        login_result = await make_api_request(wialon_api_url, login_params, use_tor=use_tor)
        logger.info(f"[create_token_api] login_result: {login_result}")
        if "error" in login_result:
            await message.reply(f"Ошибка авторизации: {login_result.get('error')} {login_result.get('reason', '')}")
            logger.error(f"[create_token_api] Ошибка авторизации: {login_result}")
            await state.clear()
            return
        session_id = login_result.get("eid")
        user_id = login_result.get("user", {}).get("id")
        if not session_id or not user_id:
            await message.reply("❌ Не удалось получить ID сессии или пользователя")
            logger.error(f"[create_token_api] Нет session_id или user_id: {login_result}")
            await state.clear()
            return
        # 2. Создание токена через token/update
        params = {
            "callMode": "create",
            "userId": int(user_id),
            "h": "TOKEN",
            "app": "Wialon Hosting Custom Token",
            "at": 0,
            "dur": int(duration),
            "fl": fl_value,
            "p": "{}",
            "items": []
        }
        logger.info(f"[create_token_api] create_params: {params}")
        create_params = {
            "svc": "token/update",
            "params": json.dumps(params),
            "sid": session_id
        }
        logger.info(f"[create_token_api] create_params (final): {create_params}")
        create_result = await make_api_request(wialon_api_url, create_params, use_tor=use_tor)
        logger.info(f"[create_token_api] create_result: {create_result}")
        if "error" in create_result:
            await message.reply(f"❌ Ошибка создания токена: {create_result.get('reason', create_result.get('error'))}")
            logger.error(f"[create_token_api] Ошибка создания токена: {create_result}")
            await state.clear()
            return
        new_token = create_result.get("h")
        if not new_token:
            await message.reply("❌ Не удалось создать токен")
            logger.error(f"[create_token_api] Не удалось получить новый токен из ответа: {create_result}")
            await state.clear()
            return
        # Сохраняем новый токен в базу, привязываем к логину/мастер-токену
        async with AsyncSessionLocal() as session:
            account = await session.scalar(select(WialonAccount).where(WialonAccount.username == username))
            from app.db_utils import add_token
            await add_token(session, account.id, new_token, parent_token=master_token)
        await state.update_data(last_created_token=new_token)
        await message.reply(
            f"✅ Токен успешно создан: <code>{new_token}</code>\nПроверьте его через /check_token",
            parse_mode="HTML"
        )
        logger.info(f"[create_token_api] Токен успешно создан: {new_token}")
    except Exception as e:
        logger.error(f"[create_token_api] Ошибка при создании токена: {e}")
        await message.reply(f"❌ Ошибка при создании токена: {e}")
    await state.clear()

@dp.callback_query(lambda c: c.data == "check_token_by_value")
async def check_token_by_value(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    token = data.get("last_created_token")
    if not token:
        await callback_query.message.edit_text("❌ Токен не найден в состоянии. Попробуйте создать токен заново или воспользуйтесь /check_token.")
        return
    use_tor = data.get("use_tor", True)
    logger.info(f"[check_token_by_value] Проверка токена: {token[:8]}..., use_tor={use_tor}")
    try:
        wialon_api_url = get_env_variable("WIALON_API_URL", "https://hst-api.wialon.com/wialon/ajax.html")
        params = {
            "svc": "token/login",
            "params": json.dumps({"token": token, "fl": 1})
        }
        logger.info(f"[check_token_by_value] params: {params}")
        result = await make_api_request(wialon_api_url, params, use_tor=use_tor)
        logger.info(f"[check_token_by_value] result: {result}")
        if "error" in result:
            await callback_query.message.edit_text(f"❌ Ошибка авторизации: {result.get('error')} {result.get('reason', '')}")
            logger.error(f"[check_token_by_value] Ошибка: {result}")
            return
        user = result.get("user", {})
        expire_time = result.get("tm")
        expire_str = (
            datetime.datetime.fromtimestamp(expire_time).strftime('%Y-%m-%d %H:%M:%S')
            if expire_time else "N/A"
        )
        fl = result.get("fl", "N/A")
        objects_count = len(result.get("items", [])) if "items" in result else "N/A"
        msg = (
            f"✅ <b>Токен валиден!</b>\n"
            f"👤 <b>User:</b> {user.get('nm', 'N/A')} (ID: {user.get('id', 'N/A')})\n"
            f"⏳ <b>Действует до:</b> {expire_str}\n"
            f"🔑 <b>Права (fl):</b> {fl}\n"
            f"📦 <b>Объектов доступно:</b> {objects_count}"
        )
        await callback_query.message.edit_text(msg, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"[check_token_by_value] Ошибка при проверке токена: {e}")
        await callback_query.message.edit_text(f"❌ Ошибка при проверке токена: {str(e)}")
    await state.clear()

@dp.message(Command(commands=['check_token']))
async def check_token_command(message: types.Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        tokens = await session.execute(select(Token).options(selectinload(Token.account)))
        tokens = tokens.scalars().all()
        if not tokens:
            await message.reply("Нет сохранённых токенов. Введите токен для проверки:")
            await state.set_state(GetTokenStates.waiting_for_token_input)
            return
        # Клавиатура выбора режима подключения
        buttons = [
            [types.InlineKeyboardButton(text="🧅 Через Tor", callback_data="check_token_conn:tor")],
            [types.InlineKeyboardButton(text="🚀 Напрямую", callback_data="check_token_conn:direct")]
        ]
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.reply("Выберите режим подключения для проверки токена:", reply_markup=keyboard)
        await state.set_state(GetTokenStates.waiting_for_token_input)

@dp.callback_query(lambda c: c.data.startswith("check_token_conn:"))
async def check_token_choose_connection(callback_query: types.CallbackQuery, state: FSMContext):
    conn_type = callback_query.data.split(":", 1)[1]
    use_tor = conn_type == "tor"
    await state.update_data(use_tor=use_tor)
    # Далее — выбор токена
    async with AsyncSessionLocal() as session:
        tokens = await session.execute(select(Token).options(selectinload(Token.account)))
        tokens = tokens.scalars().all()
        buttons = [
            [types.InlineKeyboardButton(
                text=f"{t.token[:6]}...{t.token[-4:]} ({t.account.username if t.account else ''})",
                callback_data=f"check_token:{t.id}")]
            for t in tokens
        ]
        buttons.append([types.InlineKeyboardButton(text="✏️ Ввести токен вручную", callback_data="check_token_manual")])
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback_query.message.edit_text("Выберите токен для проверки:", reply_markup=keyboard)
        await state.set_state(GetTokenStates.waiting_for_token_input)

@dp.callback_query(lambda c: c.data == "check_token_manual")
async def check_token_manual_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.message.edit_text("Введите токен для проверки:")
    await state.set_state(GetTokenStates.waiting_for_token_input)

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
                "created_via": "saved_credentials",
                "token_metadata": {
                    "username": credentials['username'],
                    "password": credentials['password'],
                    "host": wialon_url
                }
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
        expire_str = (
            datetime.datetime.fromtimestamp(expire_time).strftime('%Y-%m-%d %H:%M:%S')
            if expire_time else "N/A"
        )
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

@dp.message(Command(commands=['token_create_custom']))
async def token_create_custom_command(message: types.Message, state: FSMContext):
    """Начать процесс создания кастомного токена с выбором прав и срока действия."""
    if not is_user_allowed(message.from_user.id):
        await message.reply("Доступ запрещен. Обратитесь к администратору.")
        return

    async with AsyncSessionLocal() as session:
        user_tokens = await get_all_user_tokens(session)

    buttons = []
    # Добавляем кнопку для ручного ввода
    buttons.append([
        types.InlineKeyboardButton(
            text="✏️ Ввести токен вручную", 
            callback_data="api_create_token_manual"
        )
    ])

    if user_tokens:
        for i, token_data in enumerate(user_tokens[:5]):
            token = token_data["token"]
            user_info = f" ({token_data['user_name']})" if token_data.get('user_name') else ""
            buttons.insert(i, [
                types.InlineKeyboardButton(
                    text=f"🔑 Токен #{i+1}{user_info}", 
                    callback_data=f"api_create_token:{i}"
                )
            ])
        message_text = "Выберите токен, на основе которого будет создан новый токен (кастомные права):"
    else:
        message_text = "У вас нет сохраненных токенов. Введите токен для создания нового (кастомные права):"

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.reply(
        message_text,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )
    await state.set_state(CustomTokenStates.waiting_for_source_token)

@dp.callback_query(lambda c: c.data == "api_create_token_manual")
async def process_api_create_token_manual(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.edit_text(
        "Введите токен вручную:",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(CustomTokenStates.waiting_for_source_token)

@dp.message(CustomTokenStates.waiting_for_source_token)
async def process_manual_source_token(message: types.Message, state: FSMContext):
    token = message.text.strip()
    await state.update_data(source_token=token)
    await message.reply("Введите маску прав доступа (uacl) для нового токена (например, 0xFFFFFFFF):", parse_mode=ParseMode.HTML)
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
    
    # Создаем клавиатуру для выбора режима подключения
    buttons = [
        [types.InlineKeyboardButton(text="🌐 Напрямую", callback_data="api_token_action:no")],
        [types.InlineKeyboardButton(text="🧅 Через Tor", callback_data="api_token_action:yes")]
    ]
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.reply(
        "Выберите режим подключения:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )
    await state.set_state(CustomTokenStates.waiting_for_connection_mode)

@dp.callback_query(lambda c: c.data.startswith("api_token_action:"))
async def process_api_token_action(callback_query: types.CallbackQuery, state: FSMContext):
    """Создание/обновление токена через API с поддержкой кастомных прав и срока действия."""
    try:
        await callback_query.answer()
        use_tor = callback_query.data.split(":")[1] == "yes"
        
        data = await state.get_data()
        source_token = data.get("source_token")
        uacl = data.get("uacl", "0xFFFFFFFF")  # Права доступа по умолчанию
        duration = data.get("duration", 0)  # Длительность по умолчанию (бессрочно)
        
        if not source_token:
            await callback_query.message.edit_text("❌ Исходный токен не найден")
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
        
        status_message = await callback_query.message.edit_text(
            f"🔄 Создаем токен с кастомными правами {'через Tor' if use_tor else 'напрямую'}..."
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
        
        # 2. Создание токена через token/update
        params = {
            "callMode": "create",
            "userId": int(user_id),
            "h": "TOKEN",
            "app": "Wialon Hosting Custom Token",
            "at": 0,
            "dur": int(duration),
            "fl": int(uacl, 0),  # Преобразуем строку с hex в число
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
            await status_message.edit_text(f"❌ Ошибка создания токена: {create_result.get('reason', create_result.get('error'))}")
            return
             
        # Получаем новый токен из результата
        new_token = create_result.get("h")
        if not new_token:
            await status_message.edit_text("❌ Не удалось создать токен")
            return
             
        # Сохраняем новый токен как дочерний от исходного
        async with AsyncSessionLocal() as session:
            await add_token(session, callback_query.from_user.id, new_token, parent_token=source_token)
        
        # Сохраняем информацию о токене
        token_info = {
            "user_name": login_result.get("au"),
            "expire_time": int(time.time()) + int(duration) if int(duration) > 0 else None,
            "created_at": int(time.time()),
            "created_via": "api_custom",
            "uacl": uacl,
            "duration": duration,
            "token_metadata": {
                "username": login_result.get("au"),
                "password": credentials['password'],
                "host": wialon_url
            }
        }
        async with AsyncSessionLocal() as session:
            await update_token_info(session, callback_query.from_user.id, new_token, token_info)
        
        # Форматируем сообщение об успехе
        expire_info = (
            f"\n⏳ Срок действия: {datetime.datetime.fromtimestamp(token_info['expire_time']).strftime('%Y-%m-%d %H:%M:%S')}"
            if token_info['expire_time']
            else "\n⏳ Срок действия: бессрочно"
        )
        
        await status_message.edit_text(
            f"✅ Токен успешно создан с кастомными правами!\n\n"
            f"🔑 <code>{new_token}</code>\n"
            f"🔒 Права доступа: {uacl}"
            f"{expire_info}",
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logger.error(f"Error in API token operation: {e}")
        await callback_query.message.edit_text(f"❌ Произошла ошибка: {str(e)}")
    finally:
        await state.clear()

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
    Обработчик команды /get_token: показывает сохраненные учетные данные Wialon или запускает процесс получения нового токена
    """
    async with AsyncSessionLocal() as session:
        # Получаем все WialonAccount из базы
        accounts = await session.execute(select(WialonAccount))
        accounts = accounts.scalars().all()
        
        if accounts:
            # Создаем клавиатуру с сохраненными логинами
            buttons = []
            for acc in accounts:
                buttons.append([
                    types.InlineKeyboardButton(
                        text=f"👤 {acc.username}",
                        callback_data=f"use_saved_account:{acc.username}"
                    )
                ])
            # Добавляем кнопку для ввода новых данных
            buttons.append([
                types.InlineKeyboardButton(
                    text="✏️ Ввести новые учетные данные",
                    callback_data="input_new_credentials"
                )
            ])
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=buttons)
            await message.reply(
                "Выберите сохранённый логин Wialon или введите новый:",
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML
            )
            return
    # Если нет сохранённых логинов - запускаем FSM для получения логина/пароля
    await message.reply("Сохранённые учетные данные не найдены. Давайте создадим новые!\n\nВведите логин Wialon:")
    await state.set_state(GetTokenStates.manual_input_username)

@dp.callback_query(lambda c: c.data.startswith("use_saved_account:"))
async def process_saved_account_choice(callback_query: types.CallbackQuery, state: FSMContext):
    username = callback_query.data.split(":", 1)[1]
    logger.debug(f"[process_saved_account_choice] username={username}")
    async with AsyncSessionLocal() as session:
        account = await session.scalar(select(WialonAccount).where(WialonAccount.username == username))
        if not account:
            await callback_query.message.edit_text("❌ Ошибка: логин не найден в базе.")
            logger.debug(f"[process_saved_account_choice] account not found for username={username}")
            return
        password = decrypt_password(account.encrypted_password)
        logger.debug(f"[process_saved_account_choice] password={'***' if password else None}")
        # Ищем мастер-токены для этого аккаунта
        tokens = await session.execute(select(Token).where(Token.account_id == account.id, Token.token_type == TokenType.MASTER))
        master_tokens = tokens.scalars().all()
        logger.debug(f"[process_saved_account_choice] found master_tokens={master_tokens}")
        if not master_tokens:
            await callback_query.message.edit_text(
                f"❌ Для логина <b>{username}</b> не найдено ни одного мастер-токена.\n\nСоздайте новый через /token_create.",
                parse_mode="HTML"
            )
            logger.debug(f"[process_saved_account_choice] no master tokens for username={username}")
            return
        if len(master_tokens) == 1:
            # Сразу используем единственный токен
            token = master_tokens[0].token
            await state.update_data(username=username, password=password, master_token=token)
            await callback_query.message.edit_text(
                f"Найден мастер-токен для <b>{username}</b>:\n<code>{token}</code>\n\nВыберите режим подключения:",
                reply_markup=get_connection_choice_keyboard(),
                parse_mode="HTML"
            )
            logger.debug(f"[process_saved_account_choice] auto-selected master_token={token}")
        else:
            # Предлагаем выбор токена и кнопку для создания нового мастер-токена
            keyboard = types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(
                        text=f"🔑 {t.token[:8]}...{t.token[-4:]}",
                        callback_data=f"choose_master_token:{t.id}")]
                    for t in master_tokens
                ] + [
                    [types.InlineKeyboardButton(
                        text="➕ Добавить новый мастер-токен",
                        callback_data="add_new_master_token"
                    )]
                ]
            )
            await callback_query.message.edit_text(
                f"Выберите мастер-токен для <b>{username}</b>:",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            await state.update_data(username=username, password=password)
            logger.debug(f"[process_saved_account_choice] presented token choices for username={username}")

@dp.callback_query(lambda c: c.data.startswith("choose_master_token:"))
async def process_choose_master_token(callback_query: types.CallbackQuery, state: FSMContext):
    token_id = int(callback_query.data.split(":", 1)[1])
    data = await state.get_data()
    username = data.get("username")
    password = data.get("password")
    async with AsyncSessionLocal() as session:
        token_obj = await session.get(Token, token_id)
        if not token_obj:
            await callback_query.message.edit_text(
                "❌ Ошибка: токен не найден в базе.")
            logger.debug(f"[process_choose_master_token] token_id={token_id} not found")
            return
        token = token_obj.token
        await state.update_data(master_token=token)
        await callback_query.message.edit_text(
            f"Выбран мастер-токен для <b>{username}</b>:\n<code>{token}</code>\n\nВыберите режим подключения:",
            reply_markup=get_connection_choice_keyboard(),
            parse_mode="HTML"
        )
        logger.debug(f"[process_choose_master_token] selected master_token={token} for username={username}")

@dp.callback_query(lambda c: c.data == "add_new_master_token")
async def process_add_new_master_token(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    username = data.get("username")
    password = data.get("password")
    logger.debug(f"[process_add_new_master_token] username={username}")
    if not username or not password:
        await callback_query.message.edit_text("❌ Не удалось найти логин или пароль для создания мастер-токена.")
        logger.debug(f"[process_add_new_master_token] missing username or password")
        return
    # Не показываем список токенов, сразу предлагаем выбор подключения
    keyboard = get_connection_choice_keyboard()
    await callback_query.message.edit_text(
        "Выберите способ подключения для получения нового мастер-токена:",
        reply_markup=keyboard
    )
    await state.set_state(GetTokenStates.connection_mode_choice)

# Обработчик выбора типа подключения для нового мастер-токена
@dp.callback_query(GetTokenStates.connection_mode_choice)
async def process_add_new_master_token_connection_mode(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    data = await state.get_data()
    username = data.get("username")
    password = data.get("password")
    if not username or not password:
        await callback_query.message.edit_text("❌ Ошибка: отсутствуют учетные данные")
        await state.clear()
        return
    use_tor = callback_query.data.split(":")[1] == "yes"
    await state.update_data(use_tor=use_tor)
    status_message = await callback_query.message.edit_text(
        f"🔄 Получаем мастер-токен для <b>{username}</b> {'через Tor' if use_tor else 'напрямую'}...",
        parse_mode=ParseMode.HTML
    )
    try:
        from app.scraper import wialon_login_and_get_url
        wialon_url = "https://hosting.wialon.com/login.html?access_type=-1&duration=0"
        login_result = await wialon_login_and_get_url(username, password, wialon_url, use_tor=use_tor)
        logger.debug(f"[process_add_new_master_token_connection_mode] wialon_login_and_get_url result={login_result}")
        if "error" in login_result or not login_result.get("token") or not isinstance(login_result["token"], str) or len(login_result["token"]) < 20 or "Error" in login_result["token"]:
            error_msg = login_result.get("error") or login_result.get("token") or "Не удалось получить токен."
            screenshot = login_result.get("screenshot")
            msg = f"❌ Ошибка входа в Wialon: {error_msg}"
            if screenshot:
                msg += f"\nСкриншот: {screenshot}"
            await status_message.edit_text(msg)
            logger.error(f"[process_add_new_master_token_connection_mode] невалидный токен: {error_msg}")
            return
        master_token = login_result["token"]
        async with AsyncSessionLocal() as session:
            from app.db_utils import save_master_token
            await save_master_token(
                session,
                token=master_token,
                username=username,
                password=password
            )
        await status_message.edit_text(
            f"✅ Новый мастер-токен успешно получен и сохранён для <b>{username}</b>:\n<code>{master_token}</code>",
            parse_mode="HTML"
        )
        logger.debug(f"[process_add_new_master_token_connection_mode] new master_token saved for username={username}")
    except Exception as e:
        logger.exception(f"[process_add_new_master_token_connection_mode] error: {e}")
        await status_message.edit_text(f"❌ Ошибка при создании мастер-токена: {e}")
    finally:
        await state.clear()

@dp.callback_query(lambda c: c.data == "input_new_credentials")
async def process_new_credentials_input(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик ввода новых учетных данных"""
    await callback_query.answer()
    await callback_query.message.edit_text("Введите логин Wialon:")
    await state.set_state(GetTokenStates.manual_input_username)

@dp.message(GetTokenStates.manual_input_username)
async def get_token_username(message: types.Message, state: FSMContext):
    await state.update_data(username=message.text.strip())
    await message.reply("Введите пароль Wialon:")
    await state.set_state(GetTokenStates.manual_input_password)

@dp.message(GetTokenStates.manual_input_password)
async def get_token_password(message: types.Message, state: FSMContext):
    password = message.text.strip()
    await state.update_data(password=password)
    
    keyboard = get_connection_choice_keyboard()
    await message.reply("Выберите способ подключения:", reply_markup=keyboard)
    await state.set_state(GetTokenStates.connection_mode_choice)

@dp.callback_query(GetTokenStates.connection_mode_choice)
async def get_token_connection_mode(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик выбора режима подключения для получения токена."""
    await callback_query.answer()
    
    # Получаем данные из состояния
    data = await state.get_data()
    username = data.get('username')
    password = data.get('password')
    logger.debug(f"[get_token_connection_mode] username={username}, password={'***' if password else None}")
    
    if not username or not password:
        await callback_query.message.edit_text("❌ Ошибка: отсутствуют учетные данные")
        await state.clear()
        return
    
    # Определяем, использовать ли Tor
    use_tor = callback_query.data.split(":")[1] == "yes"
    await state.update_data(use_tor=use_tor)
    
    # Отображаем сообщение о процессе
    status_message = await callback_query.message.edit_text(
        f"🔄 Получаем токен для <b>{username}</b> {'через Tor' if use_tor else 'напрямую'}...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        # Получаем URL Wialon из переменных окружения
        wialon_url = get_env_variable("WIALON_BASE_URL")
        
        # Запускаем процесс авторизации
        result = await wialon_login_and_get_url(
            username, 
            password, 
            wialon_url,
            use_tor=use_tor
        )
        
        if not result or not result.get('token') or not isinstance(result["token"], str) or len(result["token"]) < 20 or "Error" in result["token"]:
            error_msg = result.get("error") or result.get("token") or "Не удалось получить токен."
            screenshot = result.get("screenshot")
            msg = f"❌ Ошибка входа в Wialon: {error_msg}"
            if screenshot:
                msg += f"\nСкриншот: {screenshot}"
            await status_message.edit_text(msg)
            logger.error(f"[get_token_connection_mode] невалидный токен: {error_msg}")
            return
        
        token = result['token']
        
        # Сохраняем только мастер-токен (child-токены только через API!)
        async with AsyncSessionLocal() as session:
            await save_token_chain(
                session,
                username=username,  # логин Wialon
                password=password,  # пароль Wialon
                master_token=token,  # это мастер-токен!
                creation_method="LOGIN",
                token_metadata={
                    'connection_type': 'tor' if use_tor else 'direct',
                    'user_agent': result.get('user', {}).get('au'),
                    'company': result.get('user', {}).get('crt')
                }
            )
        
        # Отправляем сообщение об успехе
        await status_message.edit_text(
            f"✅ Токен успешно получен и сохранён!\n\n"
            f"🔑 Токен: <code>{token}</code>",
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logger.error(f"Ошибка при получении токена: {str(e)}")
        await status_message.edit_text(
            f"❌ Произошла ошибка: {str(e)}",
            parse_mode=ParseMode.HTML
        )
    finally:
        await state.clear()

async def process_token_duration(message: types.Message, state: FSMContext):
    try:
        duration = int(message.text)
        if duration <= 0:
            await message.reply("❌ Длительность должна быть положительным числом!")
            return

        async with state.proxy() as data:
            metadata = data.get('metadata', {})
            metadata['duration'] = duration
            data['metadata'] = metadata

        await state.set_state(TokenStates.waiting_for_uacl)
        await message.reply("✅ Отлично! Теперь введите UACL (права доступа) для токена:")
    except Exception as e:
        await message.reply(f"❌ Ошибка при обработке длительности: {str(e)}")

@dp.callback_query(lambda c: c.data.startswith("check_token:"))
async def check_token_choose(callback_query: types.CallbackQuery, state: FSMContext):
    token_id = int(callback_query.data.split(":", 1)[1])
    use_tor = (await state.get_data()).get("use_tor", True)
    async with AsyncSessionLocal() as session:
        token_obj = await session.get(Token, token_id)
        # Получаем связи
        account = None
        if token_obj.account_id:
            account = await session.get(WialonAccount, token_obj.account_id)
        parent_token = None
        if token_obj.parent_token_id:
            parent_token = await session.get(Token, token_obj.parent_token_id)
    token = token_obj.token
    logger.info(f"[check_token] Проверка токена: {token[:8]}..., use_tor={use_tor}")
    try:
        wialon_api_url = get_env_variable("WIALON_API_URL", "https://hst-api.wialon.com/wialon/ajax.html")
        params = {
            "svc": "token/login",
            "params": json.dumps({"token": token, "fl": 1})
        }
        logger.info(f"[check_token] params: {params}")
        result = await make_api_request(wialon_api_url, params, use_tor=use_tor)
        logger.info(f"[check_token] result: {result}")
        if "error" in result:
            await callback_query.message.edit_text(f"❌ Ошибка авторизации: {result.get('error')} {result.get('reason', '')}")
            logger.error(f"[check_token] Ошибка: {result}")
            return
        user = result.get("user", {})
        expire_time = result.get("tm")
        expire_str = (
            datetime.datetime.fromtimestamp(expire_time).strftime('%Y-%m-%d %H:%M:%S')
            if expire_time else "N/A"
        )
        creation_method = getattr(token_obj, 'creation_method', 'N/A')
        created_at = getattr(token_obj, 'created_at', None)
        created_str = (
            datetime.datetime.fromtimestamp(created_at.timestamp()).strftime('%Y-%m-%d %H:%M:%S')
            if created_at else "N/A"
        )
        fl = result.get("fl", "N/A")
        objects_count = len(result.get("items", [])) if "items" in result else "N/A"
        msg = (
            f"✅ <b>Токен валиден!</b>\n"
            f"👤 <b>Логин:</b> {account.username if account else 'N/A'}\n"
            f"🔑 <b>Тип:</b> {token_obj.token_type.value}\n"
            f"🕒 <b>Создан:</b> {created_str}\n"
            f"⚙️ <b>Способ создания:</b> {creation_method}\n"
            f"⏳ <b>Действует до:</b> {expire_str}\n"
            f"🔑 <b>Права (fl):</b> {fl}\n"
            f"📦 <b>Объектов доступно:</b> {objects_count}"
        )
        if parent_token:
            msg += f"\n🔗 <b>Мастер-токен:</b> {parent_token.token[:8]}...{parent_token.token[-4:]}"
        await callback_query.message.edit_text(msg, parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"[check_token] Ошибка при проверке токена: {e}")
        await callback_query.message.edit_text(f"❌ Ошибка при проверке токена: {str(e)}")
    await state.clear()

@dp.message(Command(commands=['my_tokens']))
async def my_tokens_command(message: types.Message):
    async with AsyncSessionLocal() as session:
        tokens = await session.execute(select(Token).order_by(Token.created_at.desc()))
        tokens = tokens.scalars().all()
        if not tokens:
            await message.reply("У вас нет сохранённых токенов.")
            return
        lines = []
        for t in tokens:
            account = None
            if t.account_id:
                account = await session.get(WialonAccount, t.account_id)
            parent_token = None
            if t.parent_token_id:
                parent_token = await session.get(Token, t.parent_token_id)
            created_str = (
                datetime.datetime.fromtimestamp(t.created_at.timestamp()).strftime('%Y-%m-%d %H:%M:%S')
                if t.created_at else "N/A"
            )
            line = (
                f"👤 <b>Логин:</b> {account.username if account else 'N/A'}\n"
                f"🔑 <b>Тип:</b> {t.token_type.value}\n"
                f"🕒 <b>Создан:</b> {created_str}\n"
                f"⚙️ <b>Способ создания:</b> {t.creation_method}\n"
                f"<code>{t.token[:8]}...{t.token[-4:]}</code>"
            )
            if parent_token:
                line += f"\n🔗 <b>Мастер-токен:</b> {parent_token.token[:8]}...{parent_token.token[-4:]}"
            lines.append(line)
        text = "\n\n".join(lines)
        await message.reply(f"Ваши токены:\n\n{text}", parse_mode=ParseMode.HTML)
