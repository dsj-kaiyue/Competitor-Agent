from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.user import ChangePasswordRequest, LoginRequest, LoginResponse, RegisterRequest, UserResponse
from app.services.user_service import authenticate_user, change_password

router = APIRouter()
REGISTRATION_PAUSED_MESSAGE = (
    "感谢关注！由于当前 Token 额度有限，暂时关闭新用户注册。"
    "考核老师可使用管理员账号或测试账号登录体验，感谢理解。"
)


@router.post("/login", response_model=LoginResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = authenticate_user(db, request.username.strip(), request.password)
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user.id, user.username, user.is_admin)
    return LoginResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/register", response_model=LoginResponse)
def register(request: RegisterRequest) -> LoginResponse:
    raise HTTPException(status_code=403, detail=REGISTRATION_PAUSED_MESSAGE)


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
