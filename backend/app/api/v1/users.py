from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import get_db
from app.models.user import User
from app.schemas.user import UserActiveRequest, UserListResponse, UserResponse
from app.services.user_service import list_users, set_user_active

router = APIRouter()


@router.get("", response_model=UserListResponse)
def get_users(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> UserListResponse:
    return UserListResponse(items=[UserResponse.model_validate(user) for user in list_users(db)])


@router.patch("/{user_id}/active", response_model=UserResponse)
def update_user_active(
    user_id: int,
    request: UserActiveRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserResponse:
    target_user = db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能停用或启用当前管理员账户")
    if target_user.is_admin:
        raise HTTPException(status_code=400, detail="不能停用管理员账户")
    return UserResponse.model_validate(set_user_active(db, target_user, request.is_active))
