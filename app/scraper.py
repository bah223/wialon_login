import aiohttp
import json
from app.utils import logger, get_env_variable, get_bool_env_variable
from typing import Dict, Union
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import re
import os
import sys
import time
import socket
import asyncio
import urllib.parse

"""
Модуль scraper.py - основной модуль для автоматического входа в систему Wialon и получения токена доступа.

Этот модуль использует Playwright для автоматизации браузера. Он поддерживает два режима работы:
1. Прямое подключение к сервису Wialon
2. Подключение через прокси Tor для анонимности и обхода возможных ограничений

Основной рабочий процесс:
- Инициализация браузера (headless режим по умолчанию)
- Опционально: настройка прокси Tor
- Открытие страницы Wialon
- Автоматическое заполнение формы логина
- Получение токена из URL после успешной авторизации
- Закрытие браузера и освобождение ресурсов
"""

# Регулярное выражение для извлечения token и sid из URL после успешной авторизации
URL_PATTERN = r"(?:sid|access_token)=([^&]*)"

async def get_wialon_token() -> Dict[str, Union[bool, str, None]]:
    """
    Получает токен Wialon из переменной окружения и проверяет его
    
    Returns:
        Dict с полями:
        - success (bool): Успешность операции
        - error (str): Сообщение об ошибке (если есть)
        - access_token (str): Токен доступа
        - sid (str): ID сессии
        - user_name (str): Имя пользователя
        - token_valid_until (str): Время окончания действия токена
    """
    logger.info("Getting Wialon token from environment variables...")
    
    result = {
        "success": False,
        "error": "",
        "access_token": None,
        "sid": None,
        "user_name": None,
        "token_valid_until": None
    }
    
    try:
        # Получаем токен из переменной окружения
        access_token = get_env_variable("WIALON_TOKEN")
        logger.info(f"Got token from env: {access_token[:10]}...")
        result["access_token"] = access_token
        
        # Выполняем проверку токена через API
        api_url = get_env_variable("WIALON_API_URL")
        logger.info(f"Using API URL: {api_url}")
        
        # Подготавливаем параметры запроса
        params = {
            "svc": "token/login",
            "params": json.dumps({
                "token": access_token,
                "fl": 1
            })
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, params=params) as response:
                api_result = await response.json()
                
                if "error" in api_result:
                    error_msg = f"API Error: {api_result['error']}"
                    logger.error(error_msg)
                    result["error"] = error_msg
                    return result
                
                # Извлекаем и сохраняем нужные данные
                result["success"] = True
                result["sid"] = api_result.get("eid")
                result["user_name"] = api_result.get("user", {}).get("nm")
                result["token_valid_until"] = api_result.get("tm")
                
                logger.info(f"Successfully authenticated as {result['user_name']}")
                logger.info(f"Session ID: {result['sid']}")
                
                # Закрываем сессию после использования
                await logout_wialon_session(result["sid"])
                
                return result
                
    except Exception as e:
        error_msg = f"Error getting or checking token: {e}"
        logger.error(error_msg)
        result["error"] = error_msg
        
    return result

async def logout_wialon_session(sid: str) -> bool:
    """
    Завершает сессию Wialon
    
    Args:
        sid (str): ID сессии для завершения
        
    Returns:
        bool: Успешность завершения сессии
    """
    try:
        api_url = get_env_variable("WIALON_API_URL")
        params = {"svc": "core/logout"}
        headers = {"sid": sid}
        
        logger.info(f"Logging out session {sid}...")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, params=params, headers=headers) as response:
                result = await response.json()
                
                if result.get("error") == 0:
                    logger.info("Session successfully closed")
                    return True
                else:
                    logger.error(f"Error closing session: {result}")
                    return False
                    
    except Exception as e:
        logger.error(f"Error during logout: {e}")
        return False

