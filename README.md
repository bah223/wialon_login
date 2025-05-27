# Wialon Token Manager Bot

Telegram бот для управления токенами доступа к Wialon. Бот позволяет:
- Получать новые токены доступа к Wialon
- Просматривать список сохраненных токенов
- Удалять токены
- Проверять статус и срок действия токенов
- Работать с объектами Wialon через API

## Основные возможности

- 📝 Автоматическая авторизация в Wialon
- 🔒 Безопасное хранение учетных данных
- 🔄 Управление токенами (просмотр, удаление)
- 🔍 Проверка срока действия токенов
- 🤖 Удобный Telegram интерфейс

## Технологии

- Python 3.9+
- aiogram 3.x
- SQLAlchemy 2.0
- PostgreSQL
- Docker
- Docker Compose
- Tor (для анонимного доступа)

## Быстрый старт

### Требования

- Docker 20.10+
- Docker Compose 2.0+

### Установка

1. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/yourusername/wialon_token_bot.git
   cd wialon_token_bot/wialon_login
   ```

2. Создайте и настройте файл `.env`:
   ```bash
   cp .env.example .env
   # Отредактируйте .env, указав настройки бота и базы данных
   ```

3. Запустите приложение:
   ```bash
   docker-compose up -d --build
   ```

4. Проверьте логи:
   ```bash
   docker-compose logs -f
   ```

## Структура проекта

```
wialon_login/
├── app/                  # Исходный код приложения
│   ├── __init__.py
│   ├── bot.py            # Основной файл бота
│   ├── config.py         # Конфигурация
│   ├── database.py       # Настройки базы данных
│   ├── models.py         # Модели SQLAlchemy
│   ├── handlers/         # Обработчики команд
│   └── utils/            # Вспомогательные функции
├── alembic/             # Миграции базы данных
├── data/                # Данные приложения (не в репозитории)
├── screenshots/         # Скриншоты (не в репозитории)
├── .env                 # Переменные окружения (не в репозитории)
├── .gitignore           # Игнорируемые файлы
├── docker-compose.yml    # Конфигурация Docker Compose
├── Dockerfile           # Конфигурация Docker
└── README.md            # Документация
```

## Переменные окружения

Скопируйте `.env.example` в `.env` и настройте следующие переменные:

```
# Telegram Bot settings
BOT_TOKEN=your_telegram_bot_token
ALLOWED_USERS="user1_id,user2_id"  # ID пользователей, которым разрешен доступ

# Wialon credentials
WIALON_USERNAME=your_wialon_username
WIALON_PASSWORD=your_wialon_password
WIALON_BASE_URL=https://hosting.wialon.com
WIALON_API_URL=https://hst-api.wialon.com/wialon/ajax.html

# Database settings
DB_HOST=db
DB_PORT=5432
DB_NAME=wialon_db
DB_USER=wialon
DB_PASSWORD=wialonpass
```

## Команды бота

- `/start` - Начать работу с ботом
- `/help` - Показать справку
- `/get_token` - Получить новый токен
- `/list_tokens` - Показать список токенов
- `/delete_token` - Удалить токен
- `/check_token` - Проверить статус токена

## Лицензия

MIT

## Автор

Ваше имя <your.email@example.com>

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
