import sys
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Добавляем корневую директорию проекта в Python path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from app.bot import main

if __name__ == "__main__":
    main()
