import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from pymongo.errors import PyMongoError

from app.database.mongodb import tenants_collection
from app.services.attendance_service import OFFICE_TIMEZONE
from app.services.notification_service import process_weekly_violations

logger = logging.getLogger("scheduler_service")

scheduler = BackgroundScheduler(timezone=OFFICE_TIMEZONE)


def run_previous_week_notifications() -> None:
    today = datetime.now(OFFICE_TIMEZONE).date()
    current_monday = today - timedelta(days=today.weekday())
    previous_monday = current_monday - timedelta(days=7)

    # Process violations for each active tenant
    try:
        active_tenants = list(
            tenants_collection.find({"status": "active"}, {"id": 1, "_id": 1})
        )
    except PyMongoError as err:
        logger.error("Failed to query active tenants: %s", err)
        active_tenants = []

    if active_tenants:
        for tenant in active_tenants:
            tenant_id = str(tenant.get("id") or tenant.get("_id"))
            try:
                process_weekly_violations(previous_monday, tenant_id=tenant_id)
            except (PyMongoError, OSError, RuntimeError, ValueError) as err:
                logger.error(
                    "Error processing weekly violations for tenant %s: %s",
                    tenant_id,
                    err,
                )
    else:
        # Fallback for default tenant
        try:
            process_weekly_violations(previous_monday, tenant_id="default")
        except (PyMongoError, OSError, RuntimeError, ValueError) as err:
            logger.error(
                "Error processing weekly violations for default tenant: %s", err
            )


def start_scheduler() -> None:
    if not scheduler.get_job("weekly_attendance_notifications"):
        scheduler.add_job(
            run_previous_week_notifications,
            trigger="cron",
            day_of_week="mon",
            hour=9,
            minute=0,
            id="weekly_attendance_notifications",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    if not scheduler.running:
        scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
