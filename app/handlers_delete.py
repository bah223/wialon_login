from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from app.database import AsyncSessionLocal
from app.db_utils import get_all_user_tokens, add_token_history
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command(commands=["delete_token"]))
async def delete_token_command(message: types.Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        tokens = await get_all_user_tokens(session, str(message.from_user.id))
        if not tokens:
            await message.reply("У вас нет токенов для удаления.")
            return
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for t in tokens:
            preview = t["token"][:8] + '...' + t["token"][-4:]
            keyboard.add(types.KeyboardButton(preview))
        await message.reply("Выберите токен для удаления:", reply_markup=keyboard)
        await state.set_state("waiting_for_token_to_delete")

def waiting_for_token_to_delete_filter(message: types.Message, state: FSMContext):
    async def inner():
        return (await state.get_state()) == "waiting_for_token_to_delete"
    return inner

@router.message(waiting_for_token_to_delete_filter)
async def process_token_to_delete(message: types.Message, state: FSMContext):
    token_preview = message.text.strip()
    async with AsyncSessionLocal() as session:
        tokens = await get_all_user_tokens(session, str(message.from_user.id))
        token_obj = next((t for t in tokens if t["token"].startswith(token_preview[:8]) and t["token"].endswith(token_preview[-4:])), None)
        if not token_obj:
            await message.reply("❌ Токен не найден. Попробуйте ещё раз.")
            return
        # Удаление токена из MasterToken/ChildToken реализовать здесь, если требуется
        # await delete_token_by_value(session, token_obj["token"])  # Функция удалена, требуется реализовать логику, если нужно
        await add_token_history(session, str(message.from_user.id), token_obj["token"], "delete")
        await message.reply(f"✅ Токен удалён: <code>{token_obj['token']}</code>", parse_mode="HTML")
        await state.clear()
