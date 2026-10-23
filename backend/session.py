"""
Session management for tracking user projects without authentication.
"""
import uuid
from typing import Optional
from fastapi import Cookie, Response
from backend.config import get_settings

settings = get_settings()


def generate_session_id() -> str:
    """Generate a new session ID."""
    return str(uuid.uuid4())


def get_or_create_session(
    response: Response,
    session_id: Optional[str] = Cookie(None, alias=settings.session_cookie_name)
) -> str:
    """
    Get existing session ID from cookie or create a new one.
    
    Args:
        response: FastAPI response object to set cookie
        session_id: Existing session ID from cookie
        
    Returns:
        Session ID (existing or newly created)
    """
    if not session_id:
        session_id = generate_session_id()
        response.set_cookie(
            key=settings.session_cookie_name,
            value=session_id,
            max_age=settings.session_max_age,
            httponly=True,
            samesite="lax"
        )
    return session_id
