from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from app.db_utils import add_token_history, get_all_user_tokens, save_token_chain, get_all_logins, get_password_by_login
from app.database import AsyncSessionLocal
from app.wialon_api import create_token, update_token, wialon_login
from app.bot_utils import get_tor_choice_keyboard
import json
import logging
import datetime
from fastapi import Form, HTTPException, APIRouter

router = APIRouter()
logger = logging.getLogger(__name__)

class TokenStates(StatesGroup):
    choosing_input_method = State()
    choosing_login = State()
    choosing_master_token = State()
    waiting_for_master_token = State()
    waiting_for_access_rights = State()
    waiting_for_duration = State()
    waiting_for_label = State()
    waiting_for_token_to_update = State()

@router.message(Command(commands=["token_create"]))
async def token_create_handler(message: types.Message, state: FSMContext):
    """Начать процесс создания токена через API."""
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="💾 Использовать сохраненные учетные данные",
                    callback_data="token_create_saved"
                )
            ],
            [
                types.InlineKeyboardButton(
                    text="✏️ Ввести токен вручную",
                    callback_data="token_create_manual"
                )
            ]
        ]
    )
    
    await message.reply(
        "Выберите способ создания токена:",
        reply_markup=keyboard
    )
    await state.set_state(TokenStates.choosing_input_method)

@router.callback_query(lambda c: c.data == "token_create_saved")
async def process_token_create_saved(callback_query: types.CallbackQuery, state: FSMContext):
    logger.debug("[process_token_create_saved] called")
    await callback_query.answer()
    
    async with AsyncSessionLocal() as session:
        logins = await get_all_logins(session)
        logger.debug(f"[process_token_create_saved] logins={logins}")
    
    if not logins:
        await callback_query.message.edit_text(
            "❌ Нет сохраненных учетных данных. Используйте ручной ввод токена."
        )
        logger.debug("[process_token_create_saved] No logins found")
        return
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text=login, callback_data=f"token_create_login:{login}")]
        for login in logins
    ])
    
    await callback_query.message.edit_text(
        "Выберите учетную запись:",
        reply_markup=keyboard
    )
    logger.debug(f"[process_token_create_saved] presented logins: {logins}")
    await state.set_state(TokenStates.choosing_login)

@router.callback_query(lambda c: c.data.startswith("token_create_login:"))
async def process_token_create_login(callback_query: types.CallbackQuery, state: FSMContext):
    """Показать мастер-токены для выбранного логина."""
    await callback_query.answer()
    
    login = callback_query.data.split(":")[1]
    logger.debug(f"[process_token_create_login] login={login}")
    async with AsyncSessionLocal() as session:
        # Получаем пароль для логина
        password = await get_password_by_login(session, login)
        logger.debug(f"[process_token_create_login] password={'***' if password else None}")
        if not password:
            await callback_query.message.edit_text(
                "❌ Не удалось получить пароль для этой учетной записи."
            )
            return
            
        # Пробуем залогиниться
        login_result = wialon_login(login, password)
        logger.debug(f"[process_token_create_login] login_result={login_result}")
        if "error" in login_result:
            await callback_query.message.edit_text(
                f"❌ Ошибка входа в Wialon: {login_result.get('error')}"
            )
            return
            
        # Получаем все токены для этого логина
        tokens = await get_all_user_tokens(session)
        logger.debug(f"[process_token_create_login] all tokens={tokens}")
        user_tokens = [t for t in tokens if t.get("user_name") == login and t.get("type") == "master"]
        logger.debug(f"[process_token_create_login] user_tokens={user_tokens}")
        if not user_tokens:
            await callback_query.message.edit_text(
                "❌ Для этой учетной записи нет сохраненных мастер-токенов."
            )
            return
            
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(
                text=f"🔑 {t['token'][:8]}...{t['token'][-4:]}",
                callback_data=f"token_create_select:{t['token']}"
            )]
            for t in user_tokens
        ])
        
        await callback_query.message.edit_text(
            f"Выберите мастер-токен для учетной записи {login}:",
            reply_markup=keyboard
        )
        await state.set_state(TokenStates.choosing_master_token)

