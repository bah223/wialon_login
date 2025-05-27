import sys
from pathlib import Path
from dotenv import load_dotenv
import asyncio

# Загружаем переменные окружения из .env файла
load_dotenv()

# Добавляем корневую директорию проекта в Python path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from app.bot import main

if __name__ == "__main__":
    asyncio.run(main())
