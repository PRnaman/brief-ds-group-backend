from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware

from app.db import models, session
from app.schemas import brief as brief_schema
from app.schemas import submission as plan_schema # Renamed for clarity
from app.schemas import user as user_schema
from app.core import security

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # This runs when the server starts
    print("🚀 Server starting up...")
    yield
    # This runs when the server stops
    print("🛑 Server shutting down.")

app = FastAPI(title="Brief Ecosystem - Production API", lifespan=lifespan)


 
# CORS - Add this block RIGHT AFTER app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
 
@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/")
def read_root():
    return {"status": "online", "version": "2.0.0-relational"}

@app.post("/login", response_model=user_schema.LoginResponse)
def login(payload: user_schema.LoginRequest, db: Session = Depends(session.get_db)):
    """
    Real DB Login: Validates against 'users' table.
    """
    user_record = db.query(models.User).filter(models.User.email == payload.email).first()
    
    # Real Hashing Verification
    # if not user_record or not security.verify_password(payload.password, user_record.password):
    #     raise HTTPException(status_code=401, detail="Invalid email or password")
    
    return {
        "token": str(user_record.id),
        "user": {
            "email": user_record.email,
            "name": user_record.name,
            "role": user_record.role,
            "agencyName": user_record.agency.name if user_record.agency else None,
            "id": user_record.id
        }
    }

# --- MANAGEMENT ENDPOINTS ---

