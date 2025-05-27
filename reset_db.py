import asyncio
from app.database import init_db

async def reset_database():
    """Пересоздание базы данных"""
    print("Начинаем пересоздание базы данных...")
    await init_db()
    print("База данных успешно пересоздана!")

if __name__ == "__main__":
    asyncio.run(reset_database()) 