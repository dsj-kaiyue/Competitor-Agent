import socket

from celery import Celery
from kombu import Queue

from app.core.config import settings

CELERY_QUEUE_NAME = "competitor_agent_analysis"


def _socket_keepalive_options() -> dict[int, int]:
    options: dict[int, int] = {}
    if hasattr(socket, "TCP_KEEPIDLE"):
        options[socket.TCP_KEEPIDLE] = 60
    if hasattr(socket, "TCP_KEEPINTVL"):
        options[socket.TCP_KEEPINTVL] = 10
    if hasattr(socket, "TCP_KEEPCNT"):
        options[socket.TCP_KEEPCNT] = 3
    return options


celery_app = Celery(
    "competitor_agent",
    broker=settings.celery_broker_url,
    include=["app.worker"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=False,
    task_default_queue=CELERY_QUEUE_NAME,
    task_default_exchange=CELERY_QUEUE_NAME,
    task_default_routing_key=CELERY_QUEUE_NAME,
    task_queues=(
        Queue(CELERY_QUEUE_NAME, routing_key=CELERY_QUEUE_NAME),
    ),
    task_ignore_result=True,
    result_backend=None,
    worker_enable_remote_control=False,
    worker_send_task_events=False,
    task_send_sent_event=False,
    task_acks_late=False,
    task_reject_on_worker_lost=False,
    worker_prefetch_multiplier=1,
    worker_cancel_long_running_tasks_on_connection_loss=False,
    broker_pool_limit=0,
    broker_connection_timeout=5,
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=None,
    task_publish_retry=False,
    broker_transport_options={
        "socket_connect_timeout": 5,
        "socket_keepalive": True,
        "socket_keepalive_options": _socket_keepalive_options(),
        # Long-running local analysis tasks can leave the Redis broker connection
        # idle until completion. Disabling Redis ack emulation avoids stale-ACK
        # failures that strand messages in Kombu's unacked keys after WinError 10054.
        "ack_emulation": False,
        "health_check_interval": 30,
        "retry_on_timeout": True,
        "visibility_timeout": settings.celery_visibility_timeout_seconds,
    },
)
