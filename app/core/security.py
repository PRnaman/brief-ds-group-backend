from fastapi import Security, HTTPException, Depends
from fastapi.security.api_key import APIKeyHeader
from starlette.status import HTTP_403_FORBIDDEN

# --- HEADER CONFIGURATION ---
# You can change the key name here. For example: "X-Brief-Token" or "Authorization"
TOKEN_HEADER_NAME = "Authorization"
api_key_header = APIKeyHeader(name=TOKEN_HEADER_NAME, auto_error=False)

# This simulates our database of users. Each token maps to a specific User Object.
# This logic is checked on EVERY authenticated request.
USERS_DB = {
    "admin@dsgroup.com": {
        "password": "password123",
        "token": "token_ds_admin",
        "user_info": {
            "id": "user_ds_001",
            "email": "admin@dsgroup.com",
            "name": "DS Admin",
            "role": "DS_GROUP",
            "agencyName": None
        }
    },
    "alpha@agency.com": {
        "password": "password123",
        "token": "token_agency_alpha",
        "user_info": {
            "id": "user_ag_001",
            "email": "alpha@agency.com",
            "name": "Alpha User",
            "role": "AGENCY",
            "agencyName": "Agency Alpha"
        }
    },
    "beta@agency.com": {
        "password": "password123",
        "token": "token_agency_beta",
        "user_info": {
            "id": "user_ag_002",
            "email": "beta@agency.com",
            "name": "Beta User",
            "role": "AGENCY",
            "agencyName": "Agency Beta"
        }
    }
}

# Mapping of tokens back to users for verification.
TOKENS_TO_USERS = {v["token"]: v["user_info"] for v in USERS_DB.values()}

async def get_current_user(api_key: str = Depends(api_key_header)):
    """
    Middleware function that runs before your API logic.
    1. Extracts token from the header defined in TOKEN_HEADER_NAME.
    2. Validates it against the TOKENS_TO_USERS database.
    3. Blocks the request if invalid.
    """
    if not api_key:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN, detail=f"Missing {TOKEN_HEADER_NAME} header"
        )
    
    # Support both "Bearer <token>" and raw "<token>"
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
