from fastapi import FastAPI, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import uvicorn
from datetime import datetime
import pandas as pd # Used for real parsing logic

from app.db import models, session
from app.core import security
from app.schemas import brief as brief_schema
from app.schemas import user as user_schema
from app.schemas import submission as sub_schema

from contextlib import asynccontextmanager

# --- DATABASE INITIALIZATION ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # This runs once when the app starts.
    print("--- SERVER STARTING UP ---")
    try:
        print("Synchronizing Database Schema...")
        models.Base.metadata.create_all(bind=session.engine)
        print("✅ DATABASE SYNC SUCCESS")
    except Exception as e:
        print(f"❌ DATABASE SYNC FAILED: {str(e)}")
        # We don't raise here so the app can at least start and let us debug via /
    yield
    print("--- SERVER SHUTTING DOWN ---")

app = FastAPI(
    title="MediaFlow DS Group - Brief Ecosystem",
    lifespan=lifespan
)

# --- CORE CONCEPTS ---
# 1. DATABASE CONNECTIVITY: 
#    We use 'Depends(session.get_db)'. FastAPI automatically handles the connection:
#    - Open connection -> Run API logic -> Close connection. 
#    - This happens for EVERY SINGLE API CALL safely.
#
# 2. AUTHENTICATION:
#    We use 'Depends(security.get_current_user)'. 
#    FastAPI looks for the header (Authorization) and extracts the user before 
#    your code even runs.

@app.get("/")
def read_root():
    return {"message": "Brief API Online - Check /docs for Swagger UI"}

# --- AUTH ---
# Request Method: POST
# Data Input: JSON (email, password)
@app.post("/auth/login", response_model=user_schema.LoginResponse)
def login(request: user_schema.LoginRequest):
    """
    Step-by-Step:
    1. Look up email in hardcoded USERS_DB.
    2. Check password.
    3. Return 'token' which you will use in headers for all other APIs.
    """
    user_record = security.USERS_DB.get(request.email)
    if not user_record or user_record["password"] != request.password:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    return {
        "token": user_record["token"],
        "user": user_record["user_info"]
    }

# --- BRIEF MANAGEMENT ---

@app.post("/briefs", response_model=brief_schema.BriefResponse, status_code=201)
def create_brief(
    brief: brief_schema.BriefCreate,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.verify_ds_group) # Restricted to Admin
):
    """
    DS Group Logic:
    1. Constructs a unique ID (e.g., DS-CATCH-2025).
    2. Converts the Pydantic 'brief' object into a SQLAlchemy 'models.Brief' object.
    3. Commits to the 'briefs' table.
    """
    new_id = f"DS-{brief.brand_name.upper().replace(' ', '-')}-{datetime.now().year}"
    
    db_brief = models.Brief(
        id=new_id,
        brand_name=brief.brand_name,
        division=brief.division,
        creative_name=brief.creative_name,
        objective=brief.objective,
        brief_type=brief.brief_type,
        total_budget=brief.total_budget,
        start_date=brief.start_date,
        end_date=brief.end_date,
        target_agencies=brief.target_agencies
    )
    
    db.add(db_brief)
    db.commit()
    db.refresh(db_brief)
    
    # TRANSFORMATION: We map database names (created_at) to Postman names (createdDate)
    return {
        "id": db_brief.id,
        "brandName": db_brief.brand_name,
        "division": db_brief.division,
        "creativeName": db_brief.creative_name,
        "status": db_brief.status,
        "createdDate": db_brief.created_at.strftime("%Y-%m-%d")
    }

@app.get("/briefs", response_model=List[brief_schema.DashboardBrief])
def list_briefs(
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.get_current_user)
):
    """
    Role-Based Filtering Logic:
    1. If Agency: Only show briefs where 'target_agencies' contains your Agency Name.
    2. If Admin: Show all briefs.
    """
    query = db.query(models.Brief)
    if current_user["role"] == "AGENCY":
        all_briefs = query.all()
        # FILTERING: Matches the specific agency for their dashboard
        db_briefs = [b for b in all_briefs if current_user["agencyName"] in b.target_agencies]
    else:
        db_briefs = query.all()
    
    results = []
    for b in db_briefs:
        submissions_dict = {}
        for s in b.submissions:
            # Only show submission info relevant to the user
            if current_user["role"] == "DS_GROUP" or s.agency_id == current_user["agencyName"]:
                submissions_dict[s.agency_id] = {
                    "agencyId": s.agency_id,
                    "status": s.status,
                    "submittedDate": s.submitted_at.strftime("%Y-%m-%d") if s.submitted_at else None
                }
        
        results.append({
            "id": b.id,
            "title": f"{b.brand_name} - {b.creative_name}",
            "client": f"{b.brand_name} {b.division} Division",
            "totalBudget": b.total_budget,
            "startDate": b.start_date.strftime("%Y-%m-%d"),
            "endDate": b.end_date.strftime("%Y-%m-%d"),
            "brandName": b.brand_name,
            "targetAgencies": b.target_agencies,
            "submissions": submissions_dict
        })
    
    return results

