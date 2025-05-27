from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.states import GetTokenStates
from app.utils import get_bool_env_variable
from app.states import GetTokenStates
from app.database import AsyncSessionLocal
from app.db_utils import get_all_user_tokens
from app.utils import logger
from aiogram.enums import ParseMode

def get_tor_choice_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора режима подключения (Tor/прямой)."""
    buttons = [
        [
            types.InlineKeyboardButton(text="🔒 Через Tor", callback_data="check_tor:yes"),
            types.InlineKeyboardButton(text="🚀 Напрямую", callback_data="check_tor:no")
        ]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)

def get_manual_token_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для ручного ввода токена."""
    buttons = [
        [types.InlineKeyboardButton(text="✏️ Ввести токен вручную", callback_data="check_token_manual")]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)

def get_confirm_delete_all_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для подтверждения удаления всех токенов."""
    buttons = [
        [
            types.InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_delete_all"),
            types.InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_delete_all")
        ]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)

def get_connection_choice_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора режима подключения при получении токена."""
    buttons = [
        [
            types.InlineKeyboardButton(text="🔒 Через Tor", callback_data="use_tor:yes"),
            types.InlineKeyboardButton(text="🚀 Напрямую", callback_data="use_tor:no")
        ]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)

def get_saved_creds_connection_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для выбора режима подключения при использовании сохраненных учетных данных."""
    buttons = [
        [
            types.InlineKeyboardButton(text="🔒 Через Tor", callback_data="saved_creds_tor:yes"),
            types.InlineKeyboardButton(text="🚀 Напрямую", callback_data="saved_creds_tor:no")
        ]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)

async def choose_check_mode(message: types.Message, state: FSMContext):
    """
    Показывает пользователю выбор режима проверки токена (через Tor или напрямую).
    Если USE_TOR=1 в .env, то выбор не предлагается, а всегда используется Tor.
    """
    force_tor = get_bool_env_variable("USE_TOR", False)
    if force_tor:
        # Сразу запускаем проверку через Tor
        await state.update_data(use_tor=True)
        return
    
    # Если выбор разрешён, показываем клавиатуру
    keyboard = get_tor_choice_keyboard()
    await message.reply(
        "Выберите режим проверки токена:",
        reply_markup=keyboard
    )

# --- Универсальные обработчики для сценариев проверки токена ---
async def handle_check_token_manual(callback_query, state):
    await callback_query.answer()
    await callback_query.message.edit_text(
        "Пожалуйста, введите токен для проверки:\n\n"
        "<i>Вы также можете использовать команду в формате:</i>\n"
        "<code>/check_token YOUR_TOKEN</code>",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(GetTokenStates.waiting_for_token_input)

async def handle_token_input(message, state, choose_check_mode_func):
    token = message.text.strip()
    if not token:
        await message.reply("❌ Токен не может быть пустым. Пожалуйста, введите токен.")
        return
    await state.update_data(token=token)
    await choose_check_mode_func(message, state)

async def handle_check_specific_token(callback_query, state, choose_check_mode_func):
    await callback_query.answer()
    token_prefix = callback_query.data.split(":")[1]
    async with AsyncSessionLocal() as session:
        user_tokens = await get_all_user_tokens(session)
    full_token = None
    for token_data in user_tokens:
        if token_data["token"].startswith(token_prefix):
            full_token = token_data["token"]
            break
    if not full_token:
        await callback_query.message.reply("❌ Токен не найден. Возможно, он был удален.")
        return
    await state.update_data(token=full_token)
    await choose_check_mode_func(callback_query.message, state)

async def handle_check_mode_choice(callback_query, state, check_token_process_func):
    await callback_query.answer()
    use_tor = callback_query.data.split(":")[1] == "yes"
    data = await state.get_data()
    token = data.get("token")
    if not token:
        await callback_query.message.reply("❌ Токен не найден в состоянии. Начните сначала.")
        return
    await check_token_process_func(callback_query.message, token, use_tor, state)
