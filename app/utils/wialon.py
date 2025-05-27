import re
from playwright.async_api import async_playwright

async def wialon_login_and_get_url(username: str, password: str, base_url: str, use_tor: bool = False) -> dict:
    """
    Логинится в Wialon через веб-интерфейс и получает токен.
    
    Args:
        username: Имя пользователя Wialon
        password: Пароль пользователя Wialon
        base_url: Базовый URL Wialon (например, https://hosting.wialon.com)
        use_tor: Использовать ли Tor для подключения
        
    Returns:
        dict: Результат операции с токеном или ошибкой
    """
    try:
        async with async_playwright() as p:
            # Настраиваем браузер
            if use_tor:
                proxy = {
                    "server": "socks5://tor:9050"
                }
            else:
                proxy = None
                
            browser = await p.firefox.launch(proxy=proxy)
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            try:
                page = await context.new_page()
                
                # Переходим на страницу логина
                try:
                    await page.goto(f"{base_url}/login.html", wait_until="networkidle")
                except Exception as e:
                    return {"error": f"Не удалось загрузить страницу логина: {str(e)}"}
                
                # Ждем появления формы логина
                try:
                    await page.wait_for_selector("#user", timeout=10000)
                    await page.wait_for_selector("#passw", timeout=10000)
                except Exception:
                    return {"error": "Не найдена форма для ввода логина/пароля"}
                
                # Вводим логин и пароль
                await page.fill("#user", username)
                await page.fill("#passw", password)
                
                # Нажимаем кнопку входа
                try:
                    await page.click("#login-form .btn-login")
                except Exception:
                    return {"error": "Не удалось нажать кнопку входа"}
                
                # Ждем редиректа или ошибки
                try:
                    # Проверяем наличие ошибки логина
                    error_selector = "#login-form .error-message"
                    error_message = None
                    
                    try:
                        error_element = await page.wait_for_selector(error_selector, timeout=5000)
                        if error_element:
                            error_message = await error_element.text_content()
                            if error_message:
                                return {"error": error_message.strip()}
                    except Exception:
                        # Если ошибка не найдена - это хорошо
                        pass
                        
                    # Ждем редиректа и получаем URL
                    await page.wait_for_url(f"{base_url}/**", timeout=10000)
                    current_url = page.url
                    
                    # Извлекаем токен из URL
                    token_match = re.search(r"access_token=([^&]+)", current_url)
                    if token_match:
                        return {"token": token_match.group(1)}
                    else:
                        return {"error": "Токен не найден в URL после успешного входа"}
                        
                except Exception as e:
                    return {"error": f"Ошибка при ожидании редиректа: {str(e)}"}
                    
            finally:
                await context.close()
                await browser.close()
                
    except Exception as e:
        return {"error": f"Ошибка при запуске браузера: {str(e)}"} 