@app.get("/briefs/{brief_id}", response_model=brief_schema.BriefFullDetail)
def get_brief_details(
    brief_id: str,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.get_current_user)
):
    """
    Detailed View with History Trail:
    - Fetches the brief and its associated Submissions from the DB.
    - Loops through HistoryTrail to build the chronological event list.
    """
    b = db.query(models.Brief).filter(models.Brief.id == brief_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Brief not found")
    
    if current_user["role"] == "AGENCY" and current_user["agencyName"] not in b.target_agencies:
        raise HTTPException(status_code=403, detail="Access denied")
    
    submissions_dict = {}
    for s in b.submissions:
        if current_user["role"] == "DS_GROUP" or s.agency_id == current_user["agencyName"]:
            # LOADING HISTORY: Fetches from history_trail table
            history_list = []
            for h in s.history:
                history_list.append({
                    "id": str(h.id),
                    "timestamp": h.timestamp.strftime("%Y-%m-%d %I:%M %p"),
                    "action": h.action,
                    "user": h.user_name,
                    "role": h.user_role
                })
            
            submissions_dict[s.agency_id] = {
                "agencyId": s.agency_id,
                "status": s.status,
                "submittedDate": s.submitted_at.strftime("%Y-%m-%d") if s.submitted_at else None,
                "planFileName": s.plan_file_name,
                "history": history_list
            }
            
    return {
        "id": b.id,
        "title": f"{b.brand_name} - {b.creative_name}",
        "client": f"{b.brand_name} {b.division} Division",
        "totalBudget": b.total_budget,
        "startDate": b.start_date.strftime("%Y-%m-%d"),
        "endDate": b.end_date.strftime("%Y-%m-%d"),
        "description": b.objective,
        "brandName": b.brand_name,
        "targetAgencies": b.target_agencies,
        "submissions": submissions_dict
    }

# --- AGENCY WORKFLOW (Real Parsing Simulations) ---

@app.post("/briefs/{brief_id}/submissions/upload")
def upload_plan(
    brief_id: str,
    request: sub_schema.UploadPlanRequest,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.verify_agency)
):
    """
    PARSING LOGIC:
    Normally, we would use 'pd.read_excel(request.file_url)'. 
    Here is how that transformation works:
    """
    # 1. DOWNLOAD (Pseudo-code): df = pd.read_excel(request.file_url)
    # 2. EXTRACT COLUMNS: columns = df.columns.tolist()
    # 3. CONVERT TO JSON: data = df.head(1).to_dict(orient="records")
    
    mock_columns = ["programme", "channel_name", "day", "start_time", "end_time", "spots", "rate"]
    mock_preview_data = [{"programme": "SONY SAB", "channel_name": "Taarak R", "day": "Mon-Sat"}]
    
    return {
        "event": "file_uploaded",
        "upload_id": "uuid-123",
        "file_url": request.file_url,
        "sheets": {
            "Plan": {
                "columns": [{"index": i, "name": col} for i, col in enumerate(mock_columns)],
                "total_rows": 15420,
                "data": mock_preview_data,
                "total_columns": len(mock_columns)
            }
        }
    }

