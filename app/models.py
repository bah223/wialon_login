from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Enum as SQLEnum
from sqlalchemy.orm import declarative_base, relationship, backref
from enum import Enum

Base = declarative_base()

class TokenCreationMethod(Enum):
    LOGIN = "login"      # Создан через логин/пароль
    API = "api"         # Создан через API
    MANUAL = "manual"    # Введен вручную

class TokenType(Enum):
    MASTER = "master"
    CHILD = "child"

class WialonAccount(Base):
    """Сохраненные учетные данные Wialon"""
    __tablename__ = "wialon_accounts"
    
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    encrypted_password = Column(String, nullable=False)
    last_used = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связь с токенами
    tokens = relationship("Token", back_populates="account")

    def __repr__(self):
        return f"<WialonAccount(id={self.id}, username={self.username})>"

class Token(Base):
    """Универсальная таблица для всех токенов"""
    __tablename__ = "tokens"
    
    id = Column(Integer, primary_key=True)
    token = Column(String, unique=True, nullable=False)
    token_type = Column(SQLEnum(TokenType), nullable=False)
    creation_method = Column(SQLEnum(TokenCreationMethod), nullable=False)
    
    # Связь с аккаунтом (если токен получен через логин/пароль)
    account_id = Column(Integer, ForeignKey("wialon_accounts.id"), nullable=True)
    account = relationship("WialonAccount", back_populates="tokens")
    
    # Для дочерних токенов - связь с родительским
    parent_token_id = Column(Integer, ForeignKey("tokens.id"), nullable=True)
    child_tokens = relationship("Token", 
                              backref=backref("parent_token", remote_side=[id]),
                              cascade="all, delete-orphan")
    
    # Общие поля
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    last_used = Column(DateTime, nullable=True)
    access_rights = Column(String, nullable=True)  # Права доступа в формате Wialon
    
    # Дополнительные данные
    token_metadata = Column(JSON, nullable=True)  # Для хранения доп. информации

    def __repr__(self):
        return f"<Token(id={self.id}, type={self.token_type}, method={self.creation_method})>"

class TokenHistory(Base):
    """История операций с токенами"""
    __tablename__ = "token_history"
    
    id = Column(Integer, primary_key=True)
    token_id = Column(Integer, ForeignKey("tokens.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    master_token_id = Column(Integer, ForeignKey("master_tokens.id"), nullable=True)
    child_token_id = Column(Integer, ForeignKey("child_tokens.id"), nullable=True)
    action = Column(String, nullable=False)  # create, update, check, delete, copy
    created_at = Column(DateTime, default=datetime.utcnow)
    details = Column(JSON, nullable=True)  # Дополнительные данные операции
    
    # Relationships
    token = relationship("Token")
    user = relationship("User", back_populates="token_history")
    master_token = relationship("MasterToken", back_populates="token_history")
    child_token = relationship("ChildToken", back_populates="token_history")

    def __repr__(self):
        return f"<TokenHistory(id={self.id}, action={self.action})>"

# Pydantic models для API/валидации
from pydantic import BaseModel
from typing import Optional, List

class TokenResponse(BaseModel):
    """Базовый ответ для операций с токенами"""
    status: str
    message: Optional[str] = None
    token: Optional[str] = None
    expires_at: Optional[datetime] = None
    
class TokenListResponse(BaseModel):
    """Ответ со списком токенов"""
    tokens: List[str]
    parent_token: Optional[str] = None
    creation_method: Optional[str] = None

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    wialon_username = Column(String, nullable=True)
    encrypted_wialon_password = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    telegram_id = Column(String, nullable=True)
    telegram_username = Column(String, nullable=True)
    
    # Relationships
    master_tokens = relationship("MasterToken", back_populates="user")
    token_history = relationship("TokenHistory", back_populates="user")
    saved_credentials = relationship("SavedCredentials", back_populates="user")

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username})>"

class WialonCredentials(Base):
    __tablename__ = "wialon_credentials"
    
    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False)
    encrypted_password = Column(String, nullable=False)
    last_used = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связь с мастер-токенами
    master_tokens = relationship("MasterToken", back_populates="credentials")

    def __repr__(self):
        return f"<WialonCredentials(id={self.id}, username={self.username})>"

class MasterToken(Base):
    __tablename__ = "master_tokens"
    
    id = Column(Integer, primary_key=True)
    token = Column(String, unique=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    credentials_id = Column(Integer, ForeignKey("wialon_credentials.id"), nullable=True)
    creation_method = Column(SQLEnum(TokenCreationMethod), nullable=False)
    status = Column(String, default="active")
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    access_rights = Column(String, nullable=True)  # Права доступа в формате Wialon
    
    # Relationships
    user = relationship("User", back_populates="master_tokens")
    credentials = relationship("WialonCredentials", back_populates="master_tokens")
    child_tokens = relationship("ChildToken", back_populates="master_token", cascade="all, delete-orphan")
    token_history = relationship("TokenHistory", back_populates="master_token")
    object_links = relationship("TokenObjectAccess", back_populates="token")

    def __repr__(self):
        return f"<MasterToken(id={self.id}, method={self.creation_method})>"

class ChildToken(Base):
    __tablename__ = "child_tokens"
    
    id = Column(Integer, primary_key=True)
    master_token_id = Column(Integer, ForeignKey("master_tokens.id"), nullable=False)
    token = Column(String, unique=True, nullable=False)
    status = Column(String, default="active")
    creation_method = Column(SQLEnum(TokenCreationMethod), nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    duration = Column(Integer, nullable=True)  # Длительность в секундах
    access_rights = Column(String, nullable=True)  # Права доступа в формате Wialon
    
    # Relationships
    master_token = relationship("MasterToken", back_populates="child_tokens")
    token_history = relationship("TokenHistory", back_populates="child_token")

    def __repr__(self):
        return f"<ChildToken(id={self.id}, master_token_id={self.master_token_id})>"

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

class SavedCredentials(Base):
    __tablename__ = "saved_credentials"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String, nullable=False)
    extra_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="saved_credentials")

    def __repr__(self):
        return f"<SavedCredentials(id={self.id}, user_id={self.user_id})>" 