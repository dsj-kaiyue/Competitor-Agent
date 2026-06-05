import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.analysis_task import AnalysisTask
from app.models.user import User


DEFAULT_USERS = [
    ("Admin", "Admin", True),
    ("User1", "User1", False),
    ("User2", "User2", False),
    ("User3", "User3", False),
]


def ensure_default_users(db: Session) -> list[User]:
    users: list[User] = []
    for username, password, is_admin in DEFAULT_USERS:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(username=username, password_hash=hash_password(password), is_admin=is_admin, is_active=True)
            db.add(user)
            db.flush()
        else:
            user.is_admin = is_admin
        users.append(user)
    db.commit()
    return users


def assign_unowned_tasks(db: Session) -> int:
    users = ensure_default_users(db)
    tasks = list(db.scalars(select(AnalysisTask).where(AnalysisTask.user_id.is_(None)).order_by(AnalysisTask.id)))
    if not tasks:
        return 0
    rng = random.Random(20260605)
    rng.shuffle(tasks)
    rng.shuffle(users)
    for index, task in enumerate(tasks):
        task.user_id = users[index % len(users)].id
    db.commit()
    return len(tasks)


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_user(db: Session, username: str, password: str) -> User:
    normalized_username = username.strip()
    if not normalized_username:
        raise ValueError("用户名不能为空")
    if len(normalized_username) > 80:
        raise ValueError("用户名不能超过 80 个字符")
    if len(password) < 4:
        raise ValueError("密码至少需要 4 个字符")
    existing = db.scalar(select(User).where(User.username == normalized_username))
    if existing is not None:
        raise ValueError("用户名已被使用")
    user = User(username=normalized_username, password_hash=hash_password(password), is_admin=False, is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    if len(new_password) < 4:
        raise ValueError("新密码至少需要 4 个字符")
    if not verify_password(current_password, user.password_hash):
        raise ValueError("当前密码错误")
    user.password_hash = hash_password(new_password)
    db.commit()


def set_user_active(db: Session, target_user: User, is_active: bool) -> User:
    target_user.is_active = is_active
    db.commit()
    db.refresh(target_user)
    return target_user


def list_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).order_by(User.is_admin.desc(), User.id)))
