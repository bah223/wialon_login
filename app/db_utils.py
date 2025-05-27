from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models import User, MasterToken, TokenHistory, ChildToken, Object, TokenObjectAccess, SavedCredentials, WialonAccount, Token, TokenType, TokenCreationMethod
from sqlalchemy.exc import NoResultFound
from passlib.hash import bcrypt
from app.utils import encrypt_password, decrypt_password
import logging
import datetime
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
import json

logger = logging.getLogger(__name__)

async def get_user_by_username(session: AsyncSession, username: str):
    result = await session.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    return user

async def create_or_update_user(
    session: AsyncSession,
    telegram_id: int,
    username: str = None,
    wialon_username: str = None,
    wialon_password: str = None
) -> User:
    """
    Создает нового пользователя или обновляет существующего.
    
    Args:
        session: Сессия SQLAlchemy
        telegram_id: Telegram ID пользователя
        username: Telegram username
        wialon_username: Имя пользователя в Wialon
        wialon_password: Пароль в Wialon (будет зашифрован)
    
    Returns:
        User: Объект пользователя
    """
    try:
        # Ищем пользователя по Telegram ID
        user = await session.scalar(
            select(User).where(User.telegram_id == telegram_id)
        )
        
        if not user:
            # Создаем нового пользователя
            user = User(
                telegram_id=telegram_id,
                telegram_username=username,
                wialon_username=wialon_username,
                wialon_password=bcrypt.hash(wialon_password) if wialon_password else None
            )
            session.add(user)
        else:
            # Обновляем существующего пользователя
            if username:
                user.telegram_username = username
            if wialon_username:
                user.wialon_username = wialon_username
            if wialon_password:
                user.wialon_password = bcrypt.hash(wialon_password)
        
        await session.commit()
        return user
        
    except Exception as e:
        logger.error(f"Error creating/updating user: {e}")
        await session.rollback()
        raise

async def get_user_by_telegram_id(session: AsyncSession, telegram_id: str):
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalars().first()

async def create_or_update_user_by_telegram(session: AsyncSession, telegram_id: str, username: str, password: str):
    user = await get_user_by_telegram_id(session, telegram_id)
    hashed_password = bcrypt.hash(password)
    if user:
        user.username = username
        user.hashed_password = hashed_password
    else:
        user = User(telegram_id=telegram_id, username=username, hashed_password=hashed_password)
        session.add(user)
    await session.commit()
    return user

async def get_all_user_tokens(session: AsyncSession) -> list:
    """Получить все токены из истории с группировкой."""
    try:
        # Получаем все токены
        tokens = await session.scalars(
            select(Token).order_by(Token.created_at.desc())
        )
        
        result = []
        for token in tokens:
            token_info = {
                "token": token.token,
                "type": token.token_type.value,
                "creation_method": token.creation_method.value,
                "created_at": token.created_at.isoformat(),
                "status": token.status
            }
            
            # Добавляем информацию об аккаунте, если есть
            if token.account_id:
                account = await session.get(WialonAccount, token.account_id)
                if account:
                    token_info["username"] = account.username
            
            # Для дочерних токенов добавляем родительский
            if token.parent_token_id:
                parent = await session.get(Token, token.parent_token_id)
                if parent:
                    token_info["parent_token"] = parent.token
            
            # Добавляем дополнительную информацию из метаданных токена
            if token.token_metadata:
                token_info.update(token.token_metadata)
            
            result.append(token_info)
        
        return result
    except Exception as e:
        logger.error(f"Error getting all tokens: {e}")
        return []

async def add_token_history(session: AsyncSession, token_data: dict) -> None:
    """Добавить запись в историю токенов."""
    user_id = None
    if token_data.get("user_name"):
        user = await get_user_by_username(session, token_data["user_name"])
        if user:
            user_id = user.id
        else:
            user = User(username=token_data["user_name"])
            session.add(user)
            await session.commit()
            user_id = user.id

    # Новый блок: ищем или создаём токен, чтобы получить token_id
    token_id = None
    token_str = token_data.get("token")
    if token_str:
        token_obj = await session.scalar(select(Token).where(Token.token == token_str))
        if not token_obj:
            # Создаём токен с минимально необходимыми полями (тип и способ создания по умолчанию)
            token_obj = Token(
                token=token_str,
                token_type=TokenType.MASTER,  # или TokenType.CHILD, если нужно, можно доработать
                creation_method=TokenCreationMethod.MANUAL
            )
            session.add(token_obj)
            await session.commit()
        token_id = token_obj.id

    token_history = TokenHistory(
        user_id=user_id or 1,  # Используем 1 как дефолтный ID для системных операций
        token_id=token_id,
        master_token_id=token_data.get("master_token_id"),
        child_token_id=token_data.get("child_token_id"),
        action=token_data.get("action", "create"),
        created_at=datetime.datetime.now(),
        details=token_data if isinstance(token_data, dict) else {"data": str(token_data)}
    )
    session.add(token_history)
    await session.commit()

