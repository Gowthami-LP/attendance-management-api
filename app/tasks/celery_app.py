import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()


broker_url = os.getenv(
    "CELERY_BROKER_URL",
    "amqp://guest:guest@localhost:5672//",
)

celery_app = Celery(
    "attendance_management",
    broker=broker_url,
    include=["app.tasks.employee_import_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    control_queue_durable=True,
)
