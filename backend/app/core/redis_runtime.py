from __future__ import annotations

from datetime import datetime, timezone
import base64
import json
import os
import socket

import redis

from app.core.config import settings


REDIS_KEY_PREFIX = "competitor_agent"
WORKER_HEARTBEAT_KEY = f"{REDIS_KEY_PREFIX}:worker:heartbeat"
CELERY_QUEUE_NAME = "competitor_agent_analysis"
CELERY_TASK_NAME = "app.worker.run_analysis_task"


def get_redis_client() -> redis.Redis:
    return redis.Redis.from_url(
        settings.celery_broker_url,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )


def write_worker_heartbeat(worker_name: str | None = None) -> None:
    payload = {
        "worker": worker_name or socket.gethostname(),
        "pid": os.getpid(),
        "queue": "competitor_agent_analysis",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    get_redis_client().set(
        WORKER_HEARTBEAT_KEY,
        json.dumps(payload, ensure_ascii=False),
        ex=settings.celery_worker_heartbeat_ttl_seconds,
    )


def clear_worker_heartbeat() -> None:
    get_redis_client().delete(WORKER_HEARTBEAT_KEY)


def get_worker_heartbeat() -> dict | None:
    value = get_redis_client().get(WORKER_HEARTBEAT_KEY)
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {"raw": value}


def is_worker_alive() -> bool:
    return bool(get_worker_heartbeat())


def _loads(value: str | bytes) -> object:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return json.loads(value)


def _task_id_from_message(raw_message: str | bytes) -> int | None:
    try:
        message = _loads(raw_message)
        if isinstance(message, list) and message:
            message = message[0]
        if not isinstance(message, dict):
            return None
        if message.get("headers", {}).get("task") != CELERY_TASK_NAME:
            return None
        body = message.get("body")
        if not body:
            return None
        decoded = base64.b64decode(body).decode(message.get("content-encoding") or "utf-8")
        payload = json.loads(decoded)
        args = payload[0] if isinstance(payload, list) and payload else []
        if not args:
            return None
        return int(args[0])
    except Exception:
        return None


def broker_analysis_task_ids() -> set[int]:
    redis_client = get_redis_client()
    task_ids: set[int] = set()
    queue_keys = {CELERY_QUEUE_NAME}
    queue_keys.update(redis_client.scan_iter(f"{CELERY_QUEUE_NAME}*"))
    for queue_key in queue_keys:
        if redis_client.type(queue_key) != "list":
            continue
        for raw_message in redis_client.lrange(queue_key, 0, -1):
            task_id = _task_id_from_message(raw_message)
            if task_id is not None:
                task_ids.add(task_id)
    for raw_message in redis_client.hvals("unacked"):
        task_id = _task_id_from_message(raw_message)
        if task_id is not None:
            task_ids.add(task_id)
    return task_ids
