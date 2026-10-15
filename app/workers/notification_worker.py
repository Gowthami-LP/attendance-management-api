import argparse
import logging
import signal
import sys
import time
from typing import Any

from dotenv import load_dotenv
from pymongo.errors import PyMongoError

from app.database.mongodb import (
    create_notification_indexes,
    notifications_collection,
)
from app.services.notification_service import (
    deliver_notification,
)
from app.services.scheduler_service import run_previous_week_notifications

load_dotenv()

logger = logging.getLogger("notification_worker")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [notification_worker] %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

_keep_running = True


def _handle_shutdown(signum, frame):
    global _keep_running
    logger.info("Shutdown signal received (%s). Exiting gracefully...", signum)
    _keep_running = False


def process_pending_notifications(batch_size: int = 50) -> dict[str, int]:
    """Find and deliver notifications currently in pending state."""
    records = list(
        notifications_collection.find(
            {"status": "pending"},
            {"_id": 0, "notification_id": 1, "created_at": 1},
        )
        .sort("created_at", 1)
        .limit(batch_size)
    )

    sent = 0
    failed = 0

    for record in records:
        notification_id = record["notification_id"]
        result = deliver_notification(notification_id)
        if result.get("status") == "sent":
            sent += 1
        else:
            failed += 1

    return {
        "processed": len(records),
        "sent": sent,
        "failed": failed,
    }


def retry_eligible_failed_notifications(
    max_attempts: int = 3,
    batch_size: int = 50,
) -> dict[str, int]:
    """Find and retry failed notifications that have not exceeded max_attempts."""
    records = list(
        notifications_collection.find(
            {
                "status": "failed",
                "attempts": {"$lt": max_attempts},
            },
            {"_id": 0, "notification_id": 1, "created_at": 1},
        )
        .sort("created_at", 1)
        .limit(batch_size)
    )

    sent = 0
    failed = 0

    for record in records:
        notification_id = record["notification_id"]
        result = deliver_notification(notification_id)
        if result.get("status") == "sent":
            sent += 1
        else:
            failed += 1

    return {
        "retried": len(records),
        "sent": sent,
        "failed": failed,
    }


def run_worker_cycle(max_attempts: int = 3, batch_size: int = 50) -> dict[str, Any]:
    """Execute one processing cycle: drain pending notifications then retry eligible failed."""
    pending_stats = process_pending_notifications(batch_size=batch_size)
    retry_stats = retry_eligible_failed_notifications(
        max_attempts=max_attempts,
        batch_size=batch_size,
    )
    return {
        "pending": pending_stats,
        "retried": retry_stats,
    }


def start_worker_daemon(
    interval_seconds: int = 60,
    max_attempts: int = 3,
    batch_size: int = 50,
) -> None:
    """Run the worker continuously in background polling mode with graceful shutdown."""
    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    logger.info(
        "Notification worker daemon started. Polling every %d seconds (max_attempts=%d)...",
        interval_seconds,
        max_attempts,
    )

    create_notification_indexes()

    while _keep_running:
        try:
            stats = run_worker_cycle(
                max_attempts=max_attempts,
                batch_size=batch_size,
            )
            processed_total = (
                stats["pending"]["processed"] + stats["retried"]["retried"]
            )
            if processed_total > 0:
                logger.info("Cycle completed: %s", stats)
        except (PyMongoError, OSError, RuntimeError, ValueError) as exc:
            logger.error("Error during notification worker cycle: %s", exc)

        # Sleep in small slices to respond promptly to shutdown signals
        slept = 0
        while _keep_running and slept < interval_seconds:
            time.sleep(1)
            slept += 1

    logger.info("Notification worker stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="Attendance Management System - Notification Background Worker"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single processing cycle and exit",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run continuously in background daemon mode",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Polling interval in seconds for daemon mode (default: 60)",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Maximum retry attempts for failed notifications (default: 3)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of records to process per batch (default: 50)",
    )
    parser.add_argument(
        "--process-weekly",
        action="store_true",
        help="Trigger compliance evaluation and create notification records for the previous completed week",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry eligible failed notifications only",
    )

    args = parser.parse_args()

    if args.process_weekly:
        logger.info(
            "Triggering weekly violation processing for previous completed week..."
        )
        run_previous_week_notifications()
        logger.info("Weekly violation processing complete.")
        return

    if args.retry_failed:
        logger.info("Retrying eligible failed notifications...")
        stats = retry_eligible_failed_notifications(
            max_attempts=args.max_attempts,
            batch_size=args.batch_size,
        )
        logger.info("Retry results: %s", stats)
        return

    if args.daemon:
        start_worker_daemon(
            interval_seconds=args.interval,
            max_attempts=args.max_attempts,
            batch_size=args.batch_size,
        )
        return

    # Default action: run once
    logger.info("Running single worker cycle...")
    stats = run_worker_cycle(
        max_attempts=args.max_attempts,
        batch_size=args.batch_size,
    )
    logger.info("Worker cycle results: %s", stats)


if __name__ == "__main__":
    main()
