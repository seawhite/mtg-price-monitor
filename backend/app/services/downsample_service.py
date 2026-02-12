import logging
from datetime import datetime, timedelta

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.database import (
    PriceHistory,
    PriceHistoryDaily,
    PriceHistoryHourly,
    SessionLocal,
)

logger = logging.getLogger(__name__)

RAW_RETENTION_DAYS = 30
HOURLY_RETENTION_DAYS = 365


def rollup_to_hourly(db: Session) -> int:
    """Roll up raw price_history rows older than RAW_RETENTION_DAYS into hourly aggregates."""
    cutoff = datetime.utcnow() - timedelta(days=RAW_RETENTION_DAYS)

    # Aggregate old raw rows by monitor_id and truncated hour
    # SQLite: strftime('%Y-%m-%d %H:00:00', checked_at)
    hour_expr = func.strftime("%Y-%m-%d %H:00:00", PriceHistory.checked_at)

    rows = (
        db.query(
            PriceHistory.monitor_id,
            hour_expr.label("hour"),
            func.min(PriceHistory.price).label("low"),
            func.max(PriceHistory.price).label("high"),
            func.avg(PriceHistory.price).label("avg"),
            func.count().label("count"),
        )
        .filter(
            PriceHistory.checked_at < cutoff,
            PriceHistory.price.isnot(None),
        )
        .group_by(PriceHistory.monitor_id, hour_expr)
        .all()
    )

    inserted = 0
    for row in rows:
        hour_dt = datetime.strptime(row.hour, "%Y-%m-%d %H:%M:%S")
        # Skip if already rolled up
        exists = (
            db.query(PriceHistoryHourly)
            .filter(
                PriceHistoryHourly.monitor_id == row.monitor_id,
                PriceHistoryHourly.hour == hour_dt,
            )
            .first()
        )
        if not exists:
            db.add(
                PriceHistoryHourly(
                    monitor_id=row.monitor_id,
                    hour=hour_dt,
                    low=round(row.low, 2) if row.low else None,
                    high=round(row.high, 2) if row.high else None,
                    avg=round(row.avg, 2) if row.avg else None,
                    count=row.count,
                )
            )
            inserted += 1

    # Delete old raw rows (including those with NULL price)
    deleted = (
        db.query(PriceHistory)
        .filter(PriceHistory.checked_at < cutoff)
        .delete(synchronize_session=False)
    )

    return inserted


def rollup_to_daily(db: Session) -> int:
    """Roll up hourly rows older than HOURLY_RETENTION_DAYS into daily aggregates."""
    cutoff = datetime.utcnow() - timedelta(days=HOURLY_RETENTION_DAYS)

    day_expr = func.strftime("%Y-%m-%d 00:00:00", PriceHistoryHourly.hour)

    rows = (
        db.query(
            PriceHistoryHourly.monitor_id,
            day_expr.label("day"),
            func.min(PriceHistoryHourly.low).label("low"),
            func.max(PriceHistoryHourly.high).label("high"),
            func.avg(PriceHistoryHourly.avg).label("avg"),
            func.sum(PriceHistoryHourly.count).label("count"),
        )
        .filter(PriceHistoryHourly.hour < cutoff)
        .group_by(PriceHistoryHourly.monitor_id, day_expr)
        .all()
    )

    inserted = 0
    for row in rows:
        day_dt = datetime.strptime(row.day, "%Y-%m-%d %H:%M:%S")
        exists = (
            db.query(PriceHistoryDaily)
            .filter(
                PriceHistoryDaily.monitor_id == row.monitor_id,
                PriceHistoryDaily.day == day_dt,
            )
            .first()
        )
        if not exists:
            db.add(
                PriceHistoryDaily(
                    monitor_id=row.monitor_id,
                    day=day_dt,
                    low=round(row.low, 2) if row.low else None,
                    high=round(row.high, 2) if row.high else None,
                    avg=round(row.avg, 2) if row.avg else None,
                    count=row.count,
                )
            )
            inserted += 1

    deleted = (
        db.query(PriceHistoryHourly)
        .filter(PriceHistoryHourly.hour < cutoff)
        .delete(synchronize_session=False)
    )

    return inserted


def run_downsampling():
    """Run all downsampling steps. Called by the scheduler."""
    db: Session = SessionLocal()
    try:
        hourly_count = rollup_to_hourly(db)
        daily_count = rollup_to_daily(db)
        db.commit()
        if hourly_count or daily_count:
            logger.info(
                f"Downsampling complete: {hourly_count} hourly rows inserted, "
                f"{daily_count} daily rows inserted"
            )
    except Exception as e:
        db.rollback()
        logger.error(f"Downsampling failed: {e}")
    finally:
        db.close()
