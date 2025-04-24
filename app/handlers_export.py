from aiogram import Router, types
from aiogram.fsm.context import FSMContext
from app.db_utils import get_all_user_tokens, add_token_history
from app.database import AsyncSessionLocal
import io, csv, datetime

router = Router()

@router.callback_query(lambda c: c.data == "export_tokens_csv")
async def export_tokens_csv_callback(callback_query: types.CallbackQuery):
    async with AsyncSessionLocal() as session:
        user_tokens = await get_all_user_tokens(session, str(callback_query.from_user.id))
        if not user_tokens:
            await callback_query.message.reply("У вас нет сохраненных токенов для экспорта.")
            return

        output = io.StringIO()
        csv_writer = csv.writer(output)
        headers = ["Token", "User", "Created At", "Expires At", "Created Via", "Operation Type", "Parent Token", "Status"]
        csv_writer.writerow(headers)
        for token_data in user_tokens:
            csv_writer.writerow([
                token_data["token"],
                token_data.get("user_name", ""),
                datetime.datetime.fromtimestamp(token_data["created_at"]).strftime('%Y-%m-%d %H:%M:%S') if token_data.get("created_at") else "",
                datetime.datetime.fromtimestamp(token_data["expires_at"]).strftime('%Y-%m-%d %H:%M:%S') if token_data.get("expires_at") else "",
                token_data.get("created_via", ""),
                token_data.get("token_type", ""),
                token_data.get("parent_token", ""),
                token_data.get("status", "")
            ])
        output.seek(0)
        current_time = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"wialon_tokens_{current_time}.csv"
        await callback_query.message.reply_document(
            types.BufferedInputFile(output.getvalue().encode('utf-8'), filename=filename),
            caption=f"📊 Экспортировано {len(user_tokens)} токенов"
        )
        await add_token_history(session, str(callback_query.from_user.id), "", "export", {"count": len(user_tokens)})
        output.close()
