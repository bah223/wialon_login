from aiogram import Router, types
from aiogram.filters import Command
from app.database import AsyncSessionLocal
from app.models import TokenHistory, User
from sqlalchemy.future import select
import datetime

router = Router()

@router.message(Command(commands=["history"]))
async def history_command(message: types.Message):
    async with AsyncSessionLocal() as session:
        # Получаем пользователя по telegram_id
        user = await session.execute(select(User).where(User.telegram_id == str(message.from_user.id)))
        user = user.scalars().first()
        if not user:
            await message.reply("Пользователь не найден в базе данных.")
            return
        # Получаем последние 10 операций
        q = select(TokenHistory).where(TokenHistory.user_id == user.id).order_by(TokenHistory.timestamp.desc()).limit(10)
        result = await session.execute(q)
        history = result.scalars().all()
        if not history:
            await message.reply("История операций пуста.")
            return
        text = "<b>История операций с токенами:</b>\n"
        for h in history:
            dt = h.timestamp.strftime('%Y-%m-%d %H:%M:%S')
            details = f" ({h.details})" if h.details else ""
            text += f"\n<b>{dt}</b>: {h.action} — <code>{h.token}</code>{details}"
        await message.reply(text, parse_mode="HTML")
