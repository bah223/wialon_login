"""
Модуль для проверки доступности и совместимости необходимых библиотек
"""
import importlib
import sys
from app.utils import logger

def check_aiohttp_socks_support():
    """Проверяет поддержку SOCKS прокси в aiohttp."""
    try:
        import aiohttp
        # Проверяем версию aiohttp
        version = aiohttp.__version__
        logger.info(f"Found aiohttp version {version}")
        
        # Проверяем наличие aiohttp_socks
        try:
            importlib.import_module('aiohttp_socks')
            logger.info("aiohttp_socks extension is installed")
            return True
        except ImportError:
            logger.warning("aiohttp_socks extension is not installed. SOCKS proxies may not work correctly.")
            logger.warning("Install it with: pip install aiohttp_socks")
            return False
    except ImportError:
        logger.error("aiohttp is not installed!")
        return False

def run_compatibility_checks():
    """Запускает все проверки совместимости."""
    logger.info("Running compatibility checks...")
    aiohttp_socks_ok = check_aiohttp_socks_support()
    
    if not aiohttp_socks_ok:
        logger.warning("Some features may not work correctly. Please install the required dependencies.")
    else:
        logger.info("All compatibility checks passed")
    
    return aiohttp_socks_ok 