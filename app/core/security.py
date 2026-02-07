from fastapi import Security, HTTPException, Depends
from app.db import session, models
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.security.api_key import APIKeyHeader
from starlette.status import HTTP_403_FORBIDDEN

# --- HEADER CONFIGURATION ---
TOKEN_HEADER_NAME = "Authorization"
api_key_header = APIKeyHeader(name=TOKEN_HEADER_NAME, auto_error=False)

from passlib.context import CryptContext

# --- PASSWORD HASHING ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, stored_password):
    """Temporary direct comparison for plain-text passwords."""
    return plain_password == stored_password

def get_password_hash(password):
    """Generates a Bcrypt hash for storing."""
    return pwd_context.hash(password)

async def get_current_user(api_key: str = Depends(api_key_header), db: Session = Depends(session.get_db)):
    """
    Validates token against the TOKENS table in the Database.
    Token must be active and not expired (10 days limit).
    """
    if not api_key:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail=f"Missing {TOKEN_HEADER_NAME} header"
        )
    
    # Extract token (Bearer ...)
    token_str = api_key.replace("Bearer ", "") if "Bearer " in api_key else api_key
    
    # DB Lookup: Check Tokens table
    now = models.get_utc_now()
    token_record = db.query(models.Token).filter(
        models.Token.access_token == token_str,
        models.Token.is_active == True,
        models.Token.expires_at > now
    ).first()
    
    if not token_record:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail="Invalid, expired, or deactivated token"
        )
    
    user = token_record.user
    if not user:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail="User associated with token not found"
        )
    
    # Convert SQLAlchemy object to dictionary for compatibility
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "role": user.role,
        "client_id": user.client_id,
        "agency_id": user.agency_id
    }

def verify_ds_group(user: dict = Depends(get_current_user)):
    """Only allows users with role 'DS_GROUP'."""
    if user["role"] != "DS_GROUP":
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail="Only DS Group (Admin) can access this."
        )
    return user

def verify_agency(user: dict = Depends(get_current_user)):
    """Only allows users with role 'AGENCY'."""
    if user["role"] != "AGENCY":
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail="Only Agency users can access this."
        )
    return user
