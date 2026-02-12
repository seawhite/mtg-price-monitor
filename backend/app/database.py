import os
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

from app.config import settings

os.makedirs("data", exist_ok=True)

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class Monitor(Base):
    __tablename__ = "monitors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    source = Column(String, nullable=False)  # tcgplayer, ebay, manapool
    url = Column(Text, nullable=False)  # Full URL or eBay search term
    min_price = Column(Float, nullable=True)
    max_price = Column(Float, nullable=True)
    alerts_enabled = Column(Boolean, default=True)
    last_checked_at = Column(DateTime, nullable=True)
    last_price = Column(Float, nullable=True)
    last_status = Column(String, nullable=True)  # available, unavailable, error
    last_alerted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    price_history = relationship(
        "PriceHistory", back_populates="monitor", cascade="all, delete-orphan"
    )


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    monitor_id = Column(Integer, ForeignKey("monitors.id"), nullable=False)
    price = Column(Float, nullable=True)
    available = Column(Boolean, default=False)
    source_detail = Column(Text, nullable=True)
    checked_at = Column(DateTime, default=datetime.utcnow)

    monitor = relationship("Monitor", back_populates="price_history")


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
