from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models import User, MasterToken, TokenHistory
from sqlalchemy.exc import NoResultFound
from passlib.hash import bcrypt
import logging

logger = logging.getLogger(__name__)

async def get_user_by_username(session: AsyncSession, username: str):
    result = await session.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    return user

async def create_or_update_user(session: AsyncSession, username: str, password: str):
    user = await get_user_by_username(session, username)
    hashed_password = bcrypt.hash(password)
    if user:
        user.hashed_password = hashed_password
    else:
        user = User(username=username, hashed_password=hashed_password)
        session.add(user)
    await session.commit()
    return user

async def get_user_by_telegram_id(session: AsyncSession, telegram_id: str):
    result = await session.execute(select(User).where(User.telegram_id == str(telegram_id)))
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

async def get_all_user_tokens(session: AsyncSession, telegram_id: str):
    user = await get_user_by_telegram_id(session, telegram_id)
    if not user:
        logger.warning(f"[get_all_user_tokens] Пользователь с telegram_id={telegram_id} не найден!")
        return []
    master_tokens = await session.execute(select(MasterToken).where(MasterToken.user_id == user.id))
    master_tokens = master_tokens.scalars().all()
    if not master_tokens:
        logger.info(f"[get_all_user_tokens] Нет мастер-токенов для пользователя {user.username} (telegram_id={telegram_id})")
    tokens = []
    for mt in master_tokens:
        tokens.append({
            "token": mt.token,
            "user_name": user.username,
            "created_at": mt.created_at.timestamp() if mt.created_at else None,
            "expires_at": mt.expires_at.timestamp() if mt.expires_at else None,
            "created_via": mt.creation_method,
            "token_type": "master",
            "parent_token": None,
            "status": mt.status,
        })
        for ct in mt.child_tokens:
            tokens.append({
                "token": ct.token,
                "user_name": user.username,
                "created_at": ct.created_at.timestamp() if ct.created_at else None,
                "expires_at": ct.expires_at.timestamp() if ct.expires_at else None,
                "created_via": ct.creation_method,
                "token_type": "child",
                "parent_token": mt.token,
                "status": ct.status,
            })
    logger.info(f"[get_all_user_tokens] Для пользователя {user.username} (telegram_id={telegram_id}) найдено {len(tokens)} токен(ов)")
    return tokens

async def add_token_history(session: AsyncSession, telegram_id: str, token: str, action: str, details: dict = None):
    user = await get_user_by_telegram_id(session, telegram_id)
    if not user:
        return
    history = TokenHistory(user_id=user.id, token=token, action=action, details=details)
    session.add(history)
    await session.commit()
    return history

    async def get_all_logins(session):
    """
    Возвращает список всех логинов, для которых есть успешные входы (username, дата создания, кол-во токенов)
    """
    result = await session.execute("SELECT username FROM users")
    usernames = [row[0] for row in result.fetchall()]
    return usernames

async def get_password_by_login(session, username):
    result = await session.execute("SELECT hashed_password FROM users WHERE username = :username", {"username": username})
    row = result.fetchone()
    return row[0] if row else None
