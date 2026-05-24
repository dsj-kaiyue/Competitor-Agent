from fastapi import APIRouter

from app.agents.planner_agent import parse_task_plan
from app.schemas.task_plan import TaskPlanParseRequest, TaskPlanParseResponse

router = APIRouter()


@router.post("/parse", response_model=TaskPlanParseResponse)
def parse_user_input(request: TaskPlanParseRequest) -> TaskPlanParseResponse:
    return TaskPlanParseResponse(task_plan=parse_task_plan(request.user_input))
