from loguru import logger
import os
from typing import Optional, List

def get_env_variable(var_name: str, default: Optional[str] = None) -> str:
    """
    Получение переменной окружения с возможностью указать значение по умолчанию.
    
    Args:
        var_name: Имя переменной окружения
        default: Значение по умолчанию, если переменная не найдена
        
    Returns:
        str: Значение переменной окружения или значение по умолчанию
        
    Raises:
        ValueError: Если переменная не найдена и не указано значение по умолчанию
    """
    value = os.getenv(var_name)
    # Логируем результат с маскированием для безопасности
    masked_value = value[:5] + "..." if value and len(value) > 5 else value
    logger.debug(f"Reading env variable '{var_name}': {masked_value}")
    if not value:
        logger.warning(f"Environment variable '{var_name}' not found")
        if default is not None:
            logger.debug(f"Using default value for '{var_name}'")
            return default
        raise ValueError(f"Environment variable '{var_name}' not set.")
    return value

def get_allowed_user_ids() -> List[int]:
    """
    Gets the list of allowed user IDs from the environment variable ALLOWED_USERS (comma or space separated).
    """
    user_ids_str = get_env_variable("ALLOWED_USERS", default="")
    if not user_ids_str:
        return []
    # Поддержка как запятой, так и пробела как разделителя
    user_ids = [uid.strip() for uid in user_ids_str.replace(',', ' ').split() if uid.strip().isdigit()]
    return [int(user_id) for user_id in user_ids]

def is_user_allowed(user_id: int) -> bool:
    """
    Checks if the given user ID is in the allowed user IDs list.
    """
    allowed_user_ids = get_allowed_user_ids()
    return user_id in allowed_user_ids

def get_bool_env_variable(var_name: str, default: bool = False) -> bool:
    """
    Получение булевой переменной окружения с возможностью указать значение по умолчанию.
    
    Функция преобразует строковое значение переменной окружения в булево значение.
    Строки "1", "true", "yes", "y", "on" (регистр не важен) преобразуются в True.
    Все остальные значения преобразуются в False.
    
    Args:
        var_name: Имя переменной окружения
        default: Значение по умолчанию, если переменная не найдена
        
    Returns:
        bool: Булево значение переменной окружения или значение по умолчанию
    """
    try:
        value = get_env_variable(var_name, str(default)).lower()
        return value in ("1", "true", "yes", "y", "on")
    except ValueError:
        return default