async def get_all_logins(session: AsyncSession) -> list[str]:
    """Получить список всех сохраненных логинов."""
    query = select(SavedCredentials.login)
    result = await session.execute(query)
    return [row[0] for row in result.all()]

async def get_password_by_login(session: AsyncSession, login: str) -> str:
    """Получить пароль для указанного логина."""
    query = select(SavedCredentials).where(SavedCredentials.login == login)
    result = await session.execute(query)
    credentials = result.scalar_one_or_none()
    return credentials.password if credentials else None

async def save_credentials(session: AsyncSession, login: str, password: str) -> None:
    """Сохранить учетные данные."""
    # Сначала создаем или получаем пользователя
    user = await create_or_update_user(session, login, password)
    
    # Теперь сохраняем учетные данные
    credentials = SavedCredentials(
        user_id=user.id,
        login=login,
        password=password,
        created_at=datetime.datetime.now()
    )
    session.add(credentials)
    await session.commit()

async def save_wialon_credentials(
    session: AsyncSession,
    username: str,
    password: str
) -> WialonAccount:
    """Сохранить учетные данные Wialon"""
    try:
        logger.debug(f"[save_wialon_credentials] TRY TO SAVE: username={username}, password={'***' if password else None}")
        account = await session.scalar(
            select(WialonAccount).where(WialonAccount.username == username)
        )
        if account:
            logger.debug(f"[save_wialon_credentials] UPDATE EXISTING: {account}")
            account.encrypted_password = encrypt_password(password)
            account.last_used = datetime.datetime.utcnow()
        else:
            logger.debug(f"[save_wialon_credentials] CREATE NEW ACCOUNT for username={username}")
            account = WialonAccount(
                username=username,
                encrypted_password=encrypt_password(password)
            )
            session.add(account)
        await session.commit()
        logger.debug(f"[save_wialon_credentials] SUCCESS: {account}")
        return account
    except Exception as e:
        logger.error(f"Error saving Wialon credentials: {e}")
        await session.rollback()
        raise

async def save_token_chain(
    session: AsyncSession,
    username: str = None,
    password: str = None,
    master_token: str = None,
    child_token: str = None,
    creation_method: str = "LOGIN",
    access_rights: int = None,
    duration: int = None,
    expires_at: datetime.datetime = None,
    token_metadata: dict = None
) -> bool:
    """Сохранить цепочку токенов"""
    try:
        logger.debug("[save_token_chain] username=%s, password=%s, master_token=%s, child_token=%s, creation_method=%s, access_rights=%s, duration=%s, expires_at=%s, token_metadata=%s", username, '***' if password else None, master_token, child_token, creation_method, access_rights, duration, expires_at, token_metadata)
        # Если есть учетные данные - сохраняем их
        account = None
        if username and password:
            logger.debug("[save_token_chain] Before save_wialon_credentials")
            account = await save_wialon_credentials(session, username, password)
            logger.debug("[save_token_chain] After save_wialon_credentials: account=%s", account)
        
        # Если есть мастер-токен - сохраняем его
        parent_token = None
        if master_token:
            logger.debug("[save_token_chain] Before session.scalar(master_token)")
            parent_token = await session.scalar(
                select(Token).where(Token.token == master_token)
            )
            logger.debug("[save_token_chain] After session.scalar(master_token): parent_token=%s", parent_token)
            if not parent_token:
                parent_token = Token(
                    token=master_token,
                    token_type=TokenType.MASTER,
                    creation_method=TokenCreationMethod.LOGIN if account else TokenCreationMethod.MANUAL,
                    account_id=account.id if account else None,
                    access_rights=str(access_rights) if access_rights else None
                )
                session.add(parent_token)
                await session.flush()  # Гарантируем, что у master_token есть id
                logger.debug("[save_token_chain] After session.flush (master_token)")
        
        # Если есть дочерний токен - сохраняем его и привязываем к мастер-токену
        child = None
        if child_token:
            logger.debug("[save_token_chain] Before Token(child_token)")
            if not parent_token:
                raise ValueError("Нельзя сохранить дочерний токен без мастер-токена! Передайте master_token.")
            child = Token(
                token=child_token,
                token_type=TokenType.CHILD,
                creation_method=TokenCreationMethod[creation_method.upper()],
                parent_token_id=parent_token.id,
                access_rights=str(access_rights) if access_rights else None,
                expires_at=expires_at,
                token_metadata={
                    "duration": duration,
                    **(token_metadata or {})
                }
            )
            session.add(child)
            await session.flush()  # Гарантируем, что у child есть id
            logger.debug("[save_token_chain] After Token(child_token): child=%s", child)
        
        # Сохраняем историю
        if child:
            logger.debug("[save_token_chain] Before TokenHistory (child)")
            history = TokenHistory(
                token_id=child.id,
                action="create",
                details={
                    "creation_method": creation_method,
                    "username": username if username else None,
                    "access_rights": access_rights,
                    "duration": duration,
                    **(token_metadata or {})
                }
            )
            session.add(history)
            logger.debug("[save_token_chain] After TokenHistory: history=%s", history)
        elif parent_token:
            logger.debug("[save_token_chain] Before TokenHistory (master)")
            history = TokenHistory(
                token_id=parent_token.id,
                action="create",
                details={
                    "creation_method": creation_method,
                    "username": username if username else None,
                    "access_rights": access_rights,
                    "duration": duration,
                    **(token_metadata or {})
                }
            )
            session.add(history)
            logger.debug("[save_token_chain] After TokenHistory: history=%s", history)
        
        logger.debug("[save_token_chain] Before session.commit")
        await session.commit()
        logger.debug("[save_token_chain] After session.commit")
        return True
        
    except Exception as e:
        logger.error(f"Error saving token chain: {e}")
        await session.rollback()
        raise

