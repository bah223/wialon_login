import asyncio
import logging
from app.bot import start_telegram_bot, bot
from fastapi import FastAPI
import uvicorn
from app.utils import logger

logging.basicConfig(level=logging.DEBUG)

# Создаем FastAPI приложение
app = FastAPI(title="Wialon Login Bot API")

@app.on_event("startup")
async def startup_event():
    # Проверяем наличие aiohttp_socks для поддержки Tor
    try:
        import aiohttp_socks
        logger.info("aiohttp_socks is available, Tor SOCKS proxy support is enabled")
    except ImportError:
        logger.warning("aiohttp_socks is not installed, Tor SOCKS proxy support is limited")
        logger.warning("To enable full Tor support, install aiohttp_socks: pip install aiohttp_socks")
    
    # Запускаем бота в фоновом режиме
    asyncio.create_task(start_telegram_bot())

@app.get("/health")
async def health_check():
    """Проверка здоровья приложения."""
    return {"status": "ok"}

if __name__ == "__main__":
    # Запускаем бота напрямую без FastAPI
    asyncio.run(start_telegram_bot())