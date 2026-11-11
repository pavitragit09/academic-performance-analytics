
"""Administrator APIs for user account management (APAS-F-004)."""



from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.app.database import get_db
from src.app.errors import AppError
from src.app.models import AuditLogEntry, Role, User, UserSession
from src.app.routers.auth import require_admin
from src.app.security import hash_password


router = APIRouter(prefix="/users", tags=["User Administration"])


class UserCreate(BaseModel):
    """Fields required to create a user."""

    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=72)
    role: Role


class UserUpdate(BaseModel):
    """Fields that an administrator can update."""

    username: str | None = Field(default=None, min_length=3, max_length=100)
    role: Role | None = None


class UserStatusUpdate(BaseModel):
    """Activate or deactivate an account."""

    is_active: bool


class UserResponse(BaseModel):
    """Public user details; never expose password hashes."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: Role
    is_active: bool


def _audit(
    db: Session,
    request: Request,
    user_id: int,
    action: str,
    target_user_id: int,
    old_value: str | None = None,
    new_value: str | None = None,
) -> None:
    """Record an administrator's user-management action."""

    db.add(
        AuditLogEntry(
            user_id=user_id,
            action=action,
            entity=f"User:{target_user_id}",
            old_value=old_value,
            new_value=new_value,
            ip_address=(
                request.client.host
                if request.client is not None
                else None
            ),
        )
    )


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    data: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Create an account with a hashed password."""

    existing = db.scalar(
        select(User).where(User.username == data.username)
    )

    if existing is not None:
        raise AppError(409, "CONFLICT", "Username already exists")

    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        role=data.role,
        is_active=True,
    )

    db.add(user)

    try:
        db.flush()
        _audit(
            db, request, admin.id, "USER_CREATED",
            user.id, new_value=f"{user.username}:{user.role.value}",
        )
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "CONFLICT", "Username already exists") from exc

    return user


@router.get("", response_model=list[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """List all user accounts."""

    return db.scalars(select(User).order_by(User.id)).all()


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Get one user account."""

    user = db.get(User, user_id)

    if user is None:
        raise AppError(404, "NOT_FOUND", "User not found")

    return user


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    data: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Update a username or role."""

    user = db.get(User, user_id)

    if user is None:
        raise AppError(404, "NOT_FOUND", "User not found")

    changes = data.model_dump(exclude_unset=True)

    if not changes:
        raise AppError(400, "BAD_REQUEST", "No fields provided for update")
    if any(value is None for value in changes.values()):
        raise AppError(422, "VALIDATION_ERROR", "Updated fields cannot be null")

    if "username" in changes:
        duplicate = db.scalar(
            select(User).where(
                User.username == changes["username"],
                User.id != user_id,
            )
        )
        if duplicate is not None:
            raise AppError(409, "CONFLICT", "Username already exists")

    old_value = f"{user.username}:{user.role.value}"

    for field, value in changes.items():
        setattr(user, field, value)

    new_value = f"{user.username}:{user.role.value}"

    _audit(
        db, request, admin.id, "USER_UPDATED",
        user.id, old_value, new_value,
    )

    db.commit()
    db.refresh(user)

    return user


@router.patch("/{user_id}/status", response_model=UserResponse)
def update_user_status(
    user_id: int,
    data: UserStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Activate or deactivate a user account."""

    user = db.get(User, user_id)

    if user is None:
        raise AppError(404, "NOT_FOUND", "User not found")

    if user.id == admin.id and not data.is_active:
        raise AppError(400, "BAD_REQUEST", "You cannot deactivate your own account")

    old_status = user.is_active
    user.is_active = data.is_active

    # Revoke existing sessions immediately when deactivating.
    if not data.is_active:
        sessions = db.scalars(
            select(UserSession).where(
                UserSession.user_id == user.id,
                UserSession.is_revoked.is_(False),
            )
        ).all()

        for session in sessions:
            session.is_revoked = True

    _audit(
        db,
        request,
        admin.id,
        "USER_ACTIVATED" if data.is_active else "USER_DEACTIVATED",
        user.id,
        old_value=str(old_status),
        new_value=str(data.is_active),
    )

    db.commit()
    db.refresh(user)

    return user
