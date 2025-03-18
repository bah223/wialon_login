import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import FSInputFile
from app.scraper import wialon_login_and_get_url, make_api_request
from app.utils import logger, get_env_variable, get_bool_env_variable
from app.storage import token_storage
from app.states import GetTokenStates
import time
import re
import json
import urllib.parse
import socket
import os
import datetime
import csv
import io

# Получаем токен бота из переменных окружения
bot = Bot(token=get_env_variable("BOT_TOKEN"))
dp = Dispatcher(storage=MemoryStorage())

@dp.message(Command(commands=['start', 'help']))
async def start_command(message: types.Message):
    """Обработчик команды /start и /help."""
    help_text = """
🤖 Wialon Token Bot

Доступные команды:
/get_token - Получить токен чере OAuth (браузер)
/check_token - Проверить Access Token и получить данные сессии
/token_create - Создать новый токен через API
/token_update - Обновить существующий токен через API
/token_list - Список сохраненных токенов
/help - Показать это сообщение
    """
    await message.reply(help_text, parse_mode=ParseMode.HTML)

@dp.message(Command(commands=['get_token']))
async def get_token_command(message: types.Message, state: FSMContext):
    """Получить Access Token через браузер."""
    # Проверяем, есть ли сохраненные учетные данные
    credentials = token_storage.get_credentials(message.from_user.id)
    
    # Создаем клавиатуру для выбора режима подключения
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="🔒 Через Tor", callback_data="use_tor:yes"),
                types.InlineKeyboardButton(text="🚀 Напрямую", callback_data="use_tor:no")
            ]
        ]
    )
    
    # Если есть сохраненные учетные данные, добавляем кнопку для их использования
    if credentials:
        # Добавляем информацию о времени сохранения
        saved_date = datetime.datetime.fromtimestamp(credentials["saved_at"]).strftime('%Y-%m-%d %H:%M')
        # Добавляем кнопку для быстрого входа
        keyboard.inline_keyboard.insert(0, [
            types.InlineKeyboardButton(
                text=f"🔑 Войти как {credentials['username']} (сохранено {saved_date})",
                callback_data="use_saved_credentials"
            )
        ])
        # Добавляем кнопку для удаления сохраненных данных
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(
                text="❌ Удалить сохраненные данные",
                callback_data="delete_saved_credentials"
            )
        ])
    
    # Формируем сообщение
    message_text = "Выберите режим подключения к Wialon:"
    if credentials:
        message_text = "Используйте сохраненные данные или выберите режим подключения:"
    
    await message.reply(message_text, reply_markup=keyboard)
    await state.set_state(GetTokenStates.connection_mode_choice)

@dp.message(Command(commands=['check_token']))
async def check_token_command(message: types.Message, state: FSMContext):
    """Команда для проверки токена."""
    user_tokens = token_storage.get_user_tokens(message.from_user.id)
    
    # Формируем клавиатуру для выбора токена или ручного ввода
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    
    if user_tokens:
        # Формируем кнопки с последними токенами
        for i, token_data in enumerate(user_tokens[:3]):  # Показываем только 3 последних токена
            token = token_data["token"]
            # Сокращаем токен только для отображения на кнопке, не влияя на функциональность
            token_preview = f"{token[:10]}...{token[-10:]}" if len(token) > 25 else token
            
            keyboard.inline_keyboard.append([
                types.InlineKeyboardButton(
                    text=f"Токен #{i+1}: {token_preview}",
                    callback_data=f"check_token:{token}"
                )
            ])
    
    # Добавляем кнопку для ручного ввода токена
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(
            text="✏️ Ввести токен вручную", 
            callback_data="check_token_manual"
        )
    ])
    
    await message.reply(
        "Выберите действие:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

@dp.message(Command(commands=['token_list']))
async def token_list_command(message: types.Message):
    """Показать список сохраненных токенов."""
    user_tokens = token_storage.get_user_tokens(message.from_user.id)
    
    if not user_tokens:
        await message.reply("У вас нет сохраненных токенов.")
        return
    
    # Формируем ответ со списком токенов
    response = f"🔑 <b>Сохраненные токены ({len(user_tokens)}):</b>\n\n"
    
    for i, token_data in enumerate(user_tokens):
        token = token_data["token"]
        # Показываем полный токен для возможности копирования
        token_info = f"<b>#{i+1}</b>: <code>{token}</code>\n"
        
        # Добавляем информацию о пользователе, если она есть
        if "user_name" in token_data:
            token_info += f"👤 <b>Пользователь:</b> {token_data['user_name']}\n"
            
        # Добавляем информацию о времени получения
        if "created_at" in token_data:
            created_time = datetime.datetime.fromtimestamp(token_data["created_at"]).strftime('%Y-%m-%d %H:%M:%S')
            token_info += f"⏱ <b>Получен:</b> {created_time}\n"
            
        # Добавляем информацию о способе создания токена
        if "created_via" in token_data:
            via_method = "API" if token_data["created_via"] == "api" else "Браузер"
            token_info += f"🔧 <b>Создан через:</b> {via_method}\n"
            
        # Добавляем информацию о типе операции API (create/update)
        if "token_type" in token_data:
            operation_type = "Создан" if token_data["token_type"] == "create" else "Обновлен"
            token_info += f"📝 <b>Операция:</b> {operation_type}\n"
            
        # Добавляем информацию о родительском токене, если есть
        if "parent_token" in token_data:
            parent_token = token_data['parent_token']
            if parent_token:  # Проверяем, что parent_token не None
                parent_preview = f"{parent_token[:10]}...{parent_token[-10:]}" if len(parent_token) > 25 else parent_token
                token_info += f"🔄 <b>На основе:</b> <code>{parent_preview}</code>\n"
            
        # Добавляем информацию о сроке действия, если она есть
        if "expire_time" in token_data and token_data["expire_time"]:
            expire_time = int(token_data["expire_time"])
            expire_str = datetime.datetime.fromtimestamp(expire_time).strftime('%Y-%m-%d %H:%M:%S')
            # Проверяем, истек ли токен
            if expire_time < time.time():
                token_info += f"⚠️ <b>ИСТЕК:</b> {expire_str}\n"
            else:
                # Сколько дней осталось
                days_left = (expire_time - time.time()) / 86400
                token_info += f"📅 <b>Действителен до:</b> {expire_str} ({int(days_left)} дн.)\n"
                
        response += f"{token_info}\n"
    
    # Добавляем кнопку для экспорта токенов
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="📊 Экспортировать в CSV", 
                    callback_data="export_tokens_csv"
                )
            ]
        ]
    )
    
    # Отправляем список токенов
    await message.reply(response, parse_mode=ParseMode.HTML, reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "export_tokens_csv")
async def export_tokens_csv_callback(callback_query: types.CallbackQuery):
    """Обработчик для экспорта токенов в CSV через кнопку."""
    await callback_query.answer()
    
    user_tokens = token_storage.get_user_tokens(callback_query.from_user.id)
    
    if not user_tokens:
        await callback_query.message.reply("У вас нет сохраненных токенов для экспорта.")
        return
    
    # Создаем CSV в памяти
    output = io.StringIO()
    csv_writer = csv.writer(output)
    
    # Добавляем заголовки
    headers = ["Token", "User", "Created At", "Expires At", "Created Via", 
               "Operation Type", "Parent Token", "Days Left", "Status"]
    csv_writer.writerow(headers)
    
    # Добавляем данные о токенах
    for token_data in user_tokens:
        token = token_data["token"]
        user_name = token_data.get("user_name", "")
        created_at = datetime.datetime.fromtimestamp(token_data.get("created_at", 0)).strftime('%Y-%m-%d %H:%M:%S') if "created_at" in token_data else ""
        
        # Обрабатываем срок действия
        expires_at = ""
        days_left = ""
        status = "Active"
        if "expire_time" in token_data and token_data["expire_time"]:
            expire_time = int(token_data["expire_time"])
            expires_at = datetime.datetime.fromtimestamp(expire_time).strftime('%Y-%m-%d %H:%M:%S')
            
            if expire_time < time.time():
                status = "Expired"
                days_left = "0"
            else:
                days_left = str(int((expire_time - time.time()) / 86400))
        
        created_via = token_data.get("created_via", "")
        operation_type = token_data.get("token_type", "")
        parent_token = token_data.get("parent_token", "")
        
        # Записываем строку в CSV
        csv_writer.writerow([
            token, user_name, created_at, expires_at, created_via, 
            operation_type, parent_token, days_left, status
        ])
    
    # Перемещаем указатель в начало файла
    output.seek(0)
    
    # Создаем имя файла
    current_time = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"wialon_tokens_{current_time}.csv"
    
    # Отправляем файл пользователю
    await callback_query.message.reply_document(
        types.BufferedInputFile(
            output.getvalue().encode('utf-8'),
            filename=filename
        ),
        caption=f"📊 Экспортировано {len(user_tokens)} токенов"
    )
    
    # Закрываем StringIO
    output.close()

