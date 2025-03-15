from loguru import logger
import os
from typing import Optional

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