import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import Monitor, PriceHistory, get_db
from app.models import (
    HealthResponse,
    MonitorCreate,
    MonitorResponse,
    MonitorUpdate,
    PriceHistoryResponse,
)
from app.scheduler import is_scheduler_running
from app.services.monitor_service import check_single_monitor
from app.services.sns_service import send_test_notification
from app.scrapers.ebay import EbayScraper
from app.scrapers.manapool import ManapoolScraper
from app.scrapers.tcgplayer import TCGPlayerScraper

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check(db: Session = Depends(get_db)):
    count = db.query(Monitor).count()
    return HealthResponse(
        status="ok",
        monitors_count=count,
        scheduler_running=is_scheduler_running(),
    )


@router.get("/monitors", response_model=list[MonitorResponse])
def list_monitors(db: Session = Depends(get_db)):
    monitors = db.query(Monitor).order_by(Monitor.created_at.desc()).all()
    return monitors


@router.post("/monitors", response_model=MonitorResponse, status_code=201)
def create_monitor(data: MonitorCreate, db: Session = Depends(get_db)):
    if data.source not in ("tcgplayer", "ebay", "manapool"):
        raise HTTPException(
            status_code=400,
            detail="source must be one of: tcgplayer, ebay, manapool",
        )
    monitor = Monitor(
        name=data.name,
        source=data.source,
        url=data.url,
        min_price=data.min_price,
        max_price=data.max_price,
        track_min_price=data.track_min_price,
        track_max_price=data.track_max_price,
        alerts_enabled=data.alerts_enabled,
    )
    db.add(monitor)
    db.commit()
    db.refresh(monitor)
    return monitor


@router.get("/monitors/{monitor_id}", response_model=MonitorResponse)
def get_monitor(monitor_id: int, db: Session = Depends(get_db)):
    monitor = db.query(Monitor).filter(Monitor.id == monitor_id).first()
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")
    return monitor


@router.put("/monitors/{monitor_id}", response_model=MonitorResponse)
def update_monitor(
    monitor_id: int, data: MonitorUpdate, db: Session = Depends(get_db)
):
    monitor = db.query(Monitor).filter(Monitor.id == monitor_id).first()
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(monitor, key, value)

    monitor.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(monitor)
    return monitor


@router.delete("/monitors/{monitor_id}", status_code=204)
def delete_monitor(monitor_id: int, db: Session = Depends(get_db)):
    monitor = db.query(Monitor).filter(Monitor.id == monitor_id).first()
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")
    db.delete(monitor)
    db.commit()


@router.patch("/monitors/{monitor_id}/toggle-alerts", response_model=MonitorResponse)
def toggle_alerts(monitor_id: int, db: Session = Depends(get_db)):
    monitor = db.query(Monitor).filter(Monitor.id == monitor_id).first()
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")
    monitor.alerts_enabled = not monitor.alerts_enabled
    monitor.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(monitor)
    return monitor


@router.get(
    "/monitors/{monitor_id}/history", response_model=list[PriceHistoryResponse]
)
def get_price_history(
    monitor_id: int,
    days: int = Query(default=7, ge=1, le=365),
    db: Session = Depends(get_db),
):
    monitor = db.query(Monitor).filter(Monitor.id == monitor_id).first()
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")

    since = datetime.utcnow() - timedelta(days=days)
    history = (
        db.query(PriceHistory)
        .filter(
            PriceHistory.monitor_id == monitor_id,
            PriceHistory.checked_at >= since,
        )
        .order_by(PriceHistory.checked_at.asc())
        .all()
    )
    return history


@router.post("/test-sns")
def test_sns():
    success = send_test_notification()
    if not success:
        raise HTTPException(status_code=500, detail="Failed to send SNS test notification")
    return {"success": True}


@router.post("/monitors/{monitor_id}/check-now")
async def check_now(monitor_id: int, db: Session = Depends(get_db)):
    monitor = db.query(Monitor).filter(Monitor.id == monitor_id).first()
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")

    result = await check_single_monitor(monitor_id)
    return result


@router.post("/debug-scrape")
async def debug_scrape(source: str = Query(...), url: str = Query(...)):
    """Debug endpoint: run a scraper and return raw results."""
    scrapers = {
        "ebay": EbayScraper(),
        "manapool": ManapoolScraper(),
        "tcgplayer": TCGPlayerScraper(),
    }
    scraper = scrapers.get(source)
    if not scraper:
        raise HTTPException(status_code=400, detail=f"Unknown source: {source}")

    result = await scraper.scrape(url)
    return {
        "price": result.price,
        "available": result.available,
        "error": result.error,
        "listings_count": len(result.listings),
        "listings": [
            {"title": l.title, "price": l.price, "link": l.link[:100]}
            for l in result.listings[:20]
        ],
    }