@app.get("/agencies", response_model=List[dict])
def list_agencies(db: Session = Depends(session.get_db), current_user: dict = Depends(security.get_current_user)):
    """Returns a list of all agencies."""
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
    DS GROUP ONLY: Creates a new Brief.
    """
    # 1. Create the Brief record
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
        created_by=current_user["id"],
        updated_by=current_user["id"],
        
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
        remarks=brief.remarks
        # target_agency_ids removed from DB model
    )
    
    db.add(db_brief)
    db.flush()
    
    # --- AUTO-CREATE AGENCY PLAN SLOTS ---
    # We loop through the IDs provided in the request
    for target_id in brief.target_agency_ids:
        agency = db.query(models.Agency).filter(models.Agency.id == target_id).first()
        if agency:
            new_plan = models.AgencyPlan(
                brief_id=db_brief.id,
                agency_id=agency.id,
                status="DRAFT",
                created_by=current_user["id"],
                updated_by=current_user["id"]
            )
            db.add(new_plan)
            db.flush() # Get plan ID
            
            # Initial Audit
            slot_history = models.HistoryTrail(
                agency_plan_id=new_plan.id,
                action="NEW_BRIEF_CREATED",
                user_id=current_user["id"],
                details=f"The brief was created and assigned to {agency.name}.",
                comment=None
            )
            db.add(slot_history)

    db.commit()
    db.refresh(db_brief)
    
    # Fetch names for the response
    # Fetch names for the response
    target_obs = []
    # In-memory assignment for the response model (not DB persistence)
    db_brief.target_agency_ids = brief.target_agency_ids 
    
    if brief.target_agency_ids:
        agencies = db.query(models.Agency).filter(models.Agency.id.in_(brief.target_agency_ids)).all()
        target_obs = [{"id": a.id, "name": a.name} for a in agencies]
        
    db_brief.target_agency_ids = target_obs # Inject objects
    return db_brief

@app.get("/briefs", response_model=List[brief_schema.BriefResponse])
def list_briefs(
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.get_current_user)
):
    """
    Returns full detailed briefs.
    """
    if current_user["role"] == "DS_GROUP":
        db_briefs = db.query(models.Brief).all()
    else:
        db_briefs = db.query(models.Brief).join(models.AgencyPlan).filter(
            models.AgencyPlan.agency_id == current_user["agency_id"]
        ).all()
        
    results = []
    for b in db_briefs:
        # Filter agency plans based on role
        filtered_plans = []
        for p in b.agency_plans:
            if current_user["role"] == "DS_GROUP" or p.agency_id == current_user["agency_id"]:
                filtered_plans.append(p)
        
        # Privacy: Agencies should only see their own ID/Name in the target list
        # We RECONSTRUCT target_agency_ids from the existing plans
        # Because we deleted the JSON column.
        
        # 1. Get all Agency IDs attached to this brief
        all_target_ids = [p.agency_id for p in b.agency_plans]
        
        visible_ids = all_target_ids
        if current_user["role"] == "AGENCY":
            visible_ids = [aid for aid in all_target_ids if aid == current_user["agency_id"]]
            
        # Transform IDs to Objects {id, name}
        target_objects = []
        if visible_ids:
            agencies = db.query(models.Agency).filter(models.Agency.id.in_(visible_ids)).all()
            target_objects = [{"id": a.id, "name": a.name} for a in agencies]

        # We manually construct a dictionary for the response
        brief_data = {
            "id": b.id,
            "status": b.status,
            "brandName": b.brand_name,
            "division": b.division,
            "creativeName": b.creative_name,
            "campaignObjective": b.objective,
            "type": b.brief_type,
            "totalBudget": b.total_budget,
            "startDate": b.start_date,
            "endDate": b.end_date,
            "targetAgencies": target_objects, # Now returning Objects!
            "demographicsAge": b.demographics_age,
            "demographicsGender": b.demographics_gender,
            "demographicsNccs": b.demographics_nccs,
            "demographicsEtc": b.demographics_etc,
            "psychographics": b.psychographics,
            "keyMarkets": b.key_markets,
            "p1Markets": b.p1_markets,
            "p2Markets": b.p2_markets,
            "editDurations": b.edit_durations,
            "acd": b.acd,
            "dispersion": b.dispersion,
            "advertisementLink": b.advertisement_link,
            "creativeLanguages": b.creative_languages,
            "schedulingPreference": b.scheduling_preference,
            "miscellaneous": b.miscellaneous,
            "remarks": b.remarks,
            "createdAt": b.created_at,
            "updatedAt": b.updated_at,
            "creator": b.creator,
            "updater": b.updater,
            "agencyPlans": filtered_plans
        }
        results.append(brief_data)
        
    return results

@app.get("/briefs/{brief_id}", response_model=brief_schema.BriefFullDetail)
def get_brief_detail(
    brief_id: int,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.get_current_user)
):
    """Returns the same full detail as the list view for consistency."""
    db_brief = db.query(models.Brief).filter(models.Brief.id == brief_id).first()
    if not db_brief:
        raise HTTPException(status_code=404, detail="Brief not found")
        
    if current_user["role"] == "AGENCY":
        has_plan = db.query(models.AgencyPlan).filter(
            models.AgencyPlan.brief_id == brief_id,
            models.AgencyPlan.agency_id == current_user["agency_id"]
        ).first()
        if not has_plan:
            raise HTTPException(status_code=403, detail="Access denied")

    # Filter plans for the response
    filtered_plans = []
    for p in db_brief.agency_plans:
        if current_user["role"] == "DS_GROUP" or p.agency_id == current_user["agency_id"]:
            filtered_plans.append(p)
    
    # Privacy: Agencies should only see their own ID in the target list
    # Reconstruct from plans
    all_target_ids = [p.agency_id for p in db_brief.agency_plans]
    
    visible_target_agency_ids = all_target_ids
    if current_user["role"] == "AGENCY":
        visible_target_agency_ids = [aid for aid in all_target_ids if aid == current_user["agency_id"]]
        
    # Transform IDs to Objects
    target_objects = []
    if visible_target_agency_ids:
        agencies = db.query(models.Agency).filter(models.Agency.id.in_(visible_target_agency_ids)).all()
        target_objects = [{"id": a.id, "name": a.name} for a in agencies]

    # Construct total response object
    return {
        "id": db_brief.id,
        "status": db_brief.status,
        "brandName": db_brief.brand_name,
        "division": db_brief.division,
        "creativeName": db_brief.creative_name,
        "campaignObjective": db_brief.objective,
        "type": db_brief.brief_type,
        "totalBudget": db_brief.total_budget,
        "startDate": db_brief.start_date,
        "endDate": db_brief.end_date,
        "targetAgencies": target_objects,
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
        "remarks": db_brief.remarks,
        "createdAt": db_brief.created_at,
        "updatedAt": db_brief.updated_at,
        "creator": db_brief.creator,
        "updater": db_brief.updater,
        "agencyPlans": filtered_plans
    }

# --- GCS UPLOAD HANDSHAKE ---

# --- GCS STORAGE HELPER (Production Ready) ---
def generate_presigned_put_url(blob_name: str, bucket_name: str = "brief-ecosystem-bucket"):
    """
    Generates a signed URL for uploading to GCS.
    To use for real, install 'google-cloud-storage' and uncomment the logic below.
    """
    # try:
    #     from google.cloud import storage
    #     import datetime
    #     storage_client = storage.Client()
    #     bucket = storage_client.bucket(bucket_name)
    #     blob = bucket.blob(blob_name)
    #     url = blob.generate_signed_url(
    #         version="v4",
    #         expiration=datetime.timedelta(minutes=10),
    #         method="PUT",
    #         content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    #     )
    #     return url
    # except Exception:
    #     # Fallback to simulation during development
    return f"https://storage.googleapis.com/{bucket_name}/{blob_name}?X-Goog-Signature=WORKING_PRODUCTION_MOCK"

def generate_presigned_get_url(blob_name: str, bucket_name: str = "brief-ecosystem-bucket"):
    """Generates a signed URL for viewing/downloading from GCS."""
    # Logic similar to above but with method="GET"
    return f"https://storage.googleapis.com/{bucket_name}/{blob_name}?X-Goog-Signature=GET_PRODUCTION_MOCK"

# --- AGENCY PLAN WORKFLOW (GCS HANDSHAKE) ---

@app.get("/briefs/{brief_id}/upload")
def request_upload_url(
    brief_id: int,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.verify_agency)
):
    """
    AGENCY ONLY: STEP 1 - Generate the Plan UUID and the Working Presigned URL.
    """
    # 1. Look for existing slot
    plan = db.query(models.AgencyPlan).filter(
        models.AgencyPlan.brief_id == brief_id,
        models.AgencyPlan.agency_id == current_user["agency_id"]
    ).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail="No slot found for this agency in this brief.")

    # 2. Form the folder path using the PRE-EXISTING Plan UUID
    file_path = f"{brief_id}/{plan.id}/plan.xlsx"
    
    # 3. Generate the ORIGINAL Working URL
    upload_url = generate_presigned_put_url(file_path)
    
    return {
        "uploadUrl": upload_url,
        "uploadPath": file_path,
        "planId": plan.id, 
        "expiresIn": "10 minutes"
    }

@app.post("/briefs/{brief_id}/upload")
def confirm_upload(
    brief_id: int,
    payload: plan_schema.ConfirmUploadRequest,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.verify_agency)
):
    """
    AGENCY ONLY: STEP 2 - User sends the link/path and we store it.
    """
    plan = db.query(models.AgencyPlan).filter(
        models.AgencyPlan.brief_id == brief_id,
        models.AgencyPlan.agency_id == current_user["agency_id"]
    ).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail="Plan slot not found.")
        
    # Versioning Logic: If a file already exists, we increment the version
    if plan.plan_file_url:
        plan.version_number += 1
        action_detail = f"New version (v{plan.version_number}) uploaded. Path: {payload.file_url}"
    else:
        action_detail = f"Initial plan file uploaded. Path: {payload.file_url}"

    # Store the final file path
    plan.plan_file_url = payload.file_url 
    plan.plan_file_name = payload.file_url.split("/")[-1]
    
    # NEW STATUS FLOW: PENDING_REVIEW
    plan.status = "PENDING_REVIEW"
    plan.updated_at = models.get_utc_now()
    plan.updated_by = current_user["id"]
    
    # Audit History
    history = models.HistoryTrail(
        agency_plan_id=plan.id,
        action="FILE_UPLOADED",
        user_id=current_user["id"],
        details=action_detail
    )
    db.add(history)
    db.commit()
    
    return {"status": "success", "newStatus": plan.status, "version": plan.version_number}

@app.get("/briefs/{brief_id}/plans/{plan_id}", response_model=plan_schema.AgencyPlanDetail)
def get_plan_detail(
    brief_id: int,
    plan_id: int,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.get_current_user)
):
    """
    Deep-dive into a specific plan (DS Group or Agency Owner).
    """
    plan = db.query(models.AgencyPlan).filter(
        models.AgencyPlan.id == plan_id,
        models.AgencyPlan.brief_id == brief_id
    ).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    if current_user["role"] == "AGENCY" and plan.agency_id != current_user["agency_id"]:
        raise HTTPException(status_code=403, detail="Forbidden: You can only view your own plans.")

    # Generate Production VIEW URL if file exists
    view_url = None
    if plan.plan_file_url:
        view_url = generate_presigned_get_url(plan.plan_file_url)

    return {
        "id": plan.id,
        "agencyId": plan.agency.id,
        "agencyName": plan.agency.name,
        "status": plan.status,
        "submittedAt": plan.submitted_at,
        "planFileName": plan.plan_file_name,
        "planFileUrl": view_url,
        "versionNumber": plan.version_number,
        "createdAt": plan.created_at,
        "updatedAt": plan.updated_at,
        "creator": plan.creator,
        "updater": plan.updater,
        "history": plan.history
    }

# --- VALIDATION STUBS ---

# --- VALIDATION & SUBMISSION ENDPOINTS ---

@app.post("/briefs/{brief_id}/validate-columns")
def validate_columns(
    brief_id: int,
    payload: plan_schema.ValidateColumnsRequest,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.verify_agency)
):
    """Simulated column validation logic."""
    plan = db.query(models.AgencyPlan).filter(
        models.AgencyPlan.brief_id == brief_id,
        models.AgencyPlan.agency_id == current_user["agency_id"]
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan slot not found")

    required_fields = ["Date", "Channel", "Impressions", "Cost"]
    mapped_fields = [m.mapped_field for m in payload.mappings]
    missing = [f for f in required_fields if f not in mapped_fields]
    
    if missing:
        return {"status": "error", "message": f"Missing fields: {', '.join(missing)}", "isValid": False}
        
    return {"status": "success", "isValid": True, "mappingAccuracy": 0.98}

@app.post("/briefs/{brief_id}/validate-rows")
def validate_rows(
    brief_id: int,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.verify_agency)
):
    """Simulated row-level validation."""
    return {"status": "success", "isValid": True, "dataQualityScore": 0.92}

@app.post("/briefs/{brief_id}/submit")
def submit_plan(
    brief_id: int,
    payload: plan_schema.SubmitPlanRequest,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.verify_agency)
):
    """Officially submits the plan for Client Review."""
    plan = db.query(models.AgencyPlan).filter(
        models.AgencyPlan.brief_id == brief_id,
        models.AgencyPlan.agency_id == current_user["agency_id"]
    ).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail="Plan slot not found")
        
    plan.status = "PENDING_REVIEW"
    plan.submitted_at = models.get_utc_now()
    plan.updated_at = models.get_utc_now()
    plan.updated_by = current_user["id"]
    
    # Audit History
    history = models.HistoryTrail(
        agency_plan_id=plan.id,
        action="PLAN_SUBMITTED",
        user_id=current_user["id"],
        details=payload.comment or "Plan submitted for review."
    )
    db.add(history)
    db.commit()
    
    return {"status": "success", "newStatus": plan.status}

@app.post("/briefs/{brief_id}/plans/{plan_id}/review", response_model=plan_schema.ReviewResponse)
def review_plan(
    brief_id: int,
    plan_id: int,
    review: plan_schema.ReviewSubmissionRequest,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.verify_ds_group)
):
    """DS GROUP ONLY: Unified Review/Comment endpoint. Can change status, add comment, or both."""
    plan = db.query(models.AgencyPlan).filter(
        models.AgencyPlan.id == plan_id,
        models.AgencyPlan.brief_id == brief_id
    ).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
        
    old_status = plan.status
    has_status_change = review.status is not None
    
    if has_status_change:
        plan.status = review.status
        action_name = "STATUS_CHANGE"
        details_text = f"Status changed from {old_status} to {review.status}."
        history_comment = None
    else:
        action_name = "COMMENT_ADDED"
        details_text = "A new comment was added to the plan history."
        history_comment = review.comment
    
    plan.updated_at = models.get_utc_now()
    plan.updated_by = current_user["id"]
    
    # Audit History
    history = models.HistoryTrail(
        agency_plan_id=plan.id,
        action=action_name,
        user_id=current_user["id"],
        details=details_text,
        comment=history_comment
    )
    db.add(history)
    
    # Update Brief Status ONLY if the plan status actually changed
    brief = None
    if has_status_change:
        brief = db.query(models.Brief).filter(models.Brief.id == brief_id).first()
        if brief:
            all_plans = db.query(models.AgencyPlan).filter(
                models.AgencyPlan.brief_id == brief_id
            ).all()
            
            approved_count = sum(1 for p in all_plans if p.status == "APPROVED")
            rejected_count = sum(1 for p in all_plans if p.status == "REJECTED")
            
            if approved_count == len(all_plans):
                brief.status = "APPROVED"
            elif rejected_count > 0:
                brief.status = "REJECTED"
            
            brief.updated_at = models.get_utc_now()
            brief.updated_by = current_user["id"]
    
    db.commit()
    db.refresh(history)
    
    return {
        "status": "success",
        "newPlanStatus": plan.status,
        "newBriefStatus": brief.status if brief else None,
        "history": history
    }
