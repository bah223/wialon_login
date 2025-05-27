from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.models import Base
import os

# Настройки подключения к БД из переменных окружения
DB_HOST = os.getenv("DB_HOST", "db")  # используем имя сервиса из docker-compose
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "wialon_db")
DB_USER = os.getenv("DB_USER", "wialon")
DB_PASSWORD = os.getenv("DB_PASSWORD", "wialonpass")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Создаем асинхронный движок
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Установите True для отладки SQL запросов
    future=True,
    pool_size=5,
    max_overflow=10
)

# Создаем фабрику сессий
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def init_db():
    """Инициализация базы данных. Пересоздание только если явно задано."""
    reset_db = os.getenv("RESET_DB_ON_STARTUP", "False").lower() in ("1", "true", "yes")
    async with engine.begin() as conn:
        if reset_db:
            # Удаляем все таблицы перед созданием (только для разработки)
            await conn.run_sync(Base.metadata.drop_all)
        # Создаем таблицы заново (create_all не тронет существующие)
        await conn.run_sync(Base.metadata.create_all)

async def get_session() -> AsyncSession:
    """Получение сессии БД"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def check_db_connection():
    """
    Проверяет подключение к базе данных и возвращает True/False.
    """
    try:
        async with engine.begin() as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception as e:
        print(f"Ошибка подключения к базе данных: {e}")
        return False
