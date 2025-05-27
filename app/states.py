from aiogram.fsm.state import State, StatesGroup

class GetTokenStates(StatesGroup):
    """Состояния для процесса получения токена."""
    connection_mode_choice = State()   # Выбор режима подключения: через Tor или напрямую
    manual_input_username = State()   # Ввод логина вручную
    manual_input_password = State()   # Ввод пароля вручную
    check_token_mode = State()        # Выбор режима для проверки токена
    waiting_for_token_input = State() # Ожидание ввода токена вручную
    waiting_for_source_token = State() # Ожидание ввода исходного токена для создания нового
    waiting_for_api_source_token = State() # Ожидание ввода исходного токена для API создания
    waiting_for_api_update_token = State() # Ожидание ввода токена для API обновления
    waiting_for_token_to_update = State() # Ожидание ввода токена, который нужно обновить

class CustomTokenStates(StatesGroup):
    """Состояния для процесса создания кастомного токена."""
    waiting_for_source_token = State()  # Ожидание выбора исходного токена
    waiting_for_access_rights = State()  # Ожидание ввода прав доступа (uacl)
    waiting_for_duration = State()       # Ожидание ввода срока действия
    waiting_for_objects = State()        # Ожидание выбора объектов
    waiting_for_connection_mode = State() # Выбор режима подключения (Tor/прямой)