async def wialon_login_and_get_url(username: str, password: str, wialon_url: str, use_tor: bool = False) -> dict:
    """
    Выполняет вход в Wialon и возвращает URL с токеном.
    
    Args:
        username: Имя пользователя
        password: Пароль
        wialon_url: URL для входа в Wialon
        use_tor: Использовать ли Tor для подключения
        
    Returns:
        dict: Словарь с токеном, URL и путем к скриншоту (при ошибке)
    """
    logger.info(f"Starting Wialon login process for user {username} via {'TOR' if use_tor else 'direct connection'}...")
    logger.debug(f"Using credentials: {username}/{'*' * len(password)}")
    
    # Сохраняем начальный URL для возврата в случае ошибки
    initial_url = wialon_url
    screenshot_path = None
    
    async with async_playwright() as playwright:
        # Инициализируем браузер Chromium в headless или обычном режиме
        browser = await playwright.chromium.launch(headless=True)
        
        # Создаем новый контекст и страницу
        context = await browser.new_context()
        page = await context.new_page()
        
        # Инициализируем current_url с начальным значением
        current_url = initial_url
        
        try:
            # Настраиваем контекст с прокси Tor, если флаг use_tor = True
            if use_tor:
                # Подключаемся к локальному SOCKS5 прокси Tor, работающему на порту 9050
                logger.info("Setting up TOR proxy (socks5://127.0.0.1:9050)...")
                # Проверяем доступность прокси Tor
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(5)
                    sock.connect(('127.0.0.1', 9050))
                    sock.close()
                    logger.info("Successfully connected to Tor proxy")
                except Exception as e:
                    logger.error(f"Failed to connect to Tor proxy: {e}")
                    return {"token": f"Error: Tor proxy not available - {str(e)}", "url": "URL not available"}

                context = await browser.new_context(
                    proxy={
                        "server": "socks5://127.0.0.1:9050",
                        "bypass": "localhost"
                    }
                )
            else:
                context = await browser.new_context()
            
            # Создаем новую страницу
            page = await context.new_page()
            
            # Открываем страницу Wialon
            logger.info(f"Opening Wialon login page: {wialon_url}")
            await page.goto(wialon_url)
            
            # Ожидаем загрузки формы входа и заполняем её
            logger.debug("Waiting for login form...")
            
            # Ожидаем и заполняем поле имени пользователя
            try:
                # Сначала пробуем найти поле по ID
                await page.wait_for_selector("#user", timeout=10000)
                await page.fill("#user", username)
            except PlaywrightTimeoutError:
                try:
                    # Затем пробуем найти по атрибуту name
                    await page.wait_for_selector("input[name='user']", timeout=10000)
                    await page.fill("input[name='user']", username)
                except PlaywrightTimeoutError:
                    # В крайнем случае ищем любое текстовое поле
                    await page.wait_for_selector("input[type='text']", timeout=10000)
                    await page.fill("input[type='text']", username)
            
            logger.debug("Filling login form...")
            
            # Ожидаем и заполняем поле пароля
            try:
                # Сначала пробуем найти поле по ID
                await page.wait_for_selector("#passw", timeout=5000)
                await page.fill("#passw", password)
            except PlaywrightTimeoutError:
                try:
                    # Затем пробуем найти по атрибуту name
                    await page.wait_for_selector("input[name='passw']", timeout=5000)
                    await page.fill("input[name='passw']", password)
                except PlaywrightTimeoutError:
                    # В крайнем случае ищем любое поле пароля
                    await page.wait_for_selector("input[type='password']", timeout=5000)
                    await page.fill("input[type='password']", password)
            
            logger.debug("Submitting login form...")
            
            # Кликаем на кнопку входа
            try:
                await page.wait_for_selector("#submit", timeout=5000)
                await page.click("#submit")
            except PlaywrightTimeoutError:
                try:
                    await page.wait_for_selector("input[type='submit']", timeout=5000)
                    await page.click("input[type='submit']")
                except PlaywrightTimeoutError:
                    await page.press("input[type='password']", "Enter")
            
            # Ждем появления сообщения об успешной авторизации или страницы с токеном
            logger.debug("Waiting for login result...")
            
            # Даем время для обработки запроса
            await asyncio.sleep(2)
            
            # Проверяем текст страницы
            page_text = await page.evaluate("() => document.body.innerText")
            
            if "Authorized successfully" in page_text:
                logger.info("Login successful, extracting token...")
                
                # Получаем cookies
                cookies = await context.cookies()
                sid_cookie = next((c for c in cookies if c["name"] == "sid"), None)
                
                if sid_cookie:
                    # Используем cookie sid как токен
                    token = sid_cookie["value"]
                    logger.info(f"Successfully obtained token from cookies: {token[:10]}...")
                    return {"token": token, "url": page.url}
                
                # Или извлекаем токен из ответа API
                try:
                    # Проверяем локальное хранилище на наличие токена
                    token = await page.evaluate("""() => {
                        return localStorage.getItem('token') || 
                               localStorage.getItem('access_token') || 
                               sessionStorage.getItem('token') || 
                               sessionStorage.getItem('access_token');
                    }""")
                    
                    if token:
                        logger.info(f"Successfully obtained token from storage: {token[:10]}...")
                        return {"token": token, "url": page.url}
                    
                    # Или проверяем URL на наличие токена
                    current_url = page.url
                    token_match = re.search(r"access_token=([^&]+)", current_url)
                    if token_match:
                        token = token_match.group(1)
                        token = urllib.parse.unquote(token)
                        logger.info(f"Successfully obtained token from URL: {token[:10]}...")
                        return {"token": token, "url": page.url}
                    
                    # Если ничего не помогло, но авторизация успешна, возвращаем заглушку
                    logger.warning("Login successful but couldn't extract token, using placeholder")
                    return {"token": "AUTHORIZED_SUCCESSFULLY", "url": page.url}
                except Exception as e:
                    logger.error(f"Error extracting token: {e}")
                    return {"token": f"Error extracting token: {str(e)}", "url": page.url}
            else:
                # Проверяем, содержит ли URL токен
                if "access_token" in current_url or "sid=" in current_url:
                    logger.info(f"Login successful, token found in URL: {current_url[:50]}...")
                    return {"token": extract_token(current_url), "url": current_url}
                else:
                    # Проверяем, есть ли на странице сообщение об ошибке
                    try:
                        error_text = await page.inner_text("body")
                        if "Invalid user name or password" in error_text:
                            logger.error("Login failed: Invalid username or password")
                            # Делаем скриншот при ошибке
                            import os
                            import time
                            
                            # Создаем директорию для скриншотов, если её нет
                            screenshots_dir = os.path.join(os.getcwd(), "screenshots")
                            os.makedirs(screenshots_dir, exist_ok=True)
                            
                            # Генерируем уникальное имя файла
                            timestamp = int(time.time())
                            screenshot_path = os.path.join(screenshots_dir, f"error_{timestamp}.png")
                            
                            # Делаем скриншот
                            await page.screenshot(path=screenshot_path)
                            logger.info(f"Screenshot saved to {screenshot_path}")
                            
                            return {
                                "token": "Error: Invalid username or password", 
                                "url": current_url,
                                "screenshot": screenshot_path
                            }
                        else:
                            logger.error(f"Unknown response: {error_text[:100]}")
                            # Делаем скриншот при неизвестном ответе
                            import os
                            import time
                            
                            # Создаем директорию для скриншотов, если её нет
                            screenshots_dir = os.path.join(os.getcwd(), "screenshots")
                            os.makedirs(screenshots_dir, exist_ok=True)
                            
                            # Генерируем уникальное имя файла
                            timestamp = int(time.time())
                            screenshot_path = os.path.join(screenshots_dir, f"error_{timestamp}.png")
                            
                            # Делаем скриншот
                            await page.screenshot(path=screenshot_path)
                            logger.info(f"Screenshot saved to {screenshot_path}")
                            
                            return {
                                "token": f"Error: Unknown response - {error_text[:100]}", 
                                "url": current_url,
                                "screenshot": screenshot_path
                            }
                    except Exception as e:
                        logger.error(f"Error checking for error message: {e}")
            
            # Получаем текущий URL после входа
            current_url = page.url
            
        except Exception as e:
            logger.error(f"Error during Wialon login: {e}")
            # Пытаемся получить URL даже при ошибке
            try:
                current_url = page.url
                logger.info(f"URL at error: {current_url}")
                
                # Делаем скриншот при ошибке
                import os
                import time
                
                # Создаем директорию для скриншотов, если её нет
                screenshots_dir = os.path.join(os.getcwd(), "screenshots")
                os.makedirs(screenshots_dir, exist_ok=True)
                
                # Генерируем уникальное имя файла
                timestamp = int(time.time())
                screenshot_path = os.path.join(screenshots_dir, f"error_{timestamp}.png")
                
                # Делаем скриншот
                await page.screenshot(path=screenshot_path)
                logger.info(f"Screenshot saved to {screenshot_path}")
                
                return {
                    "token": f"Error: {str(e)}", 
                    "url": current_url or initial_url,
                    "screenshot": screenshot_path
                }
            except Exception as screenshot_error:
                logger.error(f"Error taking screenshot: {screenshot_error}")
                # Если не удалось получить текущий URL или сделать скриншот, возвращаем исходный URL
                return {
                    "token": f"Error: {str(e)}", 
                    "url": initial_url,
                    "screenshot": None
                }
        finally:
            await browser.close()
            logger.debug("Browser closed")

