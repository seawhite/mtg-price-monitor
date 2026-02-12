import asyncio
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.database import SessionLocal, Monitor, PriceHistory
from app.scrapers.base import ScrapeResult
from app.scrapers.ebay import EbayScraper
from app.scrapers.manapool import ManapoolScraper
from app.scrapers.tcgplayer import TCGPlayerScraper
from app.services.sns_service import send_alert, should_send_alert

logger = logging.getLogger(__name__)

SCRAPERS = {
    "tcgplayer": TCGPlayerScraper(),
    "ebay": EbayScraper(),
    "manapool": ManapoolScraper(),
}


def price_in_range(
    price: float, min_price: float | None, max_price: float | None
) -> bool:
    if min_price is not None and price < min_price:
        return False
    if max_price is not None and price > max_price:
        return False
    return True


def price_in_track_range(
    price: float, track_min: float | None, track_max: float | None
) -> bool:
    if track_min is not None and price < track_min:
        return False
    if track_max is not None and price > track_max:
        return False
    return True


async def check_single_monitor(monitor_id: int) -> dict:
    db: Session = SessionLocal()
    try:
        monitor = db.query(Monitor).filter(Monitor.id == monitor_id).first()
        if not monitor:
            return {"error": "Monitor not found"}

        scraper = SCRAPERS.get(monitor.source)
        if not scraper:
            return {"error": f"Unknown source: {monitor.source}"}

        result: ScrapeResult = await scraper.scrape(monitor.url)

        now = datetime.utcnow()
        monitor.last_checked_at = now

        if result.error:
            monitor.last_status = "error"
            # Still record the check in history
            history = PriceHistory(
                monitor_id=monitor.id,
                price=None,
                available=False,
                source_detail=f"Error: {result.error}",
                checked_at=now,
            )
            db.add(history)
            db.commit()
            return {"status": "error", "error": result.error}

        if result.available and result.price is not None:
            # For sources with multiple listings (eBay), filter by tracking range
            if result.listings:
                tracked_listings = [
                    l for l in result.listings
                    if price_in_track_range(l.price, monitor.track_min_price, monitor.track_max_price)
                ]
                tracked_price = min((l.price for l in tracked_listings), default=None)
            else:
                # Single-product sources (TCGPlayer, Manapool)
                if price_in_track_range(result.price, monitor.track_min_price, monitor.track_max_price):
                    tracked_price = result.price
                    tracked_listings = []
                else:
                    tracked_price = None
                    tracked_listings = []

            if tracked_price is not None:
                monitor.last_price = tracked_price
                monitor.last_status = "available"
            else:
                monitor.last_status = "available"

            # Record main tracked price in history
            history = PriceHistory(
                monitor_id=monitor.id,
                price=tracked_price,
                available=True,
                source_detail=None,
                checked_at=now,
            )
            db.add(history)

            # Check if tracked price is in alert range
            if tracked_price is not None and price_in_range(tracked_price, monitor.min_price, monitor.max_price):
                if monitor.alerts_enabled and should_send_alert(monitor.last_alerted_at):
                    link = monitor.url
                    if monitor.source == "ebay" and not monitor.url.startswith("http"):
                        link = f"https://www.ebay.com/sch/i.html?_nkw={monitor.url}&LH_BIN=1&LH_PrefLoc=1"

                    sent = send_alert(
                        card_name=monitor.name,
                        price=tracked_price,
                        source=monitor.source.capitalize(),
                        link=link,
                        min_price=monitor.min_price,
                        max_price=monitor.max_price,
                    )
                    if sent:
                        monitor.last_alerted_at = now

            # For eBay, record and alert on individual tracked listings
            if monitor.source == "ebay" and tracked_listings:
                for listing in tracked_listings:
                    # Record all tracked listings in history
                    lh = PriceHistory(
                        monitor_id=monitor.id,
                        price=listing.price,
                        available=True,
                        source_detail=listing.title,
                        checked_at=now,
                    )
                    db.add(lh)

                    # Alert only if listing is also in alert range
                    if price_in_range(listing.price, monitor.min_price, monitor.max_price):
                        if (
                            monitor.alerts_enabled
                            and should_send_alert(monitor.last_alerted_at)
                        ):
                            sent = send_alert(
                                card_name=monitor.name,
                                price=listing.price,
                                source="eBay",
                                link=listing.link,
                                min_price=monitor.min_price,
                                max_price=monitor.max_price,
                            )
                            if sent:
                                monitor.last_alerted_at = now
        else:
            monitor.last_status = "unavailable"
            monitor.last_price = result.price
            history = PriceHistory(
                monitor_id=monitor.id,
                price=result.price,
                available=False,
                source_detail=None,
                checked_at=now,
            )
            db.add(history)

        db.commit()
        return {
            "status": monitor.last_status,
            "price": monitor.last_price,
            "available": result.available,
        }

    except Exception as e:
        logger.error(f"Error checking monitor {monitor_id}: {e}")
        db.rollback()
        return {"error": str(e)}
    finally:
        db.close()


async def check_all_monitors():
    db: Session = SessionLocal()
    try:
        monitors = db.query(Monitor).all()
        monitor_ids = [m.id for m in monitors]
    finally:
        db.close()

    if not monitor_ids:
        logger.info("No monitors configured, skipping check.")
        return

    logger.info(f"Checking {len(monitor_ids)} monitors...")
    for mid in monitor_ids:
        try:
            result = await check_single_monitor(mid)
            logger.info(f"Monitor {mid}: {result}")
        except Exception as e:
            logger.error(f"Failed to check monitor {mid}: {e}")


def run_check_all():
    """Synchronous wrapper for APScheduler."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(check_all_monitors())
    finally:
        loop.close()
