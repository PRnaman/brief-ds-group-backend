from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import uuid
from datetime import datetime

from app.db import models, session
from app.schemas import brief as brief_schema
from app.schemas import submission as sub_schema
from app.core import security

# Create Tables upon startup
models.Base.metadata.create_all(bind=session.engine)

app = FastAPI(title="Brief Ecosystem - Production API")

# --- DATABASE INITIALIZATION (MOCK DATA) ---
# In production, this would be managed via a separate setup/migration script.
def init_mock_data():
    db = session.SessionLocal()
    try:
        # 1. Create Default Client (DS Group)
        ds_group = db.query(models.Client).filter(models.Client.id == security.ID_DS_GROUP).first()
        if not ds_group:
            ds_group = models.Client(id=security.ID_DS_GROUP, name="DS Group")
            db.add(ds_group)
        
        # 2. Create Default Agencies
        ag_alpha = db.query(models.Agency).filter(models.Agency.id == security.ID_AG_ALPHA).first()
        if not ag_alpha:
            ag_alpha = models.Agency(id=security.ID_AG_ALPHA, name="Agency Alpha", contact_email="alpha@agency.com")
            db.add(ag_alpha)
            
        ag_beta = db.query(models.Agency).filter(models.Agency.id == security.ID_AG_BETA).first()
        if not ag_beta:
            ag_beta = models.Agency(id=security.ID_AG_BETA, name="Agency Beta", contact_email="beta@agency.com")
            db.add(ag_beta)
            
        db.commit()
    finally:
        db.close()

init_mock_data()

@app.get("/")
def read_root():
    return {"status": "online", "version": "2.0.0-relational"}

# --- MANAGEMENT ENDPOINTS ---

@app.get("/agencies", response_model=List[dict])
def list_agencies(db: Session = Depends(session.get_db), current_user: dict = Depends(security.get_current_user)):
    """Returns a list of all agencies (used by DS Group to target briefs)."""
    agencies = db.query(models.Agency).all()
    return [{"id": a.id, "name": a.name} for a in agencies]

@app.get("/clients", response_model=List[dict])
def list_clients(db: Session = Depends(session.get_db), current_user: dict = Depends(security.get_current_user)):
    """Returns a list of clients."""
    clients = db.query(models.Client).all()
    return [{"id": c.id, "name": c.name} for c in clients]

# --- BRIEF WORKFLOW ---

