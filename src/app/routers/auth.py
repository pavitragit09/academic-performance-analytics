
"""Authentication, server-side sessions and role-based authorization."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app.config import API_PREFIX
from src.app.database import get_db
from src.app.errors import AppError
from src.app.models import AuditLogEntry, Role, Student, User, UserSession
from src.app.security import (
    create_session_token,
    hash_session_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

SESSION_COOKIE = "apas_session"
SESSION_IDLE_MINUTES = 15
LOCKOUT_MINUTES = 15
MAX_FAILED_LOGINS = 5

# Endpoints that do not require an authenticated session.
PUBLIC_PATHS = {
    f"{API_PREFIX}/auth/login",
    f"{API_PREFIX}/health",
}


class LoginRequest(BaseModel):
    username: str
    password: str


def _utc(value: datetime) -> datetime:
    """Normalize SQLite's potentially naive datetime to UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _audit(
    db: Session,
    action: str,
    entity: str,
    user_id: int | None = None,
    request: Request | None = None,
) -> None:
    """Record authentication and authorization events without secrets."""
    db.add(
        AuditLogEntry(
            user_id=user_id,
            action=action,
            entity=entity,
            ip_address=(
                request.client.host
                if request is not None and request.client is not None
                else None
            ),
        )
    )


def _unauthenticated(
    message: str = "Authentication required",
) -> None:
    """Raise a standard authentication error."""
    raise AppError(401, "UNAUTHENTICATED", message)


