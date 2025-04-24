import json
import os
import time
from typing import Dict, List, Any, Optional
from app.utils import logger

class TokenStorage:
    """Класс для хранения и управления токенами доступа."""
    
    def __init__(self, storage_file: str = None):
        """Инициализирует хранилище токенов.
        
        Args:
            storage_file: Путь к файлу для хранения токенов
        """
        # Используем хранилище в памяти по умолчанию, избегая проблем с правами доступа
        self.storage_file = storage_file
        self.tokens: Dict[str, Dict[str, Any]] = {}
        if storage_file:
            self._load_tokens()
    
    def _load_tokens(self) -> None:
        """Загружает токены из файла."""
        if not self.storage_file:
            return
            
        try:
            # Создаем директорию, если её нет
            os.makedirs(os.path.dirname(self.storage_file), exist_ok=True)
            
            if os.path.exists(self.storage_file):
                with open(self.storage_file, 'r') as f:
                    self.tokens = json.load(f)
                logger.info(f"Loaded {len(self.tokens)} tokens from storage")
            else:
                logger.info("Token storage file not found, creating new storage")
                self.tokens = {}
                self._save_tokens()
        except Exception as e:
            logger.error(f"Error loading tokens: {e}")
            self.tokens = {}
    
    def _save_tokens(self) -> None:
        """Сохраняет токены в файл."""
        if not self.storage_file:
            return
            
        try:
            # Создаем директорию, если её нет
            os.makedirs(os.path.dirname(self.storage_file), exist_ok=True)
            
            with open(self.storage_file, 'w') as f:
                json.dump(self.tokens, f, indent=2)
            logger.debug(f"Tokens saved to {self.storage_file}")
        except Exception as e:
            logger.error(f"Error saving tokens: {e}")
    
    def clean_old_tokens(self, max_age_days: int = 30) -> int:
        """Удаляет старые токены.
        
        Args:
            max_age_days: Максимальный возраст токена в днях
            
        Returns:
            int: Количество удаленных токенов
        """
        now = time.time()
        max_age_seconds = max_age_days * 24 * 60 * 60
        tokens_to_delete = []
        
        for token, data in self.tokens.items():
            if now - data.get("created_at", 0) > max_age_seconds:
                tokens_to_delete.append(token)
        
        for token in tokens_to_delete:
            del self.tokens[token]
        
        if tokens_to_delete:
            logger.info(f"Removed {len(tokens_to_delete)} old tokens")
            self._save_tokens()
        
        return len(tokens_to_delete)