async def save_master_token(
    session: AsyncSession,
    token: str,
    username: str = None,
    password: str = None,
    creation_method: TokenCreationMethod = TokenCreationMethod.MANUAL,
    access_rights: str = None,
    expires_at: datetime.datetime = None
) -> Token:
    """Сохранить мастер-токен и, если указаны, учетные данные"""
    try:
        # Проверяем, существует ли токен
        existing_token = await session.scalar(
            select(Token).where(Token.token == token)
        )
        if existing_token:
            return existing_token

        # Если есть логин/пароль - сохраняем или обновляем аккаунт
        account = None
        if username and password:
            account = await session.scalar(
                select(WialonAccount).where(WialonAccount.username == username)
            )
            if account:
                account.encrypted_password = encrypt_password(password)
                account.last_used = datetime.datetime.utcnow()
            else:
                account = WialonAccount(
                    username=username,
                    encrypted_password=encrypt_password(password)
                )
                session.add(account)
                await session.flush()  # Получаем ID аккаунта

        # Создаем запись токена
        token_record = Token(
            token=token,
            token_type=TokenType.MASTER,
            creation_method=creation_method,
            account_id=account.id if account else None,
            access_rights=access_rights,
            expires_at=expires_at
        )
        session.add(token_record)
        await session.flush()  # Гарантируем, что у token_record есть id
        # Добавляем запись в историю
        history = TokenHistory(
            token_id=token_record.id,
            action="create",
            details={
                "creation_method": creation_method.value,
                "username": username if username else None
            }
        )
        session.add(history)
        await session.commit()
        return token_record

    except Exception as e:
        logger.error(f"Error saving master token: {e}")
        await session.rollback()
        raise

async def save_child_token(
    session: AsyncSession,
    child_token: str,
    master_token: str,
    creation_method: TokenCreationMethod = TokenCreationMethod.API,
    access_rights: str = None,
    expires_at: datetime.datetime = None,
    duration: int = None
) -> Token:
    """Сохранить дочерний токен"""
    try:
        # Находим мастер-токен
        parent_token = await session.scalar(
            select(Token).where(
                Token.token == master_token,
                Token.token_type == TokenType.MASTER
            )
        )
        
        if not parent_token:
            # Если мастер-токен не найден, создаем его
            parent_token = Token(
                token=master_token,
                token_type=TokenType.MASTER,
                creation_method=TokenCreationMethod.MANUAL
            )
            session.add(parent_token)
            await session.flush()

        # Создаем дочерний токен
        child = Token(
            token=child_token,
            token_type=TokenType.CHILD,
            creation_method=creation_method,
            parent_token_id=parent_token.id,
            access_rights=access_rights,
            expires_at=expires_at,
            token_metadata={"duration": duration} if duration else None
        )
        session.add(child)
        
        # Добавляем запись в историю
        history = TokenHistory(
            token_id=child.id,
            action="create",
            details={
                "master_token": master_token,
                "creation_method": creation_method.value
            }
        )
        session.add(history)
        
        await session.commit()
        return child

    except Exception as e:
        logger.error(f"Error saving child token: {e}")
        await session.rollback()
        raise

