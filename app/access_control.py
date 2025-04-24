import functools
from sqlalchemy.orm import Session
from app.models import User, AccessLevel

def access_required(session_factory, min_level=AccessLevel.user):
    """
    Decorator for Telegram bot handlers to restrict access by user_id.
    session_factory: function returning a new SQLAlchemy session
    min_level: minimal access level required (enum)
    """
    def decorator(handler):
        @functools.wraps(handler)
        async def wrapper(event, *args, **kwargs):
            user_id = getattr(event.from_user, 'id', None) or getattr(event, 'from_user', None)
            if user_id is None:
                return
            session: Session = session_factory()
            try:
                user = session.query(User).filter(User.id == user_id).first()
                if not user or user.access_level < min_level:
                    # Optionally send a message to the user here
                    return
            finally:
                session.close()
            return await handler(event, *args, **kwargs)
        return wrapper
    return decorator
