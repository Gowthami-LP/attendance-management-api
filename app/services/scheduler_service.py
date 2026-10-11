from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.services.attendance_service import OFFICE_TIMEZONE
from app.services.notification_service import process_weekly_violations

scheduler = BackgroundScheduler(timezone=OFFICE_TIMEZONE)


def run_previous_week_notifications() -> None:
    today = datetime.now(OFFICE_TIMEZONE).date()
    current_monday = today - timedelta(days=today.weekday())
    previous_monday = current_monday - timedelta(days=7)
    process_weekly_violations(previous_monday)


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
