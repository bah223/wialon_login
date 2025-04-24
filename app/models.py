from enum import Enum
from sqlalchemy import (
    Column, Integer, String, Enum as SAEnum, DateTime, ForeignKey, JSON
)
from sqlalchemy.orm import declarative_base, relationship
import datetime

Base = declarative_base()

class AccessLevel(Enum):
    admin = "admin"
    user = "user"
    guest = "guest"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    access_level = Column(SAEnum(AccessLevel), default=AccessLevel.user, nullable=False)
    tokens = relationship("MasterToken", back_populates="user")
    telegram_id = Column(String, unique=True, nullable=True)  # Telegram user_id (строкой)

class MasterToken(Base):
    __tablename__ = "master_tokens"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String, unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=True)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)  # Дата создания
    creation_method = Column(String, nullable=True)  # Способ создания (API/OAuth)
    access_rights = Column(String, nullable=True)  # Сводка прав доступа (uacl/fl)
    child_tokens = relationship("ChildToken", back_populates="master_token")
    user = relationship("User", back_populates="tokens")
    object_links = relationship("TokenObjectAccess", back_populates="token")

class ChildToken(Base):
    __tablename__ = "child_tokens"
    id = Column(Integer, primary_key=True)
    master_token_id = Column(Integer, ForeignKey("master_tokens.id"), nullable=False)
    token = Column(String, unique=True, nullable=False)
    status = Column(String, default="active")
    last_used_at = Column(DateTime, default=datetime.datetime.utcnow)
    linked_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)  # Дата создания
    creation_method = Column(String, nullable=True)  # Способ создания (API/OAuth)
    access_rights = Column(String, nullable=True)  # Сводка прав доступа (uacl/fl)
    expires_at = Column(DateTime, nullable=True)  # Время окончания действия
    duration = Column(Integer, nullable=True)  # Длительность действия (сек)
    master_token = relationship("MasterToken", back_populates="child_tokens")

class Object(Base):
    __tablename__ = "objects"
    id = Column(Integer, primary_key=True)
    wialon_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    type = Column(String, nullable=True)
    extra_data = Column(JSON, nullable=True)
    # Связь с токенами через TokenObjectAccess
    token_links = relationship("TokenObjectAccess", back_populates="object")

class TokenObjectAccess(Base):
    __tablename__ = "token_object_access"
    id = Column(Integer, primary_key=True)
    token_id = Column(Integer, ForeignKey("master_tokens.id"), nullable=False)
    object_id = Column(Integer, ForeignKey("objects.id"), nullable=False)
    uacl = Column(Integer, nullable=False, default=0)  # Маска прав доступа
    fl = Column(Integer, nullable=True)  # Дополнительные флаги
    extra_data = Column(JSON, nullable=True)
    # Связи
    token = relationship("MasterToken", back_populates="object_links")
    object = relationship("Object", back_populates="token_links")

class TokenHistory(Base):
    __tablename__ = "token_history"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String, nullable=False)
    action = Column(String, nullable=False)  # create/update/delete/check
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    details = Column(JSON, nullable=True)

# Pydantic models (for FastAPI, etc.)
from pydantic import BaseModel

class StatusResponse(BaseModel):
    status: str
    message: str = None 