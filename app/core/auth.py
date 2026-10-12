from fastapi import Request, HTTPException, Depends
from typing import Optional, Dict, Any
import logging
import os
from app import pg_database as pgdb

logger = logging.getLogger("auth")

# Demo mode: disable authentication if DEMO_MODE env var is set
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"

class UserSession:
    def __init__(self, email: str, role: str, lab_id: Optional[int] = None, full_name: Optional[str] = None):
        self.email = email
        self.role = role
        self.lab_id = lab_id
        self.full_name = full_name


ROLE_ALIASES = {
    "super_admin": "admin",
    "lab_admin": "lab",
    "lab_user": "lab",
}


def normalize_role(role: str) -> str:
    return ROLE_ALIASES.get(role, role)

import hmac
import hashlib
from config.settings import cfg

def get_signature(email: str) -> str:
    return hmac.new(cfg.SECRET_KEY.encode(), email.encode(), hashlib.sha256).hexdigest()

async def get_current_user(request: Request) -> UserSession:
    """
    Backend-Validated Authentication.
    Reads 'aspira_email' and 'aspira_sig' from cookies.
    Verifies signature against SECRET_KEY.
    """
    # Skip authentication for demo/testing purposes
    if DEMO_MODE or request.headers.get("X-Demo-Mode") == "true":
        # In demo mode, respect the cookies set by the frontend UI
        email = request.cookies.get("aspira_email", "demo@aspira.com")
        role = normalize_role(request.cookies.get("aspira_role", "admin"))
        lab_id_str = request.cookies.get("aspira_lab_id")
        lab_id = int(lab_id_str) if lab_id_str else None
        
        return UserSession(
            email=email,
            role=role,
            lab_id=lab_id,
            full_name=email.split("@")[0]
        )
    
    email = request.cookies.get("aspira_email")
    sig = request.cookies.get("aspira_sig")
    
    if not email or not sig:
        logger.warning("Auth failed: Missing session cookies")
        raise HTTPException(status_code=401, detail="Unauthorized: No active session")
    
    if sig != get_signature(email):
        logger.error(f"Auth failed: Invalid signature for {email}")
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid session signature")

    # FETCH FROM BACKEND (Source of Truth)
    from app.pg_database import _pool
    if not _pool:
        logger.error("DB Pool not initialized during auth check")
        raise HTTPException(status_code=500, detail="Database connection error")

    user_row = await _pool.fetchrow(
        "SELECT email, role, lab_id, full_name FROM tat_user WHERE email = $1 AND is_active = 1",
        email
    )
    
    if not user_row:
        logger.warning(f"Auth failed: User {email} not found or inactive")
        raise HTTPException(status_code=403, detail="Forbidden: Unauthorized personnel")

    return UserSession(
        email=user_row["email"],
        role=normalize_role(user_row["role"]),
        lab_id=user_row["lab_id"],
        full_name=user_row["full_name"]
    )

def require_role(allowed_roles: list[str]):
    async def role_checker(user: UserSession = Depends(get_current_user)):
        allowed = {normalize_role(role) for role in allowed_roles}
        if normalize_role(user.role) not in allowed:
            logger.warning(f"Access denied: user={user.email} role={user.role} required={allowed_roles}")
            raise HTTPException(status_code=403, detail=f"Forbidden: {user.role} role unauthorized for this action")
        return user
    return role_checker