@app.post("/briefs", response_model=brief_schema.BriefResponse)
def create_brief(
    brief: brief_schema.BriefCreate,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.verify_ds_group)
):
    """
    DS GROUP ONLY: Creates a new Brief and automatically generates
    'Submission Slots' for every targeted agency.
    """
    # 1. Create the Brief record with all 15+ fields
    db_brief = models.Brief(
        client_id=current_user["client_id"],
        brand_name=brief.brand_name,
        division=brief.division,
        creative_name=brief.creative_name,
        objective=brief.objective,
        brief_type=brief.brief_type,
        total_budget=brief.total_budget,
        start_date=brief.start_date,
        end_date=brief.end_date,
        
        # Demographic/Market fields
        demographics_age=brief.demographics_age,
        demographics_gender=brief.demographics_gender,
        demographics_nccs=brief.demographics_nccs,
        demographics_etc=brief.demographics_etc,
        psychographics=brief.psychographics,
        key_markets=brief.key_markets,
        p1_markets=brief.p1_markets,
        p2_markets=brief.p2_markets,
        edit_durations=brief.edit_durations,
        acd=brief.acd,
        dispersion=brief.dispersion,
        advertisement_link=brief.advertisement_link,
        creative_languages=brief.creative_languages,
        scheduling_preference=brief.scheduling_preference,
        miscellaneous=brief.miscellaneous,
        remarks=brief.remarks,
        
        target_agency_names=brief.target_agencies # Store names for legacy UI preview
    )
    
    db.add(db_brief)
    db.flush() # Get ID for relationships
    
    # 2. AUTO-CREATE SUBMISSION SLOTS
    # We look up the Agencies by their Name (from the list)
    for agency_name in brief.target_agencies:
        # Find the agency ID
        agency = db.query(models.Agency).filter(models.Agency.name == agency_name).first()
        if agency:
            # Create the 'Plan Slot'
            new_slot = models.Submission(
                brief_id=db_brief.id,
                agency_id=agency.id,
                status="DRAFT"
            )
            db.add(new_slot)
            db.flush() # Get slot ID for history
            
            # Initial History Entry
            history = models.HistoryTrail(
                submission_id=new_slot.id,
                action="SLOT_CREATED",
                user_name=current_user["name"],
                details=f"Plan slot created for {agency_name} upon brief creation."
            )
            db.add(history)

    db.commit()
    db.refresh(db_brief)
    
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
    Role-Based Filtering (Relational):
    - Admin: All briefs and all plan slots.
    - Agency: Only briefs where they have an assigned plan slot.
    """
    if current_user["role"] == "DS_GROUP":
        db_briefs = db.query(models.Brief).all()
    else:
        # Fetch only briefs where there is a submission assigned to this agency
        db_briefs = db.query(models.Brief).join(models.Submission).filter(
            models.Submission.agency_id == current_user["agency_id"]
        ).all()
        
    results = []
    for b in db_briefs:
        submissions_dict = {}
        # Filter submissions inside the brief based on who is asking
        for s in b.submissions:
            if current_user["role"] == "DS_GROUP" or s.agency_id == current_user["agency_id"]:
                submissions_dict[s.agency.name] = {
                    "id": s.id,
                    "agencyId": s.agency.name,
                    "status": s.status,
                    "submittedDate": s.submitted_at.strftime("%Y-%m-%d") if s.submitted_at else None
                }
        
        results.append({
            "id": b.id,
            "title": f"{b.brand_name} - {b.creative_name}",
            "client": b.client.name,
            "totalBudget": b.total_budget,
            "startDate": b.start_date.isoformat(),
            "endDate": b.end_date.isoformat(),
            "brandName": b.brand_name,
            "targetAgencies": b.target_agency_names or [],
            "submissions": submissions_dict
        })
        
    return results

@app.get("/briefs/{brief_id}", response_model=brief_schema.BriefFullDetail)
def get_brief_detail(
    brief_id: str,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.get_current_user)
):
    """Fetches full brief details including demographic data and specific plans."""
    db_brief = db.query(models.Brief).filter(models.Brief.id == brief_id).first()
    if not db_brief:
        raise HTTPException(status_code=404, detail="Brief not found")
        
    # Check if this agency has a slot
    if current_user["role"] == "AGENCY":
        has_slot = db.query(models.Submission).filter(
            models.Submission.brief_id == brief_id,
            models.Submission.agency_id == current_user["agency_id"]
        ).first()
        if not has_slot:
            raise HTTPException(status_code=403, detail="You are not authorized to view this brief")

    submissions_dict = {}
    for s in db_brief.submissions:
        if current_user["role"] == "DS_GROUP" or s.agency_id == current_user["agency_id"]:
            # Format history for detail view
            hist_list = []
            for h in s.history:
                hist_list.append({
                    "action": h.action,
                    "user": h.user_name,
                    "comment": h.details,
                    "date": h.timestamp.strftime("%Y-%m-%d %H:%M")
                })
                
            submissions_dict[s.agency.name] = {
                "id": s.id,
                "agencyId": s.agency.name,
                "status": s.status,
                "submittedDate": s.submitted_at.strftime("%Y-%m-%d") if s.submitted_at else None,
                "planFileName": s.plan_file_name,
                "versionNumber": s.version_number,
                "history": hist_list
            }

    return {
        "id": db_brief.id,
        "title": f"{db_brief.brand_name} - {db_brief.creative_name}",
        "client": db_brief.client.name,
        "totalBudget": db_brief.total_budget,
        "startDate": db_brief.start_date.isoformat(),
        "endDate": db_brief.end_date.isoformat(),
        "description": db_brief.objective,
        "brandName": db_brief.brand_name,
        "targetAgencies": db_brief.target_agency_names or [],
        "submissions": submissions_dict,
        # New production fields
        "demographicsAge": db_brief.demographics_age,
        "demographicsGender": db_brief.demographics_gender,
        "demographicsNccs": db_brief.demographics_nccs,
        "demographicsEtc": db_brief.demographics_etc,
        "psychographics": db_brief.psychographics,
        "keyMarkets": db_brief.key_markets,
        "p1Markets": db_brief.p1_markets,
        "p2Markets": db_brief.p2_markets,
        "editDurations": db_brief.edit_durations,
        "acd": db_brief.acd,
        "dispersion": db_brief.dispersion,
        "advertisementLink": db_brief.advertisement_link,
        "creativeLanguages": db_brief.creative_languages,
        "schedulingPreference": db_brief.scheduling_preference,
        "miscellaneous": db_brief.miscellaneous,
        "remarks": db_brief.remarks
    }

# --- GCS UPLOAD HANDSHAKE ---

@app.get("/submissions/{submission_id}/upload")
def request_upload_url(
    submission_id: str,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.verify_agency)
):
    """
    STEP 1: Returns a secure, temporary GCS link for direct upload.
    """
    slot = db.query(models.Submission).filter(
        models.Submission.id == submission_id,
        models.Submission.agency_id == current_user["agency_id"]
    ).first()
    
    if not slot:
        raise HTTPException(status_code=404, detail="Plan slot not found or access denied")
        
    simulated_url = f"https://storage.googleapis.com/mock-bucket/plans/{submission_id}?signature=MOCK_KEY_123"
    return {"uploadUrl": simulated_url, "expiresIn": "10 minutes"}

@app.post("/submissions/{submission_id}/upload")
def confirm_upload(
    submission_id: str,
    payload: sub_schema.UploadPlanRequest,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.verify_agency)
):
    """
    STEP 2: Notifies the server that the GCS upload is finished.
    Flips status to CLIENT_REVIEW.
    """
    slot = db.query(models.Submission).filter(
        models.Submission.id == submission_id,
        models.Submission.agency_id == current_user["agency_id"]
    ).first()
    
    if not slot:
        raise HTTPException(status_code=404, detail="Plan slot not found or access denied")
        
    old_status = slot.status
    slot.status = "CLIENT_REVIEW"
    slot.plan_file_url = payload.file_url 
    slot.submitted_at = datetime.utcnow()
    
    # Audit History
    history = models.HistoryTrail(
        submission_id=slot.id,
        action="PLAN_UPLOADED",
        user_name=current_user["name"],
        details=f"Plan uploaded to GCS. Status changed from {old_status} to CLIENT_REVIEW."
    )
    db.add(history)
    db.commit()
    
    return {"status": "success", "newStatus": slot.status, "fileUrl": slot.plan_file_url}

# --- VALIDATION STUBS ---

@app.post("/submissions/{submission_id}/validate-columns")
def validate_columns(
    submission_id: str,
    payload: sub_schema.ValidateColumnsRequest,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.verify_agency)
):
    """
    AGENCY ONLY: Simulated column validation logic.
    Checks if the mapped headers match the expected schema.
    """
    # Verify access
    slot = db.query(models.Submission).filter(
        models.Submission.id == submission_id,
        models.Submission.agency_id == current_user["agency_id"]
    ).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Plan slot not found")

    # Simulation Logic
    required_fields = ["Date", "Channel", "Impressions", "Cost"]
    mapped_fields = [m.mapped_field for m in payload.mappings]
    
    missing = [f for f in required_fields if f not in mapped_fields]
    
    if missing:
        return {
            "status": "error",
            "message": f"Missing mandatory fields: {', '.join(missing)}",
            "isValid": False
        }
        
    return {
        "status": "success",
        "message": "All mandatory columns mapped correctly.",
        "isValid": True,
        "mappingAccuracy": 0.98,
        "details": [
            {"field": "Date", "confidence": 1.0, "reason": "Exact match"},
            {"field": "Channel", "confidence": 0.95, "reason": "Contextual match (Publisher)"},
            {"field": "Cost", "confidence": 1.0, "reason": "Exact match"},
            {"field": "Impressions", "confidence": 0.90, "reason": "Synonym match (Reach/Impressions)"}
        ]
    }

@app.post("/submissions/{submission_id}/validate-rows")
def validate_rows(
    submission_id: str,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.verify_agency)
):
    """
    AGENCY ONLY: Simulated row-level validation (Data Types, Nulls, etc.)
    """
    return {
        "status": "success",
        "isValid": True,
        "dataQualityScore": 0.92,
        "summary": {
            "totalRows": 150,
            "validRows": 148,
            "errorCount": 0,
            "warningCount": 2,
            "details": "Minor formatting warnings in 'Remarks' column. 2 rows have slightly unusual date formats but were auto-corrected."
        }
    }

@app.post("/submissions/{submission_id}/submit")
def submit_plan(
    submission_id: str,
    payload: sub_schema.SubmitPlanRequest,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.verify_agency)
):
    """
    AGENCY ONLY: Officially submits the plan for Client Review.
    """
    slot = db.query(models.Submission).filter(
        models.Submission.id == submission_id,
        models.Submission.agency_id == current_user["agency_id"]
    ).first()
    
    if not slot:
        raise HTTPException(status_code=404, detail="Plan slot not found")
        
    old_status = slot.status
    slot.status = "CLIENT_REVIEW" # Officially sent to client
    slot.submitted_at = datetime.utcnow()
    
    # Audit History
    history = models.HistoryTrail(
        submission_id=slot.id,
        action="PLAN_SUBMITTED",
        user_name=current_user["name"],
        details=payload.comment or "Plan submitted for review."
    )
    db.add(history)
    db.commit()
    
    return {"status": "success", "newStatus": slot.status}

@app.post("/submissions/{submission_id}/comments")
def add_comment(
    submission_id: str,
    payload: sub_schema.AddCommentRequest,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.get_current_user)
):
    """
    BOTH ROLES: Adds a comment to the history trail for communication.
    """
    slot = db.query(models.Submission).filter(models.Submission.id == submission_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Audit History
    history = models.HistoryTrail(
        submission_id=slot.id,
        action="COMMENT_ADDED",
        user_name=current_user["name"],
        details=payload.comment
    )
    db.add(history)
    db.commit()
    
    return {"status": "success", "message": "Comment added to history trail."}

# --- REVIEW LOGIC ---

@app.post("/submissions/{submission_id}/review")
def review_submission(
    submission_id: str,
    review: sub_schema.ReviewSubmissionRequest,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.verify_ds_group)
):
    """DS GROUP ONLY: Allows approval or requesting revisions."""
    slot = db.query(models.Submission).filter(models.Submission.id == submission_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Submission not found")
        
    old_status = slot.status
    slot.status = review.status
    
    # Audit History
    history = models.HistoryTrail(
        submission_id=slot.id,
        action=f"STATUS_CHANGE: {old_status} -> {review.status}",
        user_name=current_user["name"],
        details=review.reason
    )
    db.add(history)
    db.commit()
    
    return {"status": "success", "newStatus": slot.status}
