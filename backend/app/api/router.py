from fastapi import APIRouter

from app.api.v1 import analysis_tasks, auth, task_plans, users

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(task_plans.router, prefix="/task-plans", tags=["task-plans"])
api_router.include_router(analysis_tasks.router, prefix="/analysis-tasks", tags=["analysis-tasks"])