def _set_session_cookie(response: Response, token: str) -> None:
    """Set the secure HTTP-only session cookie."""
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_IDLE_MINUTES * 60,
        httponly=True,
        secure=True,
        samesite="lax",
        path=API_PREFIX,
    )


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Verify credentials and create a server-side session."""

    user = db.scalar(
        select(User).where(User.username == payload.username)
    )

    if user is None:
        _audit(db, "LOGIN_FAILED", "User", request=request)
        db.commit()

        raise AppError(
            401,
            "UNAUTHENTICATED",
            "Invalid username or password",
        )

    now = datetime.now(timezone.utc)

    # Check whether the account is currently locked.
    if user.locked_until is not None:
        if _utc(user.locked_until) > now:
            _audit(
                db,
                "LOGIN_BLOCKED",
                "User",
                user.id,
                request,
            )
            db.commit()

            raise AppError(
                423,
                "ACCOUNT_LOCKED",
                "Account is temporarily locked. Try again later.",
            )

        # Lockout period has ended.
        user.failed_logins = 0
        user.locked_until = None

    # Reject inactive accounts.
    if not user.is_active:
        _audit(
            db,
            "LOGIN_FAILED",
            "User",
            user.id,
            request,
        )
        db.commit()

        raise AppError(
            403,
            "FORBIDDEN",
            "Account is inactive",
        )

    # Verify the supplied password.
    if not verify_password(payload.password, user.password_hash):
        user.failed_logins += 1

        if user.failed_logins >= MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(
                minutes=LOCKOUT_MINUTES
            )

            _audit(
                db,
                "ACCOUNT_LOCKED",
                "User",
                user.id,
                request,
            )

        _audit(
            db,
            "LOGIN_FAILED",
            "User",
            user.id,
            request,
        )

        db.commit()

        if user.failed_logins >= MAX_FAILED_LOGINS:
            raise AppError(
                423,
                "ACCOUNT_LOCKED",
                "Account locked after five failed login attempts",
            )

        raise AppError(
            401,
            "UNAUTHENTICATED",
            "Invalid username or password",
        )

    # Successful login: reset failed attempts.
    user.failed_logins = 0
    user.locked_until = None

    # Generate a random session token.
    raw_token = create_session_token()

    # Store only the token hash in the database.
    session = UserSession(
        user_id=user.id,
        token_hash=hash_session_token(raw_token),
        created_at=now,
        last_activity_at=now,
        expires_at=now + timedelta(
            minutes=SESSION_IDLE_MINUTES
        ),
        is_revoked=False,
    )

    db.add(session)

    _audit(
        db,
        "LOGIN_SUCCESS",
        "User",
        user.id,
        request,
    )

    db.commit()

    # Send the raw token only through the secure cookie.
    _set_session_cookie(response, raw_token)

    return {
        "userId": user.id,
        "role": user.role.value,
        "name": user.username,
    }


def get_current_user(
    request: Request,
    response: Response,
    session_token: str | None = Cookie(
        default=None,
        alias=SESSION_COOKIE,
    ),
    db: Session = Depends(get_db),
) -> User | None:
    """
    Validate sessions for protected API endpoints.

    Login and health are public.
    Other API endpoints require a valid session.
    """

    path = request.url.path

    # Allow public endpoints, documentation and CORS preflight.
    if (
        not path.startswith(f"{API_PREFIX}/")
        or path in PUBLIC_PATHS
        or request.method == "OPTIONS"
    ):
        return None

    if not session_token:
        _unauthenticated()

    # Look up the session using the hashed token.
    stored_session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == hash_session_token(
                session_token
            )
        )
    )

    if stored_session is None or stored_session.is_revoked:
        _unauthenticated("Invalid or expired session")

    now = datetime.now(timezone.utc)

    # Reject expired sessions.
    if _utc(stored_session.expires_at) <= now:
        stored_session.is_revoked = True
        db.commit()

        _unauthenticated("Session expired")

    user = db.get(User, stored_session.user_id)

    # Reject missing or inactive users.
    if user is None or not user.is_active:
        stored_session.is_revoked = True
        db.commit()

        _unauthenticated("User is unavailable")

    # Refresh the 15-minute idle timeout.
    stored_session.last_activity_at = now
    stored_session.expires_at = now + timedelta(
        minutes=SESSION_IDLE_MINUTES
    )

    db.commit()

    # Refresh the browser cookie.
    _set_session_cookie(response, session_token)

    return user


def require_roles(*allowed_roles: Role):
    """Create a dependency that checks the authenticated user's role."""

    def role_checker(
        request: Request,
        user: User | None = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if user is None or user.role not in allowed_roles:
            _audit(
                db,
                "ACCESS_DENIED",
                "Authorization",
                user.id if user is not None else None,
                request,
            )

            db.commit()

            raise AppError(
                403,
                "FORBIDDEN",
                "You do not have permission to access this resource",
            )

        return user

    return role_checker


# Role-specific dependencies.
require_admin = require_roles(Role.ADMIN)
require_faculty = require_roles(Role.FACULTY)
require_student = require_roles(Role.STUDENT)


def verify_student_ownership(
    student_id: int,
    user: User,
    db: Session,
    request: Request | None = None,
) -> Student:
    """Ensure students can access only their own student records."""

    if user.role is Role.STUDENT:
        student = db.scalar(
            select(Student).where(
                Student.id == student_id,
                Student.user_id == user.id,
            )
        )

        if student is None:
            _audit(
                db,
                "ACCESS_DENIED",
                "Student",
                user.id,
                request,
            )

            db.commit()

            raise AppError(
                403,
                "FORBIDDEN",
                "You cannot access another student's records",
            )

        return student

    # Faculty and administrators can access existing student records.
    student = db.get(Student, student_id)

    if student is None:
        raise AppError(
            404,
            "NOT_FOUND",
            "Student not found",
        )

    return student


@router.get("/me")
def get_my_profile(
    user: User | None = Depends(get_current_user),
):
    """Return the authenticated user's profile."""

    if user is None:
        _unauthenticated()

    return {
        "id": user.id,
        "username": user.username,
        "role": user.role.value,
    }


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    session_token: str | None = Cookie(
        default=None,
        alias=SESSION_COOKIE,
    ),
    db: Session = Depends(get_db),
):
    """Revoke the current session and clear the browser cookie."""

    if session_token:
        stored_session = db.scalar(
            select(UserSession).where(
                UserSession.token_hash == hash_session_token(
                    session_token
                )
            )
        )

        if stored_session is not None and not stored_session.is_revoked:
            stored_session.is_revoked = True

            _audit(
                db,
                "LOGOUT",
                "UserSession",
                stored_session.user_id,
                request,
            )

            db.commit()

    response.delete_cookie(
        key=SESSION_COOKIE,
        path=API_PREFIX,
        httponly=True,
        secure=True,
        samesite="lax",
    )

    response.status_code = 204
    return response
