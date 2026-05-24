from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.graph.workflow import run_competitive_analysis
from app.services.task_service import update_task_status


@celery_app.task(bind=True, max_retries=3)
def run_analysis_task(self, task_id: int):
    db = SessionLocal()
    try:
        return run_competitive_analysis(db, task_id)
    except Exception as exc:
        update_task_status(db, task_id, "failed", str(exc))
        raise self.retry(exc=exc, countdown=30)
    finally:
        db.close()
