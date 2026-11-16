from sqlalchemy import Column, Integer, String, Text, JSON, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class DiscordAccount(Base):
    __tablename__ = "discord_accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    discord_id = Column(String, unique=True, index=True)
    username = Column(String)
    avatar_url = Column(String)
    auth_method = Column(String)
    encrypted_token = Column(String)
    status = Column(String, default="Active")
    created_at = Column(DateTime, server_default=func.now())
    
    schedule = relationship("Schedule", back_populates="account", uselist=False, cascade="all, delete-orphan")
    logs = relationship("MessageLog", back_populates="account", cascade="all, delete-orphan")

class Schedule(Base):
    __tablename__ = "schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("discord_accounts.id", ondelete="CASCADE"), unique=True)
    target_channels = Column(JSON, default=list)
    message_content = Column(Text, default="")
    min_delay = Column(Integer, default=65)
    max_delay = Column(Integer, default=145)
    auto_delete = Column(Boolean, default=True)
    status = Column(String, default="Paused")
    last_sent_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    
    account = relationship("DiscordAccount", back_populates="schedule")

class MessageLog(Base):
    __tablename__ = "message_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("discord_accounts.id", ondelete="CASCADE"))
    log_type = Column(String)
    channel_label = Column(String)
    detail = Column(String)
    created_at = Column(DateTime, server_default=func.now())
    
    account = relationship("DiscordAccount", back_populates="logs")