@dp.callback_query(lambda c: c.data == "check_token_manual")
async def process_check_token_manual(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик для ручного ввода токена."""
    try:
        await callback_query.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback query: {e}")
        # Продолжаем обработку даже при ошибке ответа на callback
    
    try:
        await callback_query.message.edit_text(
            "Пожалуйста, введите токен для проверки:\n\n"
            "<i>Вы также можете использовать команду в формате:</i>\n"
            "<code>/check_token YOUR_TOKEN</code>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        logger.warning(f"Не удалось изменить сообщение: {e}")
        # Отправляем новое сообщение вместо редактирования старого
        await callback_query.message.reply(
            "Пожалуйста, введите токен для проверки:\n\n"
            "<i>Вы также можете использовать команду в формате:</i>\n"
            "<code>/check_token YOUR_TOKEN</code>",
            parse_mode=ParseMode.HTML
        )
    
    # Устанавливаем состояние для ожидания ввода токена
    await state.set_state(GetTokenStates.waiting_for_token_input)

@dp.callback_query(lambda c: c.data == "check_last_token")
async def process_check_last_token(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик для проверки последнего токена."""
    try:
        await callback_query.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback query: {e}")
        # Продолжаем обработку даже при ошибке ответа на callback
    
    # Получаем последний токен пользователя
    user_tokens = token_storage.get_user_tokens(callback_query.from_user.id)
    
    if not user_tokens:
        await callback_query.message.edit_text(
            "❌ Не удалось найти сохраненные токены.\n"
            "Пожалуйста, используйте /get_token для получения нового токена."
        )
        return
    
    # Сохраняем токен в состоянии
    await state.update_data(token=user_tokens[0]["token"])
    
    # Переходим к выбору режима проверки
    await choose_check_mode(callback_query.message, state)

@dp.message(GetTokenStates.waiting_for_token_input)
async def process_token_input(message: types.Message, state: FSMContext):
    """Обработка ввода токена вручную."""
    # Получаем введенный токен
    token = message.text.strip()
    
    if not token:
        await message.reply("❌ Токен не может быть пустым. Пожалуйста, введите токен.")
        return
    
    # Сохраняем токен в состоянии
    await state.update_data(token=token)
    logger.info(f"Token manually entered: {token[:10]}...")
    
    # Переходим к выбору режима проверки
    await choose_check_mode(message, state)

@dp.message(GetTokenStates.manual_input_username)
async def process_manual_username(message: types.Message, state: FSMContext):
    """Обработка ручного ввода имени пользователя."""
    await state.update_data(username=message.text)
    await state.set_state(GetTokenStates.manual_input_password)
    await message.reply("Введите пароль Wialon:")

def extract_token_from_url(url):
    """
    Извлекает токен доступа из URL.
    
    Args:
        url: URL, возвращенный после успешной авторизации
        
    Returns:
        str: Токен доступа или пустую строку, если токен не найден
    """
    # Проверяем, является ли url строкой
    if not isinstance(url, str):
        logger.warning(f"URL is not a string: {type(url)}")
        return ""
    
    # Извлекаем токен из URL
    token = ""
    # Паттерн для токена в URL после access_token=
    if "access_token=" in url:
        token = url.split("access_token=")[1].split("&")[0]
    # Паттерн для токена в URL как часть пути
    elif "/access_token/" in url:
        token = url.split("/access_token/")[1].split("/")[0]
    
    logger.debug(f"Extracted token from URL: {token[:10]}...")
    return token

@dp.message(GetTokenStates.manual_input_password)
async def process_manual_password_input(message: types.Message, state: FSMContext):
    """Обработка ручного ввода пароля и запуск процесса получения токена."""
    await state.update_data(password=message.text)
    await get_token_process(message, state)

async def get_token_process(message: types.Message, state: FSMContext):
    """Процесс получения токена через логин и пароль."""
    try:
        logger.info("Starting token retrieval process...")
        
        # Получаем данные из состояния
        data = await state.get_data()
        username = data.get("username")
        password = data.get("password")
        
        # Получаем настройку использования Tor из состояния или по умолчанию
        use_tor = data.get("use_tor", get_bool_env_variable("USE_TOR", False))
        
        try:
            # Если учетные данные не указаны, используем переменные окружения
            if not username:
                username = get_env_variable("WIALON_USERNAME")
            if not password:
                password = get_env_variable("WIALON_PASSWORD")
            
            # Получаем URL Wialon
            try:
                wialon_url = get_env_variable("WIALON_BASE_URL")
            except:
                wialon_url = "https://hosting.wialon.com/login.html?duration=0"
                logger.warning(f"WIALON_BASE_URL not found, using default: {wialon_url}")
        except Exception as e:
            logger.error(f"Error getting credentials: {e}")
            await message.reply(f"❌ Ошибка получения учетных данных: {str(e)}")
            await state.clear()
            return
        
        # Отправляем сообщение о начале процесса авторизации
        status_message = await message.reply(
            f"🔄 Выполняется вход в Wialon{' через Tor' if use_tor else ' напрямую'}..."
        )
        
        # Выполняем вход в систему и получаем токен
        try:
            result = await wialon_login_and_get_url(username, password, wialon_url, use_tor=use_tor)
            
            # Проверяем, что получили строку (старый формат) или словарь (новый формат)
            if isinstance(result, dict):
                token = result.get("token", "")
                full_url = result.get("url", "")
                screenshot = result.get("screenshot")
            else:
                # Обратная совместимость со старым форматом
                token = result
                full_url = result
                screenshot = None
            
            # Добавляем логирование для отладки
            logger.debug(f"Token type: {type(token)}, value: {token[:70]}")
            
            # Всегда извлекаем и отображаем URL
            url_info = f"\n\n🌐 <b>URL:</b>\n<code>{full_url}</code>"
            
            # Проверяем на наличие ошибки
            if token.startswith("Error:"):
                error_message = f"❌ {token}{url_info}"
                
                # Если есть скриншот, отправляем его
                if screenshot and os.path.exists(screenshot):
                    await status_message.edit_text(f"❌ Произошла ошибка. Отправляю скриншот...", parse_mode=ParseMode.HTML)
                    try:
                        # Используем FSInputFile для отправки файла
                        photo = FSInputFile(screenshot)
                        await message.answer_photo(
                            photo, 
                            caption=error_message,
                            parse_mode=ParseMode.HTML
                        )
                        # Удаляем временный файл скриншота
                        try:
                            os.remove(screenshot)
                        except:
                            pass
                    except Exception as photo_error:
                        logger.error(f"Error sending photo: {photo_error}")
                        # Если не удалось отправить фото, отправляем только текст
                        await status_message.edit_text(error_message, parse_mode=ParseMode.HTML)
                else:
                    await status_message.edit_text(error_message, parse_mode=ParseMode.HTML)
                
                await state.clear()
                return
            
            # Успешно получили токен, сохраняем его
            user_id = message.from_user.id
            logger.debug(f"User ID type: {type(user_id)}, value: {user_id}")
            # Метод add_token в классе TokenStorage является синхронным
            token_storage.add_token(user_id=user_id, token=token)
            
            # Обновляем информацию о токене
            token_info = {
                "user_name": username,
                "created_at": int(time.time()),
                "created_via": "browser"
            }
            token_storage.update_token_info(user_id, token, token_info)
            
            # Преобразуем токен в строку, если это не строка
            token_str = str(token)
            # Отображаем токен полностью без сокращения
            token_display = token_str
            
            # Создаем клавиатуру для сохранения учетных данных
            save_credentials_keyboard = types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(text="Да, сохранить", callback_data=f"save_credentials:{username}:{password}"),
                        types.InlineKeyboardButton(text="Нет", callback_data="not_save_credentials")
                    ]
                ]
            )
            
            await status_message.edit_text(
                f"✅ Токен успешно получен и сохранен!\n\n"
                f"🔑 <code>{token_display}</code>\n\n"
                f"{url_info}\n\n"
                f"Используйте /check_token чтобы узнать информацию о токене.\n\n"
                f"Сохранить учетные данные для быстрого входа в будущем?",
                reply_markup=save_credentials_keyboard,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Error in get_token_process: {e}")
            # Добавляем трассировку стека для более подробной информации об ошибке
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            
            # Всегда пытаемся отобразить URL, даже при ошибке
            url_info = ""
            if 'full_url' in locals():
                url_info = f"\n\n🌐 <b>URL:</b>\n<code>{full_url}</code>"
            
            error_message = f"❌ <b>Произошла ошибка:</b> {str(e)}{url_info}"
            
            # Если есть скриншот, отправляем его
            if 'screenshot' in locals() and screenshot and os.path.exists(screenshot):
                try:
                    await status_message.edit_text(f"❌ Произошла ошибка. Отправляю скриншот...", parse_mode=ParseMode.HTML)
                    # Используем FSInputFile для отправки файла
                    photo = FSInputFile(screenshot)
                    await message.answer_photo(
                        photo, 
                        caption=error_message,
                        parse_mode=ParseMode.HTML
                    )
                    # Удаляем временный файл скриншота
                    try:
                        os.remove(screenshot)
                    except:
                        pass
                except Exception as photo_error:
                    logger.error(f"Error sending photo: {photo_error}")
                    # Если не удалось отправить фото, отправляем только текст
                    await status_message.edit_text(error_message, parse_mode=ParseMode.HTML)
            else:
                await status_message.edit_text(error_message, parse_mode=ParseMode.HTML)
        finally:
            await state.clear()
            logger.info("State cleared")
    except Exception as e:
        logger.error(f"Error in get_token_process: {e}")
        # Добавляем трассировку стека для более подробной информации об ошибке
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        await status_message.edit_text(f"❌ Ошибка при получении токена: {str(e)}")
        await state.clear()

@dp.message(Command(commands=['delete_token']))
async def delete_token_command(message: types.Message):
    """Удалить сохраненный токен."""
    user_tokens = token_storage.get_user_tokens(message.from_user.id)
    
    if not user_tokens:
        await message.reply(
            "❌ У вас нет сохраненных токенов.\n"
            "Используйте /get_token для получения нового токена."
        )
        return
    
    # Создаем клавиатуру с токенами для удаления
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    
    for token_data in user_tokens:
        token = token_data["token"]
        # Краткое описание токена
        token_label = f"{token[:8]}... - "
        if "user_name" in token_data:
            token_label += token_data["user_name"]
        else:
            created_time = int(token_data.get('created_at', 0))
            import datetime
            time_str = datetime.datetime.fromtimestamp(created_time).strftime('%Y-%m-%d %H:%M')
            token_label += f"Получен: {time_str}"
            
        keyboard.add(types.InlineKeyboardButton(
            text=f"🗑️ {token_label}",
            callback_data=f"delete_token:{token[:15]}"  # Передаем только начало токена
        ))
    
    await message.reply(
        "🗑️ <b>Выберите токен для удаления:</b>",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@dp.callback_query(lambda c: c.data.startswith("delete_token:"))
async def delete_token_callback(callback_query: types.CallbackQuery):
    """Обработчик удаления токена."""
    try:
        await bot.answer_callback_query(callback_query.id)
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback query: {e}")
    
    token_start = callback_query.data.split(":", 1)[1]
    status_message = await callback_query.message.reply("🔄 Удаление токена...")
    
    try:
        # Получаем все токены пользователя
        user_tokens = token_storage.get_user_tokens(callback_query.from_user.id)
        
        if not user_tokens:
            await status_message.edit_text("❌ У вас нет сохраненных токенов.")
            return
        
        found_token = None
        for token_data in user_tokens:
            token = token_data["token"]
            if token.startswith(token_start):
                found_token = token
                break
        
        if not found_token:
            await status_message.edit_text("❌ Токен не найден.")
            return
        
        # Удаляем токен через API
        import aiohttp
        import json
        
        try:
            wialon_api_url = get_env_variable("WIALON_API_URL")
        except:
            wialon_api_url = "https://hst-api.wialon.com/wialon/ajax.html"
            logger.warning(f"WIALON_API_URL not found, using default: {wialon_api_url}")
        
        async with aiohttp.ClientSession() as session:
            # Шаг 1: Авторизация токеном
            login_params = {
                "svc": "token/login",
                "params": json.dumps({
                    "token": found_token
                })
            }
            
            async with session.get(wialon_api_url, params=login_params) as response:
                result = await response.json()
                
                if "error" in result:
                    await status_message.edit_text(
                        f"❌ Ошибка при авторизации: {result.get('error')}"
                    )
                    return
                
                session_id = result.get("eid")
                token_str = result.get("user", {}).get("token", "")
                
                # Извлекаем h (имя токена) из токена - первые 72 символа
                token_h = found_token[:72]
                
                # Шаг 2: Удаляем токен через token/update
                delete_params = {
                    "svc": "token/update",
                    "params": json.dumps({
                        "callMode": "delete",
                        "userId": user_id  # Используем ID пользователя вместо h
                    }),
                    "sid": session_id
                }
                
                async with session.get(wialon_api_url, params=delete_params) as delete_response:
                    delete_result = await delete_response.json()
                    
                    # После удаления через API, удаляем из локального хранилища
                    token_storage.delete_token(found_token)
                    
                    await status_message.edit_text("✅ Токен успешно удален!")
            
            # Обновляем сообщение с информацией о токене
            try:
                await callback_query.message.edit_text(
                    callback_query.message.text + "\n\n<b>🗑️ Токен удален!</b>",
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Could not update original message: {e}")
    except Exception as e:
        logger.error(f"Error deleting token: {e}")
        await status_message.edit_text(f"❌ Ошибка при удалении токена: {str(e)}")

@dp.callback_query(lambda c: c.data.startswith("check_token:"))
async def process_check_specific_token(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик для проверки конкретного токена."""
    await callback_query.answer()
    
    # Извлекаем токен из callback_data
    token_prefix = callback_query.data.split(":")[1]
    
    # Находим полный токен по префиксу
    user_tokens = token_storage.get_user_tokens(callback_query.from_user.id)
    full_token = None
    
    for token_data in user_tokens:
        if token_data["token"].startswith(token_prefix):
            full_token = token_data["token"]
            break
    
    if not full_token:
        await callback_query.message.reply("❌ Токен не найден. Возможно, он был удален.")
        return
    
    # Сохраняем токен в состоянии
    await state.update_data(token=full_token)
    
    # Переходим к выбору режима проверки
    await choose_check_mode(callback_query.message, state)

@dp.message(Command(commands=['list_all_tokens']))
async def list_all_tokens_command(message: types.Message):
    """
    Получить полный список токенов пользователя.
    
    Примечание: Функция в работе, не все возможности реализованы.
    """
    # Получаем последний токен пользователя для авторизации
    user_tokens = token_storage.get_user_tokens(message.from_user.id)
    
    if not user_tokens:
        await message.reply(
            "❌ У вас нет сохраненных токенов для авторизации.\n"
            "Используйте /get_token для получения нового токена."
        )
        return
    
    # Используем последний токен
    latest_token = user_tokens[0]["token"]
    
    status_message = await message.reply("🔄 Получение списка всех токенов...")
    
    try:
        import aiohttp
        import json
        
        # Получаем URL API
        try:
            wialon_api_url = get_env_variable("WIALON_API_URL")
        except:
            wialon_api_url = "https://hst-api.wialon.com/wialon/ajax.html"
            logger.warning(f"WIALON_API_URL not found, using default: {wialon_api_url}")
        
        async with aiohttp.ClientSession() as session:
            # Шаг 1: Авторизация токеном
            login_params = {
                "svc": "token/login",
                "params": json.dumps({
                    "token": latest_token
                })
            }
            
            async with session.get(wialon_api_url, params=login_params) as response:
                login_result = await response.json()
                
                if "error" in login_result:
                    await status_message.edit_text(
                        f"❌ Ошибка при авторизации: {login_result.get('error')}"
                    )
                    return
                
                session_id = login_result.get("eid")
                logger.info(f"Successfully logged in, session ID: {session_id}")
                
                # Получаем базовую информацию о токене
                if "user" in login_result and "token" in login_result["user"]:
                    token_str = login_result["user"]["token"]
                    
                    # Сначала попробуем декодировать URL-encoded символы
                    try:
                        decoded_token = urllib.parse.unquote(token_str)
                        logger.debug(f"URL-decoded token: {decoded_token}")
                        token_str = decoded_token
                    except Exception as e:
                        logger.warning(f"Error decoding URL-encoded token: {e}")
                    
                    # Форматируем сообщение с информацией о текущем токене в новом формате
                    user_name = login_result.get("user", {}).get("nm", "Неизвестно")
                    tokens_text = (
                        f"🔑 <b>Информация о текущем токене:</b>\n\n"
                        f"👤 <b>Пользователь:</b> {user_name}\n"
                        f"👑 <b>ID пользователя:</b> {login_result['user'].get('id', 'Неизвестно')}\n"
                        f"🔑 <b>EID:</b> {login_result.get('eid', 'Неизвестно')}\n"
                        f"🌐 <b>Host:</b> {login_result.get('host', 'Неизвестно')}\n\n"
                        f"ℹ️ <i>Примечание: К сожалению, API не предоставляет доступ к полному списку токенов. "
                        f"Отображается информация только о текущем токене.</i>\n\n"
                        f"📋 <b>Токен:</b>\n<code>{token_str}</code>\n"
                    )
                    
                    # Добавляем информацию о времени действия, если она есть
                    try:
                        # Извлекаем dur (время действия)
                        dur_match = re.search(r'"dur"\s*:\s*(\d+)', token_str)
                        if dur_match:
                            dur_value = int(dur_match.group(1))
                            
                            # Извлекаем app (название приложения)
                            app_match = re.search(r'"app"\s*:\s*"([^"]+)"', token_str)
                            app_name = app_match.group(1) if app_match else "Неизвестно"
                            tokens_text += f"\n🔌 <b>Приложение:</b> {app_name}"
                            
                            # Извлекаем at (время активации) или ct (время создания)
                            at_match = re.search(r'"at"\s*:\s*(\d+)', token_str)
                            if not at_match:
                                at_match = re.search(r'"ct"\s*:\s*(\d+)', token_str)
                            
                            at_value = int(at_match.group(1)) if at_match else int(time.time())
                            at_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(at_value))
                            tokens_text += f"\n⏱️ <b>Активирован:</b> {at_str}"
                            
                            # Обработка времени действия
                            if dur_value == 0:
                                # Токен "бессрочный"
                                tokens_text += f"\n⌛️ <b>Время действия:</b> <i>100 дней (условно бессрочный)</i>"
                                # Вычисляем условную дату окончания (100 дней)
                                approx_end_time = at_value + 8640000  # 100 дней в секундах
                                end_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(approx_end_time))
                                tokens_text += f"\n📅 <b>Действителен до:</b> {end_str} (при бездействии)"
                            else:
                                # Токен с ограниченным сроком
                                days = dur_value // 86400
                                hours = (dur_value % 86400) // 3600
                                minutes = (dur_value % 3600) // 60
                                
                                dur_str = f"{days} дн."
                                if hours > 0:
                                    dur_str += f" {hours} ч."
                                elif hours > 0:
                                    dur_str = f"{hours} ч. {minutes} мин."
                                else:
                                    dur_str = f"{minutes} мин."
                                
                                tokens_text += f"\n⌛️ <b>Время действия:</b> {dur_str}"
                                tokens_text += f"\n📅 <b>Действителен до:</b> {end_str}"
                                
                                # Проверяем, истек ли токен
                                end_time = at_value + dur_value
                                if end_time < time.time():
                                    tokens_text += f"\n⚠️ <b>ВНИМАНИЕ! Токен истек!</b>"
                                else:
                                    # Предупреждение о скором истечении
                                    remaining = end_time - int(time.time())
                                    if remaining > 0 and remaining < 259200:  # 3 дня в секундах
                                        rem_days = remaining // 86400
                                        rem_hours = (remaining % 86400) // 3600
                                        tokens_text += f"\n⚠️ <b>Внимание!</b> Токен истекает через {rem_days} дн. {rem_hours} ч.!"
                    except Exception as e:
                        logger.error(f"Error extracting token duration: {e}")
                        tokens_text += "\n⚠️ <i>Не удалось определить время действия токена</i>"
                else:
                    tokens_text = "❌ Не удалось получить информацию о токене."
                
                # Временно отключаем кнопки, которые не работают
                keyboard = None

                # Отправляем сообщение с информацией о токене
                await status_message.edit_text(tokens_text, parse_mode=ParseMode.HTML)
                
    except Exception as e:
        logger.error(f"Error listing tokens: {e}")
        await status_message.edit_text(f"❌ Ошибка при получении списка токенов: {str(e)}")

@dp.callback_query(lambda c: c.data.startswith("logout_session:"))
async def logout_session_callback(callback_query: types.CallbackQuery):
    """Обработчик закрытия сессии по запросу пользователя."""
    try:
        await bot.answer_callback_query(callback_query.id)
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback query: {e}")
    
    session_id = callback_query.data.split(":", 1)[1]
    status_message = await callback_query.message.reply("🔄 Закрытие сессии...")
    
    try:
        import aiohttp
        import json
        
        # Получаем URL API
        try:
            wialon_api_url = get_env_variable("WIALON_API_URL")
        except:
            wialon_api_url = "https://hst-api.wialon.com/wialon/ajax.html"
            logger.warning(f"WIALON_API_URL not found, using default: {wialon_api_url}")
        
        async with aiohttp.ClientSession() as session:
            logout_params = {
                "svc": "core/logout",
                "params": json.dumps({}),
                "sid": session_id
            }
            
            async with session.get(wialon_api_url, params=logout_params) as logout_response:
                logout_result = await logout_response.json()
                
                if "error" in logout_result:
                    await status_message.edit_text(
                        f"❌ Ошибка при закрытии сессии: {logout_result.get('error')}"
                    )
                else:
                    await status_message.edit_text("✅ Сессия успешно закрыта!")
                    
                    # Обновляем сообщение с информацией о токене
                    try:
                        await callback_query.message.edit_text(
                            callback_query.message.text + "\n\n<b>🔒 Сессия закрыта!</b>",
                            parse_mode="HTML"
                        )
                    except Exception as e:
                        logger.warning(f"Could not update original message: {e}")
    except Exception as e:
        logger.error(f"Error during session logout: {e}")
        await status_message.edit_text(f"❌ Ошибка при закрытии сессии: {str(e)}")

@dp.callback_query(lambda c: c.data == "list_all_tokens")
async def list_all_tokens_callback(callback_query: types.CallbackQuery):
    """Обработчик обновления списка токенов."""
    try:
        await bot.answer_callback_query(callback_query.id)
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback query: {e}")
    
    # Вызываем функцию получения списка токенов
    await list_all_tokens_command(callback_query.message)

@dp.callback_query(lambda c: c.data.startswith("extend_token:"))
async def extend_token_callback(callback_query: types.CallbackQuery):
    """Обработчик продления срока действия токена."""
    try:
        await bot.answer_callback_query(callback_query.id)
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback query: {e}")
    
    token_start = callback_query.data.split(":", 1)[1]
    status_message = await callback_query.message.reply("🔄 Продление токена...")
    
    try:
        # Получаем все токены пользователя
        user_tokens = token_storage.get_user_tokens(callback_query.from_user.id)
        
        if not user_tokens:
            await status_message.edit_text("❌ У вас нет сохраненных токенов.")
            return
        
        found_token = None
        for token_data in user_tokens:
            token = token_data["token"]
            if token.startswith(token_start):
                found_token = token
                break
        
        if not found_token:
            await status_message.edit_text("❌ Токен не найден.")
            return
        
        # Продление токена через token/update API
        import aiohttp
        import json
        
        try:
            wialon_api_url = get_env_variable("WIALON_API_URL")
        except:
            wialon_api_url = "https://hst-api.wialon.com/wialon/ajax.html"
            logger.warning(f"WIALON_API_URL not found, using default: {wialon_api_url}")
        
        async with aiohttp.ClientSession() as session:
            # Шаг 1: Авторизация токеном
            login_params = {
                "svc": "token/login",
                "params": json.dumps({
                    "token": found_token
                })
            }
            
            async with session.get(wialon_api_url, params=login_params) as response:
                result = await response.json()
                
                if "error" in result:
                    await status_message.edit_text(
                        f"❌ Ошибка при авторизации: {result.get('error')}"
                    )
                    return
                
                session_id = result.get("eid")
                token_str = result.get("user", {}).get("token", "")
                
                # Декодируем URL-encoded строку токена
                try:
                    decoded_token = urllib.parse.unquote(token_str)
                    token_str = decoded_token
                except Exception as e:
                    logger.warning(f"Error decoding URL-encoded token: {e}")
                
                # Извлекаем h (имя токена) из токена - первые 72 символа
                token_h = found_token[:72]
                
                # Получаем информацию о приложении
                app_match = re.search(r'"app"\s*:\s*"([^"]+)"', token_str)
                app_name = app_match.group(1) if app_match else "Wialon Hosting"
                
                # Шаг 2: Продление токена с помощью token/update API
                update_params = {
                    "svc": "token/update",
                    "params": json.dumps({
                        "callMode": "update",
                        "userId": user_id,  # Используем ID пользователя
                        "dur": 8640000,  # 100 дней в секундах
                        "app": app_name,
                        "at": 0,  # Активировать прямо сейчас
                        "fl": 8192,  # Базовый доступ
                        "p": "{}"
                    }),
                    "sid": session_id
                }
                
                async with session.get(wialon_api_url, params=update_params) as update_response:
                    update_result = await update_response.json()
                    
                    if "error" in update_result:
                        await status_message.edit_text(
                            f"❌ Ошибка при продлении токена: {update_result.get('error')}"
                        )
                        return
                    
                    # Получаем обновленную информацию о токене
                    dur_value = update_result.get("dur", 0)
                    at_value = update_result.get("at", int(time.time()))
                    end_time = at_value + dur_value
                    end_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))
                    
                    # Обновляем информацию о токене в хранилище
                    token_storage.update_token_data(found_token, {
                        "duration": dur_value,
                        "is_permanent": dur_value == 0,
                        "expire_time": end_time if dur_value > 0 else at_value + 8640000,
                        "created_time": at_value,
                        "token_name": app_name,
                        "last_checked": int(time.time())
                    })
                    
                    await status_message.edit_text(
                        f"✅ Токен успешно продлен!\n\n"
                        f"⌛ <b>Новый срок действия:</b> 100 дней\n"
                        f"📅 <b>Действителен до:</b> {end_time_str}\n",
                        parse_mode="HTML"
                    )
                    
                    # Обновляем исходное сообщение
                    try:
                        await check_token_command(callback_query.message, found_token)
                    except Exception as e:
                        logger.error(f"Error refreshing token info: {e}")
    except Exception as e:
        logger.error(f"Error extending token: {e}")
        await status_message.edit_text(f"❌ Ошибка при продлении токена: {str(e)}")

@dp.callback_query(lambda c: c.data.startswith("use_tor:"))
async def process_connection_mode(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработка выбора режима подключения (через Tor или напрямую)."""
    await callback_query.answer()
    
    # Извлекаем выбор пользователя
    use_tor = callback_query.data.split(":")[1] == "yes"
    
    # Сохраняем выбор в состоянии
    await state.update_data(use_tor=use_tor)
    
    # Отправляем сообщение о выбранном режиме
    mode_text = "🔒 Через Tor" if use_tor else "🚀 Напрямую"
    await callback_query.message.edit_text(
        f"Выбран режим подключения: {mode_text}\n\n"
        "Введите ваш логин для Wialon:"
    )
    
    # Переходим к вводу логина
    await state.set_state(GetTokenStates.manual_input_username)

@dp.callback_query(lambda c: c.data.startswith("check_tor:"))
async def process_check_token_mode(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик выбора режима проверки токена."""
    try:
        await callback_query.answer()
    except Exception as e:
        logger.warning(f"Не удалось ответить на callback query: {e}")
        # Продолжаем обработку даже при ошибке ответа на callback
    
    # Получаем выбранный режим
    use_tor = callback_query.data.split(":")[1] == "yes"
    
    # Получаем токен из состояния
    data = await state.get_data()
    token = data.get("token", "")
    
    if not token:
        await callback_query.message.reply("❌ Токен не найден. Пожалуйста, получите новый токен.")
        await state.clear()
        return
    
    # Проверяем токен
    await check_token_process(callback_query.message, token, use_tor, state)

async def check_token_process(message: types.Message, token: str, use_tor: bool = None, state: FSMContext = None):
    """Процесс проверки токена."""
    # Если не указано явно, получаем настройку Tor из конфига
    if use_tor is None:
        use_tor = get_bool_env_variable("USE_TOR", False)
    
    status_message = await message.reply(
        f"🔄 Проверка токена{' через Tor' if use_tor else ' напрямую'}..."
    )
    
    try:
        import json
        import re
        
        # Получаем URL API
        try:
            wialon_api_url = get_env_variable("WIALON_API_URL")
        except:
            wialon_api_url = "https://hst-api.wialon.com/wialon/ajax.html"
            logger.warning(f"WIALON_API_URL not found, using default: {wialon_api_url}")
        
        # Добавляем логирование для отладки
        logger.debug(f"Checking token: {token[:10]}...")
        logger.debug(f"API URL: {wialon_api_url}")
        
        # Параметры для запроса авторизации токеном
        login_params = {
            "svc": "token/login",
            "params": json.dumps({
                "token": token,
                "fl": 7
            })
        }
        
        # Логируем параметры запроса
        logger.debug(f"API request params: {login_params}")
        
        # Используем нашу функцию для запросов к API
        login_result = await make_api_request(wialon_api_url, login_params, use_tor)
        
        # Логируем результат запроса
        logger.debug(f"API response: {login_result}")
        
        # Проверяем на ошибки
        if "error" in login_result:
            error_code = login_result.get("error")
            logger.error(f"API returned error: {error_code}")
            if error_code == 1:
                await status_message.edit_text("❌ Токен недействителен или истек срок его действия.")
            elif error_code == 4:
                await status_message.edit_text("❌ Некорректный формат токена.")
            else:
                await status_message.edit_text(f"❌ Ошибка при проверке токена: {error_code}")
            return
        
        # Получаем базовую информацию о токене
        if "user" in login_result and "token" in login_result:
            # Получаем информацию о пользователе
            user_name = login_result["user"].get("nm", "Неизвестно")
            user_id = login_result["user"].get("id", "Неизвестно")
            eid = login_result.get("eid", "Неизвестно")
            host = login_result.get("host", "Неизвестно")
            
            logger.info(f"Token check successful for user: {user_name}, EID: {eid}")
            
            # Получаем информацию о токене
            token_info = login_result.get("token", "{}")
            logger.debug(f"Token info from API: {token_info}")
            
            # Парсим информацию о токене
            token_data = {}
            try:
                # Пытаемся распарсить JSON в поле token
                tokeninfo = safe_parse_json(token_info)
                token_data.update(tokeninfo)
            except Exception as e:
                logger.error(f"Error parsing token info: {e}")
            
            # Форматируем сообщение с информацией о текущем токене в новом формате
            tokens_text = (
                f"🔑 <b>Информация о текущем токене:</b>\n\n"
                f"👤 <b>Пользователь:</b> {user_name}\n"
                f"👑 <b>ID пользователя:</b> {user_id}\n"
                f"🔑 <b>EID:</b> {eid}\n"
                f"🌐 <b>Host:</b> {host}\n\n"
                f"ℹ️ <i>Примечание: К сожалению, API не предоставляет доступ к полному списку токенов. "
                f"Отображается информация только о текущем токене.</i>\n\n"
                f"📋 <b>Токен:</b>\n<code>{token}</code>\n"
            )
            
            # Добавляем информацию о времени действия, если она есть
            try:
                # Получаем время действия токена
                dur_value = token_data.get("dur")
                if dur_value is not None:
                    # Получаем название приложения
                    app_name = token_data.get("app", "Wialon")
                    # Декодируем URL-encoded строки
                    if isinstance(app_name, str) and '%20' in app_name:
                        app_name = urllib.parse.unquote(app_name)
                    tokens_text += f"\n🔌 <b>Приложение:</b> {app_name}"
                    
                    # Получаем время активации токена
                    at_value = token_data.get("at") or token_data.get("ct") or int(time.time())
                    at_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(at_value))
                    tokens_text += f"\n⏱️ <b>Активирован:</b> {at_str}"
                    
                    # Проверяем, бессрочный ли токен
                    if dur_value == 0:
                        # Для бессрочных токенов показываем условные 100 дней
                        tokens_text += f"\n⌛️ <b>Время действия:</b> <i>100 дней (условно бессрочный)</i>"
                        # Вычисляем условную дату окончания (100 дней)
                        approx_end_time = at_value + 8640000  # 100 дней в секундах
                        end_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(approx_end_time))
                        tokens_text += f"\n📅 <b>Действителен до:</b> {end_str} (при бездействии)"
                    else:
                        # Вычисляем время окончания действия токена
                        end_time = at_value + dur_value
                        end_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time))
                        
                        # Форматируем время действия
                        days = dur_value // 86400
                        hours = (dur_value % 86400) // 3600
                        minutes = (dur_value % 3600) // 60
                        
                        if days > 0:
                            dur_str = f"{days} дн."
                            if hours > 0:
                                dur_str += f" {hours} ч."
                        elif hours > 0:
                            dur_str = f"{hours} ч. {minutes} мин."
                        else:
                            dur_str = f"{minutes} мин."
                        
                        tokens_text += f"\n⌛️ <b>Время действия:</b> {dur_str}"
                        tokens_text += f"\n📅 <b>Действителен до:</b> {end_str}"
                        
                        # Проверяем, истек ли токен
                        if end_time < time.time():
                            tokens_text += f"\n⚠️ <b>ВНИМАНИЕ! Токен истек!</b>"
                        else:
                            # Предупреждение о скором истечении
                            remaining = end_time - int(time.time())
                            if remaining > 0 and remaining < 259200:  # 3 дня в секундах
                                rem_days = remaining // 86400
                                rem_hours = (remaining % 86400) // 3600
                                tokens_text += f"\n⚠️ <b>Внимание!</b> Токен истекает через {rem_days} дн. {rem_hours} ч.!"
            except Exception as e:
                logger.error(f"Error extracting token duration: {e}")
                tokens_text += "\n⚠️ <i>Не удалось определить время действия токена</i>"
        else:
            logger.error(f"Unexpected API response structure: {login_result}")
            tokens_text = "❌ Не удалось получить информацию о токене."
        
        # Временно отключаем кнопки, которые не работают
        keyboard = None

        # Отправляем сообщение с информацией о токене
        await status_message.edit_text(tokens_text, parse_mode=ParseMode.HTML)
        
        # Очищаем состояние после проверки
        if state:
            await state.clear()
        
    except Exception as e:
        logger.error(f"Error checking token: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        await status_message.edit_text(f"❌ Ошибка при проверке токена: {str(e)}")
        
        # Очищаем состояние после ошибки
        if state:
            await state.clear()

# Функция для безопасного парсинга JSON в поле token
def safe_parse_json(json_str: str) -> dict:
    """Безопасно парсит JSON строку, даже если она содержит экранированные кавычки или обрамлена кавычками."""
    if not isinstance(json_str, str):
        logger.warning(f"Expected string for JSON parsing, got {type(json_str)}")
        return {}

    # Лог первых 50 символов для отладки
    logger.debug(f"Attempting to parse JSON: {json_str[:50]}...")
    
    # Специальный случай для Wialon token - по документации
    # https://sdk.wialon.com/wiki/ru/sidebar/remoteapi/codesamples/login
    # "token": "{"app":"Wialon Hosting","ct":1443682655,"at":1443682655,"dur":2592000,"fl":-1,"p":"{}","items":[]}"
    if "app" in json_str and "dur" in json_str:
        try:
            import re
            # Извлечение значения dur напрямую регулярным выражением
            dur_match = re.search(r'"dur"\s*:\s*(\d+)', json_str)
            if dur_match:
                dur_value = int(dur_match.group(1))
                logger.info(f"Extracted duration value: {dur_value} seconds ({dur_value//86400} days)")
                
                # Извлечение времени активации
                at_match = re.search(r'"at"\s*:\s*(\d+)', json_str)
                at_value = int(at_match.group(1)) if at_match else None
                
                # Если нет at, проверяем ct (время создания)
                if not at_value:
                    ct_match = re.search(r'"ct"\s*:\s*(\d+)', json_str)
                    at_value = int(ct_match.group(1)) if ct_match else int(time.time())
                at_value = int(at_match.group(1)) if at_match else int(time.time())
                
                # Извлекаем имени приложения
                app_match = re.search(r'"app"\s*:\s*"([^"]+)"', json_str)
                app_name = app_match.group(1) if app_match else "Wialon"
                
                return {
                    "dur": dur_value,
                    "at": at_value,
                    "app": app_name
                }
        except Exception as e:
            logger.error(f"Error extracting Wialon token data with regex: {e}")
    
    # Стандартные методы парсинга (без изменений)
    try:
        # Сначала пробуем напрямую парсить как есть
        result = json.loads(json_str)
        logger.debug("Successfully parsed JSON directly")
        return result
    except:
        try:
            # Если не удалось, пробуем удалить внешние кавычки и распарсить снова
            if json_str.startswith('"') and json_str.endswith('"'):
                cleaned = json_str[1:-1].replace('\\"', '"')
                result = json.loads(cleaned)
                logger.debug("Successfully parsed JSON after removing quotes")
                return result
        except:
            pass
        
        try:
            # Если и это не помогло, пробуем заменить одинарные кавычки на двойные
            alt_json = json_str.replace("'", '"')
            result = json.loads(alt_json)
            logger.debug("Successfully parsed JSON after replacing single quotes")
            return result
        except:
            pass
    
        try:
            # Если все методы парсинга не сработали, попробуем регулярные выражения
            import re
            # Найдем значение dur
            dur_match = re.search(r'"dur"\s*:\s*(\d+)', json_str)
            if dur_match:
                dur_value = int(dur_match.group(1))
                logger.debug(f"Extracted dur={dur_value} using regex")
                
                # Найдем значение at или ct
                at_match = re.search(r'"(?:at|ct)"\s*:\s*(\d+)', json_str)
                at_value = int(at_match.group(1)) if at_match else 0
                
                return {"dur": dur_value, "at": at_value}
        except:
            pass
    
    logger.warning(f"Failed to parse JSON: {json_str[:30]}...")
    # Возвращаем пустой словарь, если все методы парсинга не сработали
    return {}

@dp.callback_query(lambda c: c.data == "delete_all_tokens")
async def process_delete_all_tokens(callback_query: types.CallbackQuery):
    """Обработчик для удаления всех токенов пользователя."""
    await callback_query.answer()
    
    # Получаем ID пользователя
    user_id = callback_query.from_user.id
    
    # Создаем клавиатуру для подтверждения
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(
                    text="✅ Да, удалить все",
                    callback_data="confirm_delete_all"
                ),
                types.InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="cancel_delete_all"
                )
            ]
        ]
    )
    
    # Запрашиваем подтверждение
    await callback_query.message.edit_text(
        "⚠️ <b>Внимание!</b> Вы уверены, что хотите удалить <b>ВСЕ</b> сохраненные токены?\n\n"
        "Это действие нельзя отменить.",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

@dp.callback_query(lambda c: c.data == "confirm_delete_all")
async def process_confirm_delete_all(callback_query: types.CallbackQuery):
    """Обработчик подтверждения удаления всех токенов."""
    await callback_query.answer()
    
    # Получаем ID пользователя
    user_id = callback_query.from_user.id
    
    # Удаляем все токены пользователя
    token_storage.delete_all_user_tokens(user_id)
    
    # Сообщаем об успешном удалении
    await callback_query.message.edit_text(
        "✅ Все токены успешно удалены.",
        parse_mode=ParseMode.HTML
    )

@dp.callback_query(lambda c: c.data == "cancel_delete_all")
async def process_cancel_delete_all(callback_query: types.CallbackQuery):
    """Обработчик отмены удаления всех токенов."""
    await callback_query.answer()
    
    # Возвращаемся к списку токенов
    await token_list_command(callback_query.message)

@dp.message(Command(commands=['create_token']))
async def create_token_command(message: types.Message, state: FSMContext):
    """Создать новый токен на основе существующего."""
    # Получаем последний токен пользователя
    user_tokens = token_storage.get_user_tokens(message.from_user.id)
    
    # Создаем клавиатуру для выбора токена
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    
    # Добавляем кнопку для ввода токена вручную
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(
            text="✏️ Ввести токен вручную", 
            callback_data="create_token_manual"
        )
    ])
    
    # Добавляем кнопки для имеющихся токенов, если они есть
    if user_tokens:
        for i, token_data in enumerate(user_tokens[:5]):  # Не более 5 токенов
            token = token_data["token"]
            token_preview = f"{token[:10]}...{token[-10:]}" if len(token) > 25 else token
            
            # Если есть имя пользователя, добавляем его
            user_info = ""
            if "user_name" in token_data:
                user_info = f" ({token_data['user_name']})"
            
            keyboard.inline_keyboard.insert(i, [
                types.InlineKeyboardButton(
                    text=f"🔑 Токен #{i+1}{user_info}", 
                    callback_data=f"token:{i}"
                )
            ])
        
        message_text = "Выберите токен, на основе которого будет создан новый токен:"
    else:
        message_text = "У вас нет сохраненных токенов. Введите токен вручную:"
    
    await message.reply(
        message_text,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

@dp.callback_query(lambda c: c.data == "create_token_manual")
async def process_create_token_manual(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик для ручного ввода токена для создания нового."""
    await callback_query.answer()
    
    await callback_query.message.edit_text(
        "Пожалуйста, введите токен, на основе которого нужно создать новый:\n\n"
        "<i>Формат: строка с токеном доступа Wialon</i>",
        parse_mode=ParseMode.HTML
    )
    
    # Устанавливаем состояние для ожидания ввода токена
    await state.set_state(GetTokenStates.waiting_for_source_token)

@dp.message(GetTokenStates.waiting_for_source_token)
async def process_source_token_input(message: types.Message, state: FSMContext):
    """Обработка ввода исходного токена."""
    source_token = message.text.strip()
    
    if not source_token:
        await message.reply("❌ Токен не может быть пустым. Пожалуйста, введите токен.")
        return
    
    # Сохраняем токен в состоянии
    await state.update_data(source_token=source_token)
    
    # Показываем выбор режима подключения
    await show_connection_choice(message, state, source_token)

async def show_connection_choice(message, state: FSMContext, token: str):
    """Показать выбор режима подключения."""
    await state.update_data(source_token=token)
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="🔒 Через Tor", callback_data="create_token:yes"),
                types.InlineKeyboardButton(text="🚀 Напрямую", callback_data="create_token:no")
            ]
        ]
    )
    
    # Проверяем, это сообщение или колбэк
    if hasattr(message, 'reply'):
        # Это сообщение Message
        await message.reply(
            f"Выберите режим подключения для создания нового токена:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
    else:
        # Это сообщение от callback_query
        await message.edit_text(
            f"Выберите режим подключения для создания нового токена:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )

@dp.callback_query(lambda c: c.data.startswith("token:"))
async def process_token_selection(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработка выбора токена из списка."""
    # Получаем индекс токена
    index = int(callback_query.data.split(":")[1])
    user_tokens = token_storage.get_user_tokens(callback_query.from_user.id)
    token = user_tokens[index]["token"]
    
    # Сохраняем выбранный токен
    await state.update_data(source_token=token)
    
    # Показываем выбор режима подключения
    await show_connection_choice(callback_query.message, state, token)

@dp.callback_query(lambda c: c.data.startswith("create_token:"))
async def process_create_token(callback_query: types.CallbackQuery, state: FSMContext):
    """Создание нового токена через API."""
    try:
        await callback_query.answer()
        use_tor = callback_query.data.split(":")[1] == "yes"
        
        data = await state.get_data()
        source_token = data.get("source_token")
        # Добавляем переменную api_operation
        api_operation = "create"
        
        if not source_token:
            await callback_query.message.edit_text("❌ Токен не найден")
            return
             
        # Если токен - это словарь, извлекаем строку токена
        if isinstance(source_token, dict):
            source_token = source_token.get("token", "")
             
        # Очищаем токен от URL и других лишних данных
        if isinstance(source_token, str):
            # Если это URL или JSON, извлекаем только токен
            if "access_token=" in source_token:
                source_token = source_token.split("access_token=")[1].split("&")[0]
            elif source_token.startswith("{") and "token" in source_token:
                try:
                    token_data = json.loads(source_token)
                    source_token = token_data.get("token", source_token)
                except:
                    pass
         
        status_message = await callback_query.message.edit_text(
            f"🔄 Создаем новый токен {'через Tor' if use_tor else 'напрямую'}..."
        )
         
        # Получаем URL API
        wialon_api_url = get_env_variable("WIALON_API_URL", "https://hst-api.wialon.com/wialon/ajax.html")
         
        # 1. Логин через token/login
        login_params = {
            "svc": "token/login",
            "params": json.dumps({
                "token": source_token,
                "fl": 7  # Используем флаг 7, чтобы получить полную информацию, включая user_id
            })
        }
         
        logger.debug(f"Login params: {login_params}")
        login_result = await make_api_request(wialon_api_url, login_params, use_tor)
        logger.debug(f"Login result: {login_result}")
         
        if "error" in login_result:
            await status_message.edit_text(f"❌ Ошибка авторизации: {login_result.get('error')}")
            return
         
        # Получаем eid из результата логина
        session_id = login_result.get("eid")
        if not session_id:
            await status_message.edit_text("❌ Не удалось получить ID сессии")
            return
        
        # Получаем user_id напрямую из ответа token/login
        user_id = login_result.get("user", {}).get("id")
        if not user_id:
            await status_message.edit_text("❌ Не удалось получить ID пользователя из ответа")
            return
        
        logger.debug(f"Полученный ID сессии: {session_id}")
        logger.debug(f"Полученный ID пользователя: {user_id}")
        
        # 2. Создание/обновление токена через token/update
        create_params = {
            "svc": "token/update",  # Используем token/update как в примере
            "params": json.dumps({
                "callMode": "create",
                "userId": str(user_id),  # обязательно передаём в виде строки
                "h": "TOKEN",
                "app": "Wialon Hosting – a platform for GPS monitoring",
                "at": 0,
                "dur": 0,
                "fl": 8192,
                "p": "{}",  # именно строка "{}"
                "items": []
            }),
            "sid": session_id
        }
        
        logger.debug(f"Create params: {create_params}")
        create_result = await make_api_request(wialon_api_url, create_params, use_tor)
        logger.debug(f"Create result: {create_result}")
        
        if "error" in create_result:
            await status_message.edit_text(f"❌ Ошибка {('создания' if api_operation=='create' else 'обновления')} токена: {create_result.get('reason', create_result.get('error'))}")
            return
             
        # Получаем новый токен из результата
        new_token = create_result.get("h")  # В token/update имя токена возвращается в поле "h"
        if not new_token:
            await status_message.edit_text(f"❌ Не удалось {('создать' if api_operation=='create' else 'обновить')} токен")
            return
             
        # Сохраняем новый токен как дочерний от исходного
        # Метод add_token в TokenStorage является синхронным
        token_storage.add_token(callback_query.from_user.id, new_token, parent_token=source_token)
        
        # Сохраняем информацию о токене
        token_info = {
            "user_name": login_result.get("au"),
            "expire_time": login_result.get("tm"),
            "created_at": int(time.time()),
            "created_via": "api",  # Помечаем, что токен создан через API
            "token_type": api_operation  # create или update
        }
        token_storage.update_token_info(callback_query.from_user.id, new_token, token_info)
        
        await status_message.edit_text(
            f"✅ Токен успешно {('создан' if api_operation=='create' else 'обновлен')} через API!\n\n"
            f"🔑 <code>{new_token}</code>",
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logger.error(f"Error creating token: {e}")
        await callback_query.message.edit_text(f"❌ Произошла ошибка: {str(e)}")

@dp.message(Command(commands=['token_create']))
async def token_create_command(message: types.Message, state: FSMContext):
    """Создать новый токен через API (на основе существующего токена)."""
    # Получаем последний токен пользователя
    user_tokens = token_storage.get_user_tokens(message.from_user.id)
    
    # Создаем клавиатуру для выбора токена
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    
    # Добавляем кнопку для ввода токена вручную
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(
            text="✏️ Ввести токен вручную", 
            callback_data="api_create_token_manual"
        )
    ])
    
    # Добавляем кнопки для имеющихся токенов, если они есть
    if user_tokens:
        for i, token_data in enumerate(user_tokens[:5]):  # Не более 5 токенов
            token = token_data["token"]
            token_preview = f"{token[:10]}...{token[-10:]}" if len(token) > 25 else token
            
            # Если есть имя пользователя, добавляем его
            user_info = ""
            if "user_name" in token_data:
                user_info = f" ({token_data['user_name']})"
            
            keyboard.inline_keyboard.insert(i, [
                types.InlineKeyboardButton(
                    text=f"🔑 Токен #{i+1}{user_info}", 
                    callback_data=f"api_create_token:{i}"
                )
            ])
        
        message_text = "Выберите токен, на основе которого будет создан новый токен (через API):"
    else:
        message_text = "У вас нет сохраненных токенов. Введите токен для создания нового (через API):"
    
    await message.reply(
        message_text,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

@dp.callback_query(lambda c: c.data == "api_create_token_manual")
async def process_api_create_token_manual(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик для ручного ввода токена для создания нового через API."""
    await callback_query.answer()
    
    await callback_query.message.edit_text(
        "Пожалуйста, введите токен, на основе которого нужно создать новый (через API):\n\n"
        "<i>Формат: строка с токеном доступа Wialon</i>",
        parse_mode=ParseMode.HTML
    )
    
    # Устанавливаем состояние для ожидания ввода токена
    await state.set_state(GetTokenStates.waiting_for_api_source_token)

@dp.message(GetTokenStates.waiting_for_api_source_token)
async def process_api_source_token_input(message: types.Message, state: FSMContext):
    """Обработка ввода исходного токена для API создания."""
    source_token = message.text.strip()
    
    if not source_token:
        await message.reply("❌ Токен не может быть пустым. Пожалуйста, введите токен.")
        return
    
    # Сохраняем токен в состоянии
    await state.update_data(source_token=source_token)
    
    # Показываем выбор режима подключения
    await show_api_connection_choice(message, state, source_token)

async def show_api_connection_choice(message, state: FSMContext, token: str):
    """Показать выбор режима подключения для API создания/обновления токена."""
    await state.update_data(source_token=token)
    
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="🔒 Через Tor", callback_data="api_token_action:yes"),
                types.InlineKeyboardButton(text="🚀 Напрямую", callback_data="api_token_action:no")
            ]
        ]
    )
    
    # Проверяем, это сообщение или колбэк
    if hasattr(message, 'reply'):
        # Это сообщение Message
        await message.reply(
            f"Выберите режим подключения для работы с токеном:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )
    else:
        # Это сообщение от callback_query
        await message.edit_text(
            f"Выберите режим подключения для работы с токеном:",
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML
        )

@dp.callback_query(lambda c: c.data.startswith("api_create_token:"))
async def process_api_token_selection(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработка выбора токена из списка для API создания."""
    # Получаем индекс токена
    index = int(callback_query.data.split(":")[1])
    user_tokens = token_storage.get_user_tokens(callback_query.from_user.id)
    token = user_tokens[index]["token"]
    
    # Сохраняем выбранный токен и тип операции
    await state.update_data(source_token=token, api_operation="create")
    
    # Показываем выбор режима подключения
    await show_api_connection_choice(callback_query.message, state, token)

@dp.callback_query(lambda c: c.data.startswith("api_token_action:"))
async def process_api_token_action(callback_query: types.CallbackQuery, state: FSMContext):
    """Создание/обновление токена через API."""
    try:
        await callback_query.answer()
        use_tor = callback_query.data.split(":")[1] == "yes"
        
        data = await state.get_data()
        source_token = data.get("source_token")
        api_operation = data.get("api_operation", "create")  # По умолчанию - создание
        token_to_update = data.get("token_to_update")  # Токен для обновления (только для операции update)
        
        if not source_token:
            await callback_query.message.edit_text("❌ Токен не найден")
            return
             
        # Проверяем наличие токена для обновления при операции update
        if api_operation == "update" and not token_to_update:
            await callback_query.message.edit_text("❌ Токен для обновления не найден")
            return
            
        # Очищаем токен от URL и других лишних данных
        if isinstance(source_token, str):
            if "access_token=" in source_token:
                source_token = source_token.split("access_token=")[1].split("&")[0]
            elif source_token.startswith("{") and "token" in source_token:
                try:
                    token_data = json.loads(source_token)
                    source_token = token_data.get("token", source_token)
                except:
                    pass
        
        # Также очищаем токен для обновления, если он есть
        if api_operation == "update" and isinstance(token_to_update, str):
            if "access_token=" in token_to_update:
                token_to_update = token_to_update.split("access_token=")[1].split("&")[0]
            elif token_to_update.startswith("{") and "token" in token_to_update:
                try:
                    token_data = json.loads(token_to_update)
                    token_to_update = token_data.get("token", token_to_update)
                except:
                    pass
        
        status_message = await callback_query.message.edit_text(
            f"🔄 {('Создаем' if api_operation=='create' else 'Обновляем')} токен {'через Tor' if use_tor else 'напрямую'}..."
        )
        
        # Получаем URL API
        wialon_api_url = get_env_variable("WIALON_API_URL", "https://hst-api.wialon.com/wialon/ajax.html")
        
        # 1. Логин через token/login
        login_params = {
            "svc": "token/login",
            "params": json.dumps({
                "token": source_token,
                "fl": 7  # Используем флаг 7, чтобы получить полную информацию, включая user_id
            })
        }
        
        logger.debug(f"Login params: {login_params}")
        login_result = await make_api_request(wialon_api_url, login_params, use_tor)
        logger.debug(f"Login result: {login_result}")
        
        if "error" in login_result:
            await status_message.edit_text(f"❌ Ошибка авторизации: {login_result.get('error')}")
            return
             
        # Получаем eid из результата логина
        session_id = login_result.get("eid")
        if not session_id:
            await status_message.edit_text("❌ Не удалось получить ID сессии")
            return
        
        # Получаем user_id напрямую из ответа token/login
        user_id = login_result.get("user", {}).get("id")
        if not user_id:
            await status_message.edit_text("❌ Не удалось получить ID пользователя из ответа")
            return
        
        logger.debug(f"Полученный ID сессии: {session_id}")
        logger.debug(f"Полученный ID пользователя: {user_id}")
        
        # 2. Создание/обновление токена через token/update
        params = {
            "callMode": api_operation,  # "create" или "update"
            "userId": str(user_id),     # обязательно в виде строки
            "h": "TOKEN" if api_operation == "create" else token_to_update,  # Для обновления используем существующий токен
            "app": "Wialon Hosting – a platform for GPS monitoring",
            "at": 0,
            "dur": 0,
            "fl": 8192,
            "p": "{}",  # именно строка "{}"
            "items": []
        }
        
        create_params = {
            "svc": "token/update",  # Используем token/update как в примере
            "params": json.dumps(params),
            "sid": session_id
        }
        
        logger.debug(f"Create params: {create_params}")
        create_result = await make_api_request(wialon_api_url, create_params, use_tor)
        logger.debug(f"Create result: {create_result}")
        
        if "error" in create_result:
            await status_message.edit_text(f"❌ Ошибка {('создания' if api_operation=='create' else 'обновления')} токена: {create_result.get('reason', create_result.get('error'))}")
            return
             
        # Получаем новый токен из результата
        new_token = create_result.get("h")  # В token/update имя токена возвращается в поле "h"
        if not new_token:
            await status_message.edit_text(f"❌ Не удалось {('создать' if api_operation=='create' else 'обновить')} токен")
            return
             
        # Сохраняем новый токен как дочерний от исходного
        # Метод add_token в TokenStorage является синхронным
        if api_operation == "create":
            # При создании указываем исходный токен как родительский
            token_storage.add_token(callback_query.from_user.id, new_token, parent_token=source_token)
        else:
            # При обновлении сохраняем информацию об обоих токенах
            token_storage.add_token(callback_query.from_user.id, new_token, parent_token=token_to_update)
        
        # Сохраняем информацию о токене
        token_info = {
            "user_name": login_result.get("au"),
            "expire_time": login_result.get("tm"),
            "created_at": int(time.time()),
            "created_via": "api",  # Помечаем, что токен создан через API
            "token_type": api_operation  # create или update
        }
        token_storage.update_token_info(callback_query.from_user.id, new_token, token_info)
        
        await status_message.edit_text(
            f"✅ Токен успешно {('создан' if api_operation=='create' else 'обновлен')} через API!\n\n"
            f"🔑 <code>{new_token}</code>",
            parse_mode=ParseMode.HTML
        )
        
    except Exception as e:
        logger.error(f"Error in API token operation: {e}")
        await callback_query.message.edit_text(f"❌ Произошла ошибка: {str(e)}")

@dp.message(Command(commands=['token_update']))
async def token_update_command(message: types.Message, state: FSMContext):
    """Обновить существующий токен через API."""
    # Сначала выбираем исходный токен (для авторизации)
    user_tokens = token_storage.get_user_tokens(message.from_user.id)
    
    # Создаем клавиатуру для выбора токена
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    
    # Добавляем кнопку для ввода токена вручную
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(
            text="✏️ Ввести токен вручную", 
            callback_data="api_update_token_manual"
        )
    ])
    
    # Добавляем кнопки для имеющихся токенов, если они есть
    if user_tokens:
        for i, token_data in enumerate(user_tokens[:5]):  # Не более 5 токенов
            token = token_data["token"]
            token_preview = f"{token[:10]}...{token[-10:]}" if len(token) > 25 else token
            
            # Если есть имя пользователя, добавляем его
            user_info = ""
            if "user_name" in token_data:
                user_info = f" ({token_data['user_name']})"
            
            keyboard.inline_keyboard.insert(i, [
                types.InlineKeyboardButton(
                    text=f"🔑 Токен #{i+1}{user_info}", 
                    callback_data=f"api_update_token:{i}"
                )
            ])
        
        message_text = "Выберите <b>исходный токен</b> для авторизации (источник):"
    else:
        message_text = "У вас нет сохраненных токенов. Введите <b>исходный токен</b> для авторизации:"
    
    await message.reply(
        message_text,
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

@dp.callback_query(lambda c: c.data == "api_update_token_manual")
async def process_api_update_token_manual(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик для ручного ввода токена для обновления через API."""
    await callback_query.answer()
    
    await callback_query.message.edit_text(
        "Пожалуйста, введите <b>исходный токен</b> для авторизации:\n\n"
        "<i>Формат: строка с токеном доступа Wialon</i>",
        parse_mode=ParseMode.HTML
    )
    
    # Устанавливаем состояние для ожидания ввода токена
    await state.set_state(GetTokenStates.waiting_for_api_update_token)

@dp.message(GetTokenStates.waiting_for_api_update_token)
async def process_api_update_token_input(message: types.Message, state: FSMContext):
    """Обработка ввода токена для API обновления."""
    source_token = message.text.strip()
    
    if not source_token:
        await message.reply("❌ Токен не может быть пустым. Пожалуйста, введите токен.")
        return
    
    # Сохраняем исходный токен в состоянии
    await state.update_data(source_token=source_token)
    
    # Теперь запрашиваем токен для обновления
    await message.reply(
        "Теперь введите <b>токен для обновления</b> (который нужно обновить):",
        parse_mode=ParseMode.HTML
    )
    
    # Устанавливаем состояние для ожидания ввода токена для обновления
    await state.set_state(GetTokenStates.waiting_for_token_to_update)

@dp.message(GetTokenStates.waiting_for_token_to_update)
async def process_token_to_update_input(message: types.Message, state: FSMContext):
    """Обработка ввода токена, который нужно обновить."""
    token_to_update = message.text.strip()
    
    if not token_to_update:
        await message.reply("❌ Токен не может быть пустым. Пожалуйста, введите токен для обновления.")
        return
    
    # Сохраняем токен для обновления и тип операции
    await state.update_data(token_to_update=token_to_update, api_operation="update")
    
    # Показываем выбор режима подключения
    data = await state.get_data()
    source_token = data.get("source_token")
    await show_api_connection_choice(message, state, source_token)

@dp.callback_query(lambda c: c.data.startswith("api_update_token:"))
async def process_api_update_token_selection(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработка выбора исходного токена из списка."""
    # Получаем индекс токена
    index = int(callback_query.data.split(":")[1])
    user_tokens = token_storage.get_user_tokens(callback_query.from_user.id)
    token = user_tokens[index]["token"]
    
    # Сохраняем выбранный исходный токен
    await state.update_data(source_token=token)
    
    # Создаем клавиатуру для выбора токена для обновления
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[])
    
    # Добавляем кнопку для ввода токена вручную
    keyboard.inline_keyboard.append([
        types.InlineKeyboardButton(
            text="✏️ Ввести токен вручную", 
            callback_data="token_to_update_manual"
        )
    ])
    
    # Добавляем кнопки для других токенов, исключая выбранный
    added_tokens = 0
    for i, token_data in enumerate(user_tokens):
        # Пропускаем уже выбранный исходный токен
        if i == index:
            continue
            
        # Ограничиваем до 5 токенов
        if added_tokens >= 5:
            break
            
        token_to_update = token_data["token"]
        token_preview = f"{token_to_update[:10]}...{token_to_update[-10:]}" if len(token_to_update) > 25 else token_to_update
        
        # Если есть имя пользователя, добавляем его
        user_info = ""
        if "user_name" in token_data:
            user_info = f" ({token_data['user_name']})"
        
        keyboard.inline_keyboard.append([
            types.InlineKeyboardButton(
                text=f"🔑 Токен #{i+1}{user_info}", 
                callback_data=f"token_to_update:{i}"
            )
        ])
        added_tokens += 1
    
    # Показываем клавиатуру с выбором токена для обновления
    await callback_query.message.edit_text(
        "Теперь выберите <b>токен для обновления</b>:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

@dp.callback_query(lambda c: c.data == "token_to_update_manual")
async def process_token_to_update_manual(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик для ручного ввода токена, который нужно обновить."""
    await callback_query.answer()
    
    await callback_query.message.edit_text(
        "Пожалуйста, введите <b>токен для обновления</b>:\n\n"
        "<i>Формат: строка с токеном доступа Wialon</i>",
        parse_mode=ParseMode.HTML
    )
    
    # Устанавливаем состояние для ожидания ввода токена
    await state.set_state(GetTokenStates.waiting_for_token_to_update)

@dp.callback_query(lambda c: c.data.startswith("token_to_update:"))
async def process_token_to_update_selection(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработка выбора токена для обновления из списка."""
    # Получаем индекс токена
    index = int(callback_query.data.split(":")[1])
    user_tokens = token_storage.get_user_tokens(callback_query.from_user.id)
    token_to_update = user_tokens[index]["token"]
    
    # Сохраняем выбранный токен для обновления и тип операции
    await state.update_data(token_to_update=token_to_update, api_operation="update")
    
    # Показываем выбор режима подключения
    data = await state.get_data()
    source_token = data.get("source_token")
    await show_api_connection_choice(callback_query.message, state, source_token)

@dp.callback_query(lambda c: c.data == "use_saved_credentials")
async def process_use_saved_credentials(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик для использования сохраненных учетных данных."""
    await callback_query.answer()
    
    # Получаем сохраненные учетные данные
    credentials = token_storage.get_credentials(callback_query.from_user.id)
    if not credentials:
        await callback_query.message.edit_text("❌ Сохраненные данные не найдены или повреждены.")
        return
    
    # Спрашиваем, какой режим подключения использовать
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="🔒 Через Tor", callback_data="saved_creds_tor:yes"),
                types.InlineKeyboardButton(text="🚀 Напрямую", callback_data="saved_creds_tor:no")
            ]
        ]
    )
    
    await callback_query.message.edit_text(
        f"Используем сохраненные данные для <b>{credentials['username']}</b>.\n\n"
        "Выберите режим подключения:",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML
    )