@router.callback_query(lambda c: c.data.startswith("token_create_select:"))
async def process_token_create_select(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработка выбора мастер-токена."""
    await callback_query.answer()
    
    token = callback_query.data.split(":")[1]
    await state.update_data(master_token=token)
    
    access_flags_table = (
        "\n<b>Доступные флаги прав (uacl):</b>\n"
        "<pre>"
        "0x100   — online tracking\n"
        "0x200   — view access to most data\n"
        "0x400   — modification of non-sensitive data\n"
        "0x800   — modification of sensitive data\n"
        "0x1000  — modification of critical data (incl. messages deletion)\n"
        "0x2000  — communication\n"
        "-1      — unlimited operation as authorized user (manage user tokens)\n"
        "</pre>\n"
        "Для полного доступа используйте <code>0xFFFFFFFF</code> (рекомендуется).\n\n"
        "Введите права доступа (uacl) для нового токена (например, 0xFFFFFFFF, 0x1, 0x2000):"
    )
    await callback_query.message.edit_text(access_flags_table, parse_mode="HTML")
    await state.set_state(TokenStates.waiting_for_access_rights)

@router.callback_query(lambda c: c.data == "token_create_manual")
async def process_token_create_manual(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработка ручного ввода токена."""
    await callback_query.answer()
    
    await callback_query.message.edit_text(
        "Введите мастер-токен:",
        parse_mode="HTML"
    )
    await state.set_state(TokenStates.waiting_for_master_token)

@router.message(TokenStates.waiting_for_master_token)
async def process_master_token_input(message: types.Message, state: FSMContext):
    """Обработка введенного вручную мастер-токена."""
    token = message.text.strip()
    await state.update_data(master_token=token)
    
    access_flags_table = (
        "\n<b>Доступные флаги прав (uacl):</b>\n"
        "<pre>"
        "0x100   — online tracking\n"
        "0x200   — view access to most data\n"
        "0x400   — modification of non-sensitive data\n"
        "0x800   — modification of sensitive data\n"
        "0x1000  — modification of critical data (incl. messages deletion)\n"
        "0x2000  — communication\n"
        "-1      — unlimited operation as authorized user (manage user tokens)\n"
        "</pre>\n"
        "Для полного доступа используйте <code>0xFFFFFFFF</code> (рекомендуется).\n\n"
        "Введите права доступа (uacl) для нового токена (например, 0xFFFFFFFF, 0x1, 0x2000):"
    )
    await message.reply(access_flags_table, parse_mode="HTML")
    await state.set_state(TokenStates.waiting_for_access_rights)

@router.message(TokenStates.waiting_for_access_rights)
async def process_access_rights(message: types.Message, state: FSMContext):
    uacl = message.text.strip()
    await state.update_data(access_rights=uacl)
    await message.reply("Введите длительность токена в секундах (например, 86400 для 1 дня). Если оставить поле пустым, будет использовано максимальное время (10 лет):")
    await state.set_state(TokenStates.waiting_for_duration)

@router.message(TokenStates.waiting_for_duration)
async def process_duration(message: types.Message, state: FSMContext):
    try:
        duration = int(message.text.strip()) if message.text.strip() else 315360000
        if duration <= 0:
            raise ValueError
    except ValueError:
        await message.reply("Некорректная длительность. Введите положительное целое число (секунды):")
        return
    
    await state.update_data(duration=duration)
    await message.reply("Введите метку (label) для токена (или отправьте '-' чтобы пропустить):")
    await state.set_state(TokenStates.waiting_for_label)

@router.message(TokenStates.waiting_for_label)
async def process_label(message: types.Message, state: FSMContext):
    label = message.text.strip()
    if label == "-":
        label = None
    
    await state.update_data(label=label)
    data = await state.get_data()
    
    try:
        result = await create_token(
            data["master_token"], 
            data["access_rights"], 
            data["duration"], 
            label
        )
        new_token = result.get("token")
        
        # Сохраняем токен в базу данных
        async with AsyncSessionLocal() as session:
            # Сохраняем историю
            await add_token_history(
                session, 
                "API",  # для API-запросов используем специальный идентификатор
                new_token,
                "create",
                {"label": label}
            )
            
            # Сохраняем токен
            success = await save_token_chain(
                session,
                None,  # username не требуется для дочернего токена
                None,  # password не требуется для дочернего токена
                data["master_token"],
                new_token,
                creation_method="API",
                access_rights=int(data["access_rights"], 0) if data["access_rights"].startswith("0x") else int(data["access_rights"]),
                duration=data["duration"],
                expires_at=datetime.datetime.utcnow() + datetime.timedelta(seconds=data["duration"]) if data["duration"] else None
            )
            
            if success:
                await message.reply(
                    f"✅ Токен успешно создан и сохранен!\n\n"
                    f"🔑 <code>{new_token}</code>\n"
                    f"⏳ Длительность: {data['duration']} сек\n"
                    f"🔒 Права доступа: {data['access_rights']}\n"
                    f"🏷 Метка: {label if label else 'не указана'}",
                    parse_mode="HTML"
                )
            else:
                await message.reply(
                    f"⚠️ Токен создан, но возникла ошибка при сохранении:\n"
                    f"<code>{new_token}</code>",
                    parse_mode="HTML"
                )
    except Exception as e:
        logger.error(f"Ошибка создания токена: {e}")
        await message.reply(f"❌ Ошибка создания токена: {e}")
    finally:
        await state.clear()

@router.message(Command(commands=["token_update"]))
async def token_update_handler(message: types.Message, state: FSMContext):
    """Начать процесс обновления токена."""
    async with AsyncSessionLocal() as session:
        user_tokens = await get_all_user_tokens(session)
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [types.InlineKeyboardButton(
                text="✏️ Ввести токен вручную", 
                callback_data="token_update_manual"
            )]
        ]
    )
    
    if user_tokens:
        for i, token_data in enumerate(user_tokens[:5]):
            token = token_data["token"]
            user_info = f" ({token_data['user_name']})" if "user_name" in token_data else ""
            keyboard.inline_keyboard.insert(i, [
                types.InlineKeyboardButton(
                    text=f"🔑 Токен #{i+1}{user_info}", 
                    callback_data=f"token_update:{i}"
                )
            ])
        message_text = "Выберите токен для обновления:"
    else:
        message_text = "У вас нет сохраненных токенов. Введите токен для обновления:"
    
    await message.reply(message_text, reply_markup=keyboard)
    await state.set_state(TokenStates.waiting_for_token_to_update)