async def make_api_request(url: str, params: dict, use_tor: bool = False) -> dict:
    """
    Выполняет запрос к API с опциональным использованием Tor.
    
    Args:
        url: URL API
        params: Параметры запроса
        use_tor: Использовать ли Tor для запроса
        
    Returns:
        dict: Ответ API в формате JSON
    """
    # Настраиваем прокси для aiohttp если используем Tor
    proxy = None
    connector = None
    
    if use_tor:
        try:
            # Пытаемся использовать aiohttp_socks для SOCKS прокси
            from aiohttp_socks import ProxyConnector
            logger.info("Using aiohttp_socks for Tor proxy connection")
            connector = ProxyConnector.from_url('socks5://127.0.0.1:9050')
        except ImportError:
            # Если aiohttp_socks не установлен, предупреждаем и не используем прокси
            logger.warning("aiohttp_socks not available, falling back to direct connection")
            logger.warning("Please install aiohttp_socks for Tor support: pip install aiohttp_socks")
            use_tor = False
    
    try:
        # Используем ProxyConnector если доступен и Tor запрошен
        if connector and use_tor:
            logger.info("Using SOCKS5 connector for Tor")
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"API request failed with status {response.status}: {error_text}")
                        return {"error": f"HTTP error {response.status}"}
        else:
            # Обычное соединение без прокси
            logger.info("Using direct connection without proxy")
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        logger.error(f"API request failed with status {response.status}: {error_text}")
                        return {"error": f"HTTP error {response.status}"}
    except Exception as e:
        logger.error(f"Exception during API request: {e}")
        return {"error": str(e)}