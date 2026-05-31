from fastapi import APIRouter

from app.agents.planner_agent import parse_task_plan
from app.graph.workflow import _console
from app.schemas.task_plan import TaskPlanParseRequest, TaskPlanParseResponse

router = APIRouter()


@router.post("/parse", response_model=TaskPlanParseResponse)
def parse_user_input(request: TaskPlanParseRequest) -> TaskPlanParseResponse:
    _console(
        "task plan parse requested",
        {
            "input_length": len(request.user_input),
            "auto_discover_competitors": request.auto_discover_competitors,
            "auto_add_analysis_dimensions": request.auto_add_analysis_dimensions,
        },
    )
    task_plan = parse_task_plan(
        request.user_input,
        auto_discover_competitors=request.auto_discover_competitors,
        auto_add_analysis_dimensions=request.auto_add_analysis_dimensions,
    )
    _console(
        "task plan parse completed",
        {
            "competitor_count": len(task_plan.competitors),
            "dimension_count": len(task_plan.analysis_dimensions),
            "auto_discover_competitors": task_plan.auto_discover_competitors,
            "auto_add_analysis_dimensions": request.auto_add_analysis_dimensions,
        },
    )
    return TaskPlanParseResponse(task_plan=task_plan)