async def get_token_info(session: AsyncSession, token: str) -> dict:
    """Получить информацию о токене"""
    try:
        token_record = await session.scalar(
            select(Token).where(Token.token == token)
        )
        
        if not token_record:
            return None
            
        info = {
            "token": token_record.token,
            "type": token_record.token_type.value,
            "creation_method": token_record.creation_method.value,
            "status": token_record.status,
            "created_at": token_record.created_at,
            "expires_at": token_record.expires_at,
            "access_rights": token_record.access_rights
        }
        
        # Добавляем информацию о родительском токене
        if token_record.parent_token_id:
            parent = await session.get(Token, token_record.parent_token_id)
            if parent:
                info["parent_token"] = parent.token
        
        # Добавляем информацию об аккаунте
        if token_record.account_id:
            account = await session.get(WialonAccount, token_record.account_id)
            if account:
                info["username"] = account.username
        
        # Добавляем дополнительную информацию из метаданных токена
        if token_record.token_metadata:
            info.update(token_record.token_metadata)
        
        # Логируем проверку
        history = TokenHistory(
            token_id=token_record.id,
            action="check",
            details={"found_in_db": True}
        )
        session.add(history)
        await session.commit()
        
        return info
        
    except Exception as e:
        logger.error(f"Error getting token info: {e}")
        return None

async def update_token_status(
    session: AsyncSession,
    token: str,
    status: str,
    details: dict = None
) -> bool:
    """Обновить статус токена"""
    try:
        token_record = await session.scalar(
            select(Token).where(Token.token == token)
        )
        
        if not token_record:
            return False
            
        token_record.status = status
        token_record.last_used = datetime.datetime.utcnow()
        
        history = TokenHistory(
            token_id=token_record.id,
            action="update",
            details=details
        )
        session.add(history)
        
        await session.commit()
        return True
        
    except Exception as e:
        logger.error(f"Error updating token status: {e}")
        await session.rollback()
        return False

async def get_account_tokens(
    session: AsyncSession,
    username: str
) -> dict:
    """Получить все токены для учетной записи"""
    try:
        # Находим аккаунт
        account = await session.scalar(
            select(WialonAccount).where(WialonAccount.username == username)
        )
        
        if not account:
            return None
            
        # Получаем все мастер-токены для аккаунта
        master_tokens = await session.scalars(
            select(Token).where(
                Token.account_id == account.id,
                Token.token_type == TokenType.MASTER
            )
        )
        
        result = {
            "username": account.username,
            "master_tokens": []
        }
        
        # Для каждого мастер-токена получаем дочерние
        for master in master_tokens:
            token_info = {
                "token": master.token,
                "created_at": master.created_at,
                "status": master.status,
                "child_tokens": []
            }
            
            children = await session.scalars(
                select(Token).where(
                    Token.parent_token_id == master.id,
                    Token.token_type == TokenType.CHILD
                )
            )
            
            token_info["child_tokens"] = [
                {
                    "token": child.token,
                    "created_at": child.created_at,
                    "status": child.status,
                    "expires_at": child.expires_at
                }
                for child in children
            ]
            
            result["master_tokens"].append(token_info)
            
        return result

    except Exception as e:
        logger.error(f"Error getting account tokens: {e}")
        return None

async def add_token(session, account_id, token, parent_token=None, creation_method="API", metadata=None):
    parent_token_id = None
    if parent_token:
        # Если parent_token — это строка токена, ищем его id
        if isinstance(parent_token, str):
            parent = await session.scalar(select(Token).where(Token.token == parent_token))
            if parent:
                parent_token_id = parent.id
        elif isinstance(parent_token, int):
            parent_token_id = parent_token
        elif hasattr(parent_token, 'id'):
            parent_token_id = parent_token.id
    new_token = Token(
        account_id=account_id,
        token=token,
        token_type=TokenType.CHILD if parent_token_id else TokenType.MASTER,
        parent_token_id=parent_token_id,
        creation_method=creation_method,
        # metadata=metadata or {},  # если в модели есть поле metadata, раскомментируй
    )
    session.add(new_token)
    await session.commit()
    return new_token
