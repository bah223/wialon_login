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
    
    def add_token(self, user_id: int, token: str, parent_token: str = None) -> None:
        """Добавляет токен в хранилище.
        
        Args:
            user_id: ID пользователя Telegram
            token: Токен доступа
            parent_token: Исходный токен, на основе которого был создан новый токен
        """
        # Преобразуем аргументы в нужные типы
        user_id = int(user_id) if user_id is not None else 0
        token = str(token) if token is not None else ""
        
        # Проверяем валидность токена
        if not token:
            logger.error("Attempted to add empty token")
            return
        
        if token in self.tokens:
            logger.info(f"Token {token[:8]}... already exists, updating...")
            # Обновляем существующий токен
            self.tokens[token]["updated_at"] = time.time()
            if parent_token:
                self.tokens[token]["parent_token"] = parent_token
        else:
            # Добавляем новый токен
            self.tokens[token] = {
                "user_id": user_id,
                "created_at": time.time(),
                "updated_at": time.time(),
                "parent_token": parent_token
            }

        # Вывод состояния хранилища для отладки
        logger.info(f"Token storage now contains {len(self.tokens)} tokens")
        # Выводим первые несколько символов всех ключей для отладки
        token_keys = [k[:8] + "..." for k in self.tokens.keys()]
        logger.debug(f"Token keys: {token_keys}")
                
        logger.info(f"Token added for user {user_id}")
        self._save_tokens()
    
    def update_token_data(self, token: str, data: Dict[str, Any]) -> bool:
        """Обновляет данные для существующего токена.
        
        Args:
            token: Токен доступа
            data: Новые данные для обновления
            
        Returns:
            bool: True если токен найден и обновлен, иначе False
        """
        if token in self.tokens:
            self.tokens[token].update(data)
            self.tokens[token]["last_used"] = time.time()
            logger.info(f"Token data updated for token {token[:5]}...")
            self._save_tokens()
            return True
        
        logger.warning(f"Attempted to update non-existent token {token[:5]}...")
        return False
    
    def get_token_data(self, token: str) -> Optional[Dict[str, Any]]:
        """Получает данные для указанного токена.
        
        Args:
            token: Токен доступа
            
        Returns:
            Optional[Dict]: Данные токена или None, если токен не найден
        """
        if token in self.tokens:
            self.tokens[token]["last_used"] = time.time()
            self._save_tokens()
            return self.tokens[token]
        
        return None
    
    def get_user_tokens(self, user_id: int) -> List[Dict[str, Any]]:
        """Получает все токены пользователя.
        
        Args:
            user_id: ID пользователя Telegram
            
        Returns:
            List[Dict]: Список токенов с их данными
        """
        user_tokens = []
        
        for token, data in self.tokens.items():
            if data.get("user_id") == user_id:
                user_tokens.append({
                    "token": token,
                    **data
                })
        
        return sorted(user_tokens, key=lambda x: x.get("created_at", 0), reverse=True)
    
    def delete_token(self, token: str) -> bool:
        """Удаляет токен из хранилища.
        
        Args:
            token: Токен для удаления
            
        Returns:
            bool: True если токен найден и удален, иначе False
        """
        if token in self.tokens:
            del self.tokens[token]
            logger.info(f"Token {token[:5]}... deleted")
            self._save_tokens()
            return True
        
        return False
    
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

    async def delete_all_user_tokens(self, user_id: int) -> None:
        """Удаляет все токены пользователя.
        
        Args:
            user_id: ID пользователя Telegram
        """
        user_id = int(user_id)
        tokens_to_delete = []
        
        # Находим все токены пользователя
        for token, data in self.tokens.items():
            if data.get("user_id") == user_id:
                tokens_to_delete.append(token)
        
        # Удаляем найденные токены
        for token in tokens_to_delete:
            del self.tokens[token]
        
        logger.info(f"Deleted all tokens for user {user_id} (total: {len(tokens_to_delete)})")
        self._save_tokens()

    def update_token_info(self, user_id, token, token_info):
        """
        Обновляет информацию о токене.
        
        Args:
            user_id: ID пользователя
            token: Токен доступа
            token_info: Словарь с дополнительной информацией о токене
        """
        user_id = str(user_id)
        
        if user_id not in self.tokens:
            logger.warning(f"Пользователь {user_id} не найден в хранилище токенов")
            return False
        
        # Находим токен в списке токенов пользователя
        for i, token_data in enumerate(self.tokens[user_id]):
            if token_data.get("token") == token:
                # Обновляем информацию о токене
                self.tokens[user_id][i].update(token_info)
                self._save_tokens()
                logger.info(f"Обновлена информация о токене для пользователя {user_id}")
                return True
        
        logger.warning(f"Токен не найден для пользователя {user_id}")
        return False


# Создаем глобальный экземпляр хранилища в памяти, без файла на диске
token_storage = TokenStorage() 