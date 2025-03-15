# Wialon Login Bot

Telegram бот для автоматизации входа в систему Wialon, получения и управления токенами доступа.
Бот поддерживает анонимное подключение через сеть Tor для обеспечения приватности.

## Функциональность

- Автоматическая авторизация в системе Wialon с получением токена доступа
- Проверка валидности токена и получение информации о сроке его действия
- Продление срока действия токена (в работе)
- Удаление токенов (в работе)
- Просмотр списка сохраненных токенов
- Анонимный доступ к Wialon через сеть Tor
- Закрытие сессий Wialon

## Запуск с использованием Docker

### Предварительные требования

- Docker
- Docker Compose

### Шаги для запуска

1. Клонируйте репозиторий:
   ```
   git clone https://github.com/yourusername/wialon_login_bot.git
   cd wialon_login_bot
   ```

2. Создайте файл .env на основе .env.example:
   ```
   cp .env.example .env
   ```

3. Отредактируйте файл .env, указав ваш токен Telegram бота и другие настройки.

4. Запустите контейнеры:
   ```
   docker-compose up -d
   ```

5. Проверьте логи:
   ```
   docker-compose logs -f
   ```

### Остановка контейнеров

```
docker-compose down
```

## Использование

1. Найдите бота в Telegram по имени пользователя
2. Отправьте команду /start для начала работы
3. Используйте команду /get_token для получения токена доступа
4. Используйте команду /check_token для проверки токена

## Дополнительные команды

- /token_list - Список сохраненных токенов
- /delete_token - Удалить сохраненный токен
- /help - Показать справку

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/your-username/wialon_login.git
cd wialon_login
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Создайте файл `.env` и добавьте необходимые переменные окружения:
```
BOT_TOKEN=your_telegram_bot_token
WIALON_USERNAME=your_wialon_username
WIALON_PASSWORD=your_wialon_password
WIALON_BASE_URL=https://hosting.wialon.com/login.html?duration=0
WIALON_API_URL=https://hst-api.wialon.com/wialon/ajax.html
DATABASE_URL=sqlite:///./database.db
USE_TOR=false
DEBUG=True
LOG_LEVEL=DEBUG
```

4. Запустите бот:
```bash
python app/main.py
```

## Запуск с Docker

1. Убедитесь, что у вас установлены Docker и Docker Compose

2. Создайте файл `.env` на основе `.env.example`

3. Запустите контейнер:
```bash
docker-compose up -d
```

4. Просмотр логов:
```bash
docker-compose logs -f
```

5. Остановка контейнера:
```bash
docker-compose down
```

## Переменные окружения

- `BOT_TOKEN` - Токен вашего Telegram бота
- `WIALON_USERNAME` - Имя пользователя для доступа к Wialon
- `WIALON_PASSWORD` - Пароль для доступа к Wialon
- `WIALON_BASE_URL` - URL для входа в Wialon
- `WIALON_API_URL` - URL для API запросов к Wialon
- `USE_TOR` - Использовать ли Tor для анонимного доступа (true/false)
- `DEBUG` - Включение/выключение режима отладки
- `LOG_LEVEL` - Уровень логирования

## Структура проекта

```
wialon_login/
├── app/
│   ├── bot.py         # Логика Telegram бота
│   ├── main.py        # Основной файл приложения
│   ├── models.py      # Модели базы данных
│   ├── scraper.py     # Парсер данных Wialon
│   └── utils.py       # Вспомогательные функции
│   ├── states.py      # Состояния FSM для диалогов
│   └── storage.py     # Хранилище токенов
├── .env               # Файл с переменными окружения
├── .env.example       # Пример файла переменных окружения
├── .gitignore        # Игнорируемые Git файлы
├── tor/               # Конфигурация Tor
│   └── torrc          # Файл настроек Tor
├── README.md         # Документация проекта
├── start.sh          # Скрипт запуска приложения с Tor
├── Dockerfile        # Инструкции для сборки Docker образа
├── docker-compose.yml # Конфигурация Docker Compose
└── requirements.txt  # Зависимости проекта
```

## Использование Tor

Бот поддерживает анонимный доступ к Wialon через сеть Tor:

1. Включение Tor: установите переменную окружения `USE_TOR=true`
2. При запуске через Docker, Tor будет запущен автоматически
3. При локальном запуске требуется установленный Tor:
   - Ubuntu/Debian: `sudo apt install tor`
   - CentOS/RHEL: `sudo yum install tor`
   - Windows: Установите Tor Browser
4. Убедитесь, что Tor запущен и слушает порт 9050:
   - Linux/macOS: `sudo service tor start` или `sudo systemctl start tor`
   - Windows: запустите Tor Browser

### Проверка работы Tor

Чтобы проверить, работает ли Tor правильно, выполните следующую команду:

```bash
curl --socks5 127.0.0.1:9050 https://check.torproject.org/api/ip
```

Если вы видите ответ с IP-адресом и строкой "IsTor":true, значит Tor работает корректно.

### Преимущества и ограничения использования Tor

**Преимущества:**
- Скрывает ваш реальный IP-адрес от Wialon
- Повышает приватность и анонимность
- Может обойти некоторые региональные ограничения

**Ограничения:**
- Значительно снижает скорость работы
- Может быть блокирован некоторыми сервисами
- Не скрывает ваши учетные данные от самой системы Wialon

## Лицензия

MIT
