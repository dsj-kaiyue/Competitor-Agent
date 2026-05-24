from fastapi import APIRouter

from app.api.v1 import analysis_tasks, task_plans

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(task_plans.router, prefix="/task-plans", tags=["task-plans"])
api_router.include_router(analysis_tasks.router, prefix="/analysis-tasks", tags=["analysis-tasks"])
