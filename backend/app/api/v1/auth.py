from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.user import ChangePasswordRequest, LoginRequest, LoginResponse, RegisterRequest, UserResponse
from app.services.user_service import authenticate_user, change_password, create_user

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = authenticate_user(db, request.username.strip(), request.password)
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user.id, user.username, user.is_admin)
    return LoginResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/register", response_model=LoginResponse)
def register(request: RegisterRequest, db: Session = Depends(get_db)) -> LoginResponse:
    try:
        user = create_user(db, request.username, request.password)
    except ValueError as exc:
        raise HTTPException(status_code=409 if "已被使用" in str(exc) else 400, detail=str(exc)) from exc
    token = create_access_token(user.id, user.username, user.is_admin)
    return LoginResponse(access_token=token, user=UserResponse.model_validate(user))


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.post("/password", response_model=UserResponse)
def update_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    try:
        change_password(db, current_user, request.current_password, request.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.refresh(current_user)
    return UserResponse.model_validate(current_user)
