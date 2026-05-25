from datetime import datetime, timedelta
from threading import Event, Thread

from celery.signals import worker_ready, worker_shutdown
from sqlalchemy import select

from app.core.celery_app import CELERY_QUEUE_NAME, celery_app
from app.core.database import SessionLocal
from app.core.config import settings
from app.core.redis_runtime import broker_analysis_task_ids, clear_worker_heartbeat, write_worker_heartbeat
from app.graph.workflow import _console, run_competitive_analysis
from app.models.agent_node import AgentNode
from app.models.analysis_task import AnalysisTask
from app.services.task_service import update_task_status


_heartbeat_stop = Event()
_heartbeat_thread: Thread | None = None


def _start_worker_heartbeat(worker_name: str | None) -> None:
    global _heartbeat_thread
    if _heartbeat_thread and _heartbeat_thread.is_alive():
        return

    def loop() -> None:
        while not _heartbeat_stop.is_set():
            try:
                write_worker_heartbeat(worker_name)
            except Exception as exc:
                _console("celery worker heartbeat failed", {"error": str(exc)})
            _heartbeat_stop.wait(settings.celery_worker_heartbeat_interval_seconds)

    _heartbeat_stop.clear()
    _heartbeat_thread = Thread(target=loop, daemon=True, name="celery-worker-heartbeat")
    _heartbeat_thread.start()


def _recover_missing_queued_tasks() -> None:
    db = SessionLocal()
    try:
        broker_task_ids = broker_analysis_task_ids()
        recover_after = datetime.utcnow() - timedelta(seconds=settings.celery_queued_recovery_max_age_seconds)
        queued_tasks = list(db.scalars(select(AnalysisTask).where(AnalysisTask.status == "queued").order_by(AnalysisTask.id)))
        for task in queued_tasks:
            if task.updated_at and task.updated_at < recover_after:
                _console("skip old queued task recovery", {"task_id": task.id, "updated_at": task.updated_at.isoformat()})
                continue
            node_statuses = list(
                db.scalars(select(AgentNode.status).where(AgentNode.task_id == task.id).order_by(AgentNode.id))
            )
            if any(status != "pending" for status in node_statuses):
                continue
            if task.id in broker_task_ids:
                continue
            async_result = run_analysis_task.apply_async(args=[task.id], queue=CELERY_QUEUE_NAME, routing_key=CELERY_QUEUE_NAME)
            _console("requeued missing queued task", {"task_id": task.id, "celery_task_id": async_result.id, "queue": CELERY_QUEUE_NAME})
    except Exception as exc:
        _console("queued task recovery failed", {"error": str(exc)})
    finally:
        db.close()


@worker_ready.connect
def on_worker_ready(sender=None, **kwargs) -> None:
    worker_name = getattr(sender, "hostname", None)
    _console("celery worker ready", {"worker": worker_name, "queue": CELERY_QUEUE_NAME})
    write_worker_heartbeat(worker_name)
    _start_worker_heartbeat(worker_name)
    _recover_missing_queued_tasks()


@worker_shutdown.connect
def on_worker_shutdown(sender=None, **kwargs) -> None:
    _heartbeat_stop.set()
    try:
        clear_worker_heartbeat()
    except Exception as exc:
        _console("celery worker heartbeat cleanup failed", {"error": str(exc)})


@celery_app.task(bind=True, max_retries=3, ignore_result=True, name="app.worker.run_analysis_task")
def run_analysis_task(self, task_id: int):
    _console("celery task received", {"task_id": task_id, "celery_task_id": self.request.id, "queue": CELERY_QUEUE_NAME})
    db = SessionLocal()
    try:
        task = db.get(AnalysisTask, task_id)
        if task is None:
            _console("celery task skipped because analysis task is missing", {"task_id": task_id})
            return {"skipped": True, "reason": "missing_task"}
        if task.status not in {"created", "queued", "failed"}:
            _console("celery task skipped because task is already active", {"task_id": task_id, "status": task.status})
            return {"skipped": True, "reason": "already_active", "status": task.status}
        update_task_status(db, task_id, "running")
        result = run_competitive_analysis(db, task_id)
        _console("celery task completed", {"task_id": task_id, "celery_task_id": self.request.id})
        return result
    except Exception as exc:
        _console("celery task failed", {"task_id": task_id, "error": str(exc)})
        update_task_status(db, task_id, "failed", str(exc))
        raise self.retry(exc=exc, countdown=30)
    finally:
        db.close()
