from fastapi import Security, HTTPException, Depends
from fastapi.security.api_key import APIKeyHeader
from starlette.status import HTTP_403_FORBIDDEN

# --- UUID Constants for Mock Auth ---
# In a real app, these would come from the database.
ID_DS_GROUP = "550e8400-e29b-41d4-a716-446655440000"
ID_AG_ALPHA = "550e8400-e29b-41d4-a716-446655440001"
ID_AG_BETA  = "550e8400-e29b-41d4-a716-446655440002"

# --- HEADER CONFIGURATION ---
TOKEN_HEADER_NAME = "Authorization"
api_key_header = APIKeyHeader(name=TOKEN_HEADER_NAME, auto_error=False)

# This simulates our database of users. Each token maps to a specific User Object.
USERS_DB = {
    "admin@dsgroup.com": {
        "password": "password123",
        "token": "token_ds_admin",
        "user_info": {
            "id": "550e8400-e29b-41d4-a716-446655440003",
            "email": "admin@dsgroup.com",
            "name": "DS Admin",
            "role": "DS_GROUP",
            "client_id": ID_DS_GROUP,
            "agency_id": None
        }
    },
    "alpha@agency.com": {
        "password": "password123",
        "token": "token_agency_alpha",
        "user_info": {
            "id": "550e8400-e29b-41d4-a716-446655440004",
            "email": "alpha@agency.com",
            "name": "Alpha User",
            "role": "AGENCY",
            "client_id": None,
            "agency_id": ID_AG_ALPHA,
            "agency_name": "Agency Alpha" # Keep for backward compat in UI
        }
    },
    "beta@agency.com": {
        "password": "password123",
        "token": "token_agency_beta",
        "user_info": {
            "id": "550e8400-e29b-41d4-a716-446655440005",
            "email": "beta@agency.com",
            "name": "Beta User",
            "role": "AGENCY",
            "client_id": None,
            "agency_id": ID_AG_BETA,
            "agency_name": "Agency Beta"
        }
    }
}

# Mapping of tokens back to users for verification.
TOKENS_TO_USERS = {v["token"]: v["user_info"] for v in USERS_DB.values()}

async def get_current_user(api_key: str = Depends(api_key_header)):
    """
    Middleware function that validates tokens and returns User context.
    Now includes client_id and agency_id for relational isolation.
    """
    if not api_key:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail=f"Missing {TOKEN_HEADER_NAME} header"
        )
    
    token = api_key.replace("Bearer ", "") if "Bearer " in api_key else api_key
    
    user = TOKENS_TO_USERS.get(token)
    if not user:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail="Invalid or expired token"
        )
    
    return user

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
