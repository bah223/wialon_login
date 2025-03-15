from aiogram.fsm.state import State, StatesGroup

class GetTokenStates(StatesGroup):
    """Состояния для процесса получения токена."""
    connection_mode_choice = State()   # Выбор режима подключения: через Tor или напрямую
    manual_input_username = State()   # Ввод логина вручную
    manual_input_password = State()   # Ввод пароля вручную
    check_token_mode = State()        # Выбор режима для проверки токена
    waiting_for_token_input = State() # Ожидание ввода токена вручную
    waiting_for_source_token = State() # Ожидание ввода исходного токена для создания нового