@router.callback_query(lambda c: c.data.startswith("token_update:"))
async def process_token_update_choice(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    index = int(callback_query.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        user_tokens = await get_all_user_tokens(session)
    token = user_tokens[index]["token"]
    await state.update_data(token_to_update=token)
    await callback_query.message.edit_text(
        "Введите новые права доступа (uacl) для токена (например, 0xFFFFFFFF):",
        parse_mode="HTML"
    )
    await state.set_state(TokenStates.waiting_for_access_rights)

@router.message(TokenStates.waiting_for_token_to_update)
async def process_token_to_update(message: types.Message, state: FSMContext):
    token = message.text.strip()
    await state.update_data(token_to_update=token)
    await message.reply("Введите новые права доступа (uacl) для токена (например, 0xFFFFFFFF):")
    await state.set_state(TokenStates.waiting_for_access_rights)

@router.post("/token_create")
async def token_create(
    master_token: str = Form(...),
    access_rights: str = Form(...),
    duration: int = Form(...),
    label: str = Form(None)
):
    try:
        result = await create_token(master_token, access_rights, duration, label)
        new_token = result.get("token")
        
        async with AsyncSessionLocal() as session:
            # Сохраняем историю
            await add_token_history(
                session,
                "API",  # для API-запросов используем специальный идентификатор
                new_token,
                "create",
                {"label": label}
            )
            
            # Сохраняем токен
            success = await save_token_chain(
                session,
                None,  # username не требуется для дочернего токена
                None,  # password не требуется для дочернего токена
                master_token,
                new_token,
                creation_method="API",
                access_rights=int(access_rights, 0) if access_rights.startswith("0x") else int(access_rights),
                duration=duration,
                expires_at=datetime.datetime.utcnow() + datetime.timedelta(seconds=duration) if duration else None
            )
            
            if success:
                return {
                    "status": "success",
                    "token": new_token,
                    "message": "Token created and saved successfully"
                }
            else:
                return {
                    "status": "warning",
                    "token": new_token,
                    "message": "Token created but not saved to database"
                }
                
    except Exception as e:
        logger.error(f"Error creating token: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/token_create_custom")
async def token_create_custom(
    master_token: str = Form(...),
    access_rights: str = Form(...),
    duration: int = Form(...),
    label: str = Form(None),
    custom_data: str = Form(...)
):
    try:
        result = await create_token(master_token, access_rights, duration, label)
        new_token = result.get("token")
        
        async with AsyncSessionLocal() as session:
            # Сохраняем историю с дополнительными данными
            await add_token_history(
                session,
                "API",
                new_token,
                "create",
                {
                    "label": label,
                    "custom_data": json.loads(custom_data)
                }
            )
            
            # Сохраняем токен
            success = await save_token_chain(
                session,
                None,
                None,
                master_token,
                new_token,
                creation_method="API",
                access_rights=int(access_rights, 0) if access_rights.startswith("0x") else int(access_rights),
                duration=duration,
                expires_at=datetime.datetime.utcnow() + datetime.timedelta(seconds=duration) if duration else None,
                custom_data=json.loads(custom_data)
            )
            
            if success:
                return {
                    "status": "success",
                    "token": new_token,
                    "message": "Token created and saved successfully"
                }
            else:
                return {
                    "status": "warning",
                    "token": new_token,
                    "message": "Token created but not saved to database"
                }
                
    except Exception as e:
        logger.error(f"Error creating token: {e}")
        raise HTTPException(status_code=500, detail=str(e))
