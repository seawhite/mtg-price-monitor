from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class MonitorCreate(BaseModel):
    name: str
    source: str  # tcgplayer, ebay, manapool
    url: str
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    track_min_price: Optional[float] = None
    track_max_price: Optional[float] = None
    alerts_enabled: bool = True


class MonitorUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    track_min_price: Optional[float] = None
    track_max_price: Optional[float] = None
    alerts_enabled: Optional[bool] = None


class MonitorResponse(BaseModel):
    id: int
    name: str
    source: str
    url: str
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    track_min_price: Optional[float] = None
    track_max_price: Optional[float] = None
    alerts_enabled: bool
    last_checked_at: Optional[datetime] = None
    last_price: Optional[float] = None
    last_status: Optional[str] = None
    last_alerted_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PriceHistoryResponse(BaseModel):
    id: int
    monitor_id: int
    price: Optional[float] = None
    low: Optional[float] = None
    high: Optional[float] = None
    available: bool = True
    source_detail: Optional[str] = None
    checked_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    status: str
    monitors_count: int
    scheduler_running: bool
