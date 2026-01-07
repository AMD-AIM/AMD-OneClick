"""
Background scheduler for cleanup tasks
"""
import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import settings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def cleanup_job():
    """Periodic job to cleanup idle and expired instances"""
    from .k8s_client import k8s_client
    
    logger.info("Running cleanup job...")
    try:
        cleaned = k8s_client.cleanup_idle_instances()
        if cleaned:
            logger.info(f"Cleaned up {len(cleaned)} instances: {cleaned}")
        else:
            logger.info("No instances to clean up")
    except Exception as e:
        logger.error(f"Cleanup job failed: {e}")


def start_scheduler():
    """Start the background scheduler"""
    scheduler.add_job(
        cleanup_job,
        trigger=IntervalTrigger(minutes=settings.IDLE_TIMEOUT_MINUTES),
        id="cleanup_job",
        name="Cleanup idle and expired instances",
        replace_existing=True
    )
    scheduler.start()
    logger.info(f"Scheduler started, cleanup runs every {settings.IDLE_TIMEOUT_MINUTES} minutes")


def stop_scheduler():
    """Stop the background scheduler"""
    scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")