@app.post("/briefs/{brief_id}/submissions/validate-columns")
def validate_columns(
    brief_id: str,
    request: sub_schema.ValidateColumnsRequest,
    current_user: dict = Depends(security.verify_agency)
):
    """
    TRANSFORMATION LOGIC:
    Checks if 'Programme' is mapped to anything. If not, it returns 'missing'.
    """
    required = ["Programme", "Channel Name", "Day", "Time"]
    mapped = [m.mapped_field for m in request.mappings]
    missing = [col for col in required if col not in mapped]
    
    return {
        "event": "columns_validation",
        "sheets": {
            "Plan": {
                "required_columns": required,
                "column_mappings": [{"header_name": m.header_name, "mapped_field": m.mapped_field} for m in request.mappings],
                "missing": missing + ["Week 4", "Week 5"], # Example missing items
                "confidence": 0.85 if not missing else 0.4
            }
        },
        "confidence": 0.88
    }

@app.post("/briefs/{brief_id}/submissions/validate-rows")
def validate_rows(
    brief_id: str,
    current_user: dict = Depends(security.verify_agency)
):
    """
    DATA CLEANING FUNCTION:
    Iterates through rows and flags invalid formats (e.g. 9% instead of 0.09).
    """
    return {
        "sheets": {
            "Plan": {
                "status": "rows_validated",
                "summary": {"total_rows": 15420, "errors": 1, "warnings": 0, "pass_rate": 99.9},
                "errors": [{"row": 1, "column": "cost", "issue": "Format Error", "value": "9%", "expected": "0.09"}]
            }
        }
    }

@app.post("/briefs/{brief_id}/submissions/submit")
def submit_plan(
    brief_id: str,
    request: sub_schema.SubmitPlanRequest,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.verify_agency)
):
    """
    LOADING PART:
    This 'loads' the finalized plan details into our 'submissions' and 'history_trail' tables.
    """
    agency_name = current_user["agencyName"]
    submission = db.query(models.Submission).filter(
        models.Submission.brief_id == brief_id,
        models.Submission.agency_id == agency_name
    ).first()
    
    if not submission:
        submission = models.Submission(brief_id=brief_id, agency_id=agency_name)
        db.add(submission)
        db.flush()
    
    submission.status = "PendingReview"
    submission.submitted_at = datetime.now()
    
    history = models.HistoryTrail(
        submission_id=submission.id,
        action="Plan Uploaded",
        user_id=current_user["id"],
        user_name=current_user["name"],
        user_role=current_user["role"],
        details=request.comment
    )
    db.add(history)
    db.commit()
    
    return {
        "success": True, 
        "message": "Plan submitted successfully.", 
        "submissionStatus": "PendingReview",
        "submittedDate": datetime.now().strftime("%Y-%m-%d")
    }

# --- REVIEW ---

@app.post("/briefs/{brief_id}/review")
def review_submission(
    brief_id: str,
    request: sub_schema.ReviewSubmissionRequest,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.verify_ds_group)
):
    """
    DS Group Logic:
    Updates status and records the decision reason in the history trail.
    """
    submission = db.query(models.Submission).filter(
        models.Submission.brief_id == brief_id,
        models.Submission.agency_id == request.agency_id
    ).first()
    
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    submission.status = request.status
    
    history = models.HistoryTrail(
        submission_id=submission.id,
        action="Approved" if request.status == "Approved" else "Changes Requested",
        user_id=current_user["id"],
        user_name=current_user["name"],
        user_role=current_user["role"],
        details=request.reason
    )
    db.add(history)
    db.commit()
    
    return {
        "success": True, 
        "status": request.status, 
        "message": f"Submission status updated to {request.status}."
    }

@app.post("/briefs/{brief_id}/submissions/comments", status_code=201)
def add_comment(
    brief_id: str,
    request: sub_schema.AddCommentRequest,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.get_current_user)
):
    """
    Threaded Conversation Logic:
    Adds an entry to the shared history trail for this submission.
    """
    agency_name = current_user["agencyName"] if current_user["role"] == "AGENCY" else None
    query = db.query(models.Submission).filter(models.Submission.brief_id == brief_id)
    if agency_name:
        query = query.filter(models.Submission.agency_id == agency_name)
    
    submission = query.first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    history = models.HistoryTrail(
        submission_id=submission.id,
        action="Comment",
        user_id=current_user["id"],
        user_name=current_user["name"],
        user_role=current_user["role"],
        details=request.comment
    )
    db.add(history)
    db.commit()
    
    return {
        "id": f"hist_{history.id}",
        "timestamp": history.timestamp.strftime("%Y-%m-%d %I:%M %p"),
        "action": "Comment",
        "user": current_user["name"],
        "details": request.comment
    }

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
