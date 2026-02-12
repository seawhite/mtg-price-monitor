import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.services.downsample_service import run_downsampling
from app.services.monitor_service import run_check_all

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def start_scheduler():
    scheduler.add_job(
        run_check_all,
        "interval",
        seconds=settings.check_interval_seconds,
        id="check_all_monitors",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        run_downsampling,
        "interval",
        hours=1,
        id="downsample_history",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info(
        f"Scheduler started: checking every {settings.check_interval_seconds}s"
    )
    # Backfill: run downsampling once on startup for existing data
    try:
        run_downsampling()
    except Exception as e:
        logger.error(f"Startup downsampling backfill failed: {e}")


def stop_scheduler():
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped.")


def is_scheduler_running() -> bool:
    return scheduler.running