@dp.callback_query(lambda c: c.data.startswith("saved_creds_tor:"))
async def process_saved_creds_connection(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик для выбора режима подключения с сохраненными данными."""
    await callback_query.answer()
    
    # Определяем, использовать ли Tor
    use_tor = callback_query.data.split(":")[1] == "yes"
    
    # Получаем сохраненные учетные данные
    credentials = token_storage.get_credentials(callback_query.from_user.id)
    if not credentials:
        await callback_query.message.edit_text("❌ Сохраненные данные не найдены или повреждены.")
        return
    
    # Отображаем сообщение о процессе
    status_message = await callback_query.message.edit_text(
        f"🔄 Получаем токен для <b>{credentials['username']}</b> {'через Tor' if use_tor else 'напрямую'}...",
        parse_mode=ParseMode.HTML
    )
    
    try:
        # Получаем URL Wialon из переменных окружения
        try:
            wialon_url = get_env_variable("WIALON_BASE_URL")
        except:
            wialon_url = "https://hosting.wialon.com/login.html?duration=0"
            
        # Запускаем процесс авторизации с сохраненными данными
        result = await wialon_login_and_get_url(
            credentials['username'], 
            credentials['password'], 
            wialon_url,
            use_tor=use_tor
        )
        
        # Проверяем, что получили строку (старый формат) или словарь (новый формат)
        if isinstance(result, dict):
            token = result.get("token", "")
            full_url = result.get("url", "")
        else:
            # Обратная совместимость
            token = extract_token_from_url(result)
            full_url = result
        
        if token:
            token_storage.add_token(callback_query.from_user.id, token)
            
            # Сохраняем информацию о токене
            token_info = {
                "user_name": credentials['username'],
                "created_at": int(time.time()),
                "created_via": "saved_credentials"
            }
            token_storage.update_token_info(callback_query.from_user.id, token, token_info)
            
            # Формируем текст сообщения
            url_info = f"\n\n🌐 <b>URL:</b>\n<code>{full_url}</code>" if full_url else ""
            
            await status_message.edit_text(
                f"✅ Токен успешно получен и сохранен!\n\n"
                f"🔑 <code>{token}</code>"
                f"{url_info}",
                parse_mode=ParseMode.HTML
            )
        else:
            # В случае, если токен не был извлечен
            url_display = full_url if isinstance(full_url, str) else str(result)
            await status_message.edit_text(
                f"⚠️ Не удалось извлечь токен из полученного результата.\n\n"
                f"Результат: <code>{url_display}</code>",
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"Error using saved credentials: {e}")
        await status_message.edit_text(
            f"❌ Ошибка при получении токена: {str(e)}",
            parse_mode=ParseMode.HTML
        )

@dp.callback_query(lambda c: c.data == "delete_saved_credentials")
async def process_delete_credentials(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик для удаления сохраненных учетных данных."""
    await callback_query.answer()
    
    # Удаляем учетные данные
    token_storage.delete_credentials(callback_query.from_user.id)
    
    # Возвращаемся к обычному выбору режима подключения
    keyboard = types.InlineKeyboardMarkup(
        inline_keyboard=[
            [
                types.InlineKeyboardButton(text="🔒 Через Tor", callback_data="use_tor:yes"),
                types.InlineKeyboardButton(text="🚀 Напрямую", callback_data="use_tor:no")
            ]
        ]
    )
    
    await callback_query.message.edit_text(
        "✅ Сохраненные данные удалены.\n\n"
        "Выберите режим подключения к Wialon:",
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data.startswith("save_credentials:"))
async def process_save_credentials(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик для сохранения учетных данных."""
    await callback_query.answer()
    
    # Извлекаем учетные данные из callback_data
    parts = callback_query.data.split(":", 2)  # Ограничиваем до 3 частей
    if len(parts) != 3:
        await callback_query.message.edit_text("❌ Ошибка в данных для сохранения.")
        return
    
    username = parts[1]
    password = parts[2]
    
    # Сохраняем учетные данные
    try:
        token_storage.save_credentials(callback_query.from_user.id, username, password)
    except Exception as e:
        logger.error(f"Ошибка при сохранении учетных данных: {e}")
        await callback_query.message.edit_text(
            "❌ Не удалось сохранить учетные данные. Попробуйте позже.",
            parse_mode=ParseMode.HTML
        )
        return
    
    # Обновляем сообщение, удаляя кнопки и добавляя информацию о сохранении
    current_text = callback_query.message.text
    if "Сохранить учетные данные" in current_text:
        new_text = current_text.split("\n\nСохранить учетные данные")[0]
    else:
        new_text = current_text
        
    new_text += "\n\n✅ Учетные данные сохранены для быстрого входа."
    
    await callback_query.message.edit_text(
        new_text,
        parse_mode=ParseMode.HTML
    )

@dp.callback_query(lambda c: c.data == "not_save_credentials")
async def process_not_save_credentials(callback_query: types.CallbackQuery, state: FSMContext):
    """Обработчик для отказа от сохранения учетных данных."""
    await callback_query.answer()
    
    # Убираем кнопки, оставляем исходный текст
    current_text = callback_query.message.text
    if "Сохранить учетные данные" in current_text:
        new_text = current_text.split("\n\nСохранить учетные данные")[0]
    else:
        new_text = current_text
    
    await callback_query.message.edit_text(
        new_text,
        parse_mode=ParseMode.HTML
    )

@dp.message(Command(commands=['export_tokens']))
async def export_tokens_command(message: types.Message):
    """Экспортировать токены в CSV-файл."""
    user_tokens = token_storage.get_user_tokens(message.from_user.id)
    
    if not user_tokens:
        await message.reply("У вас нет сохраненных токенов для экспорта.")
        return
    
    # Создаем CSV в памяти
    output = io.StringIO()
    csv_writer = csv.writer(output)
    
    # Добавляем заголовки
    headers = ["Token", "User", "Created At", "Expires At", "Created Via", 
               "Operation Type", "Parent Token", "Days Left", "Status"]
    csv_writer.writerow(headers)
    
    # Добавляем данные о токенах
    for token_data in user_tokens:
        token = token_data["token"]
        user_name = token_data.get("user_name", "")
        created_at = datetime.datetime.fromtimestamp(token_data.get("created_at", 0)).strftime('%Y-%m-%d %H:%M:%S') if "created_at" in token_data else ""
        
        # Обрабатываем срок действия
        expires_at = ""
        days_left = ""
        status = "Active"
        if "expire_time" in token_data and token_data["expire_time"]:
            expire_time = int(token_data["expire_time"])
            expires_at = datetime.datetime.fromtimestamp(expire_time).strftime('%Y-%m-%d %H:%M:%S')
            
            if expire_time < time.time():
                status = "Expired"
                days_left = "0"
            else:
                days_left = str(int((expire_time - time.time()) / 86400))
        
        created_via = token_data.get("created_via", "")
        operation_type = token_data.get("token_type", "")
        parent_token = token_data.get("parent_token", "")
        
        # Записываем строку в CSV
        csv_writer.writerow([
            token, user_name, created_at, expires_at, created_via, 
            operation_type, parent_token, days_left, status
        ])
    
    # Перемещаем указатель в начало файла
    output.seek(0)
    
    # Создаем имя файла
    current_time = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"wialon_tokens_{current_time}.csv"
    
    # Отправляем файл пользователю
    await message.reply_document(
        types.BufferedInputFile(
            output.getvalue().encode('utf-8'),
            filename=filename
        ),
        caption=f"📊 Экспортировано {len(user_tokens)} токенов"
    )
    
    # Закрываем StringIO
    output.close()

async def start_telegram_bot():
    """Запускает Telegram бота."""
    logger.info("Starting Telegram bot...")
    await dp.start_polling(bot)

async def main():
    """Основная функция для запуска бота."""
    await start_telegram_bot()

if __name__ == '__main__':
    asyncio.run(main())