from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from app.db_utils import add_token_history
from app.database import AsyncSessionLocal
from app.wialon_api import create_token, update_token
import logging

router = Router()
logger = logging.getLogger(__name__)

@router.message(Command(commands=["token_create"]))
async def token_create_handler(message: types.Message, state: FSMContext):
    # Пример: создание токена через Wialon API и сохранение результата в БД
    # Здесь предполагается, что нужные данные (master_token, права и т.д.) уже есть в state или message
    data = await state.get_data()
    master_token = data.get("master_token")
    access_rights = data.get("access_rights")
    duration = data.get("duration")
    label = data.get("label")
    if not master_token:
        await message.reply("Сначала получите мастер-токен!")
        return
    try:
        result = await create_token(master_token, access_rights, duration, label)
        new_token = result.get("token")
        async with AsyncSessionLocal() as session:
            await add_token_history(session, str(message.from_user.id), new_token, "create", {"label": label})
        await message.reply(f"✅ Токен создан: <code>{new_token}</code>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка создания токена: {e}")
        await message.reply(f"❌ Ошибка создания токена: {e}")

@router.message(Command(commands=["token_update"]))
async def token_update_handler(message: types.Message, state: FSMContext):
    # Пример: обновление токена через Wialon API и запись в историю
    data = await state.get_data()
    token_to_update = data.get("token_to_update")
    access_rights = data.get("access_rights")
    duration = data.get("duration")
    label = data.get("label")
    if not token_to_update:
        await message.reply("Укажите токен для обновления!")
        return
    try:
        result = await update_token(token_to_update, access_rights, duration, label)
        updated_token = result.get("token")
        async with AsyncSessionLocal() as session:
            await add_token_history(session, str(message.from_user.id), updated_token, "update", {"label": label})
        await message.reply(f"✅ Токен обновлен: <code>{updated_token}</code>", parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка обновления токена: {e}")
        await message.reply(f"❌ Ошибка обновления токена: {e}")
