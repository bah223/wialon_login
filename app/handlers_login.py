from aiogram import Router, types
import logging

router = Router()
logger = logging.getLogger(__name__)

# Все обработчики, завязанные на GetTokenStates, удалены
# Если нужны другие функции (например, для админки), их можно добавить ниже
