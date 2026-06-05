from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.database import SessionLocal
from app.core.config import settings
from app.core.logging import configure_logging
from app.services.user_service import assign_unowned_tasks


configure_logging()
app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

app.include_router(api_router)


@app.on_event("startup")
def seed_users_and_task_owners() -> None:
    db = SessionLocal()
    try:
        assign_unowned_tasks(db)
    finally:
        db.close()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
