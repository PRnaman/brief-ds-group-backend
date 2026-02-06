from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
import yaml
# Load environment variables from .env file
load_dotenv()

print(f"DEBUG: GCS_BUCKET_NAME={os.getenv('GCS_BUCKET_NAME')}")
print(f"DEBUG: GOOGLE_APPLICATION_CREDENTIALS={os.getenv('GOOGLE_APPLICATION_CREDENTIALS')}")

from app.db import models, session
from app.schemas import brief as brief_schema
from app.schemas import submission as plan_schema # Renamed for clarity
from app.schemas import user as user_schema
from app.core import security, gcs, exceptions

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
# CORS - Add this block RIGHT AFTER app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

# Register Global Exception Handler
app.add_exception_handler(exceptions.BriefAppException, exceptions.global_exception_handler)
 
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
    if not user_record or not security.verify_password(payload.password, user_record.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
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

# --- AGENCY PLAN WORKFLOW (GCS HANDSHAKE) ---

@app.get("/briefs/{brief_id}/plans/{plan_id}/upload-url", response_model=plan_schema.UploadUrlResponse)
def get_upload_url(
    brief_id: int,
    plan_id: int,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.verify_agency)
):
    """
    Step 1: Get the Presigned URL for uploading the RAW file.
    """
    # 1. Verify Plan Ownership
    plan = db.query(models.AgencyPlan).filter(
        models.AgencyPlan.id == plan_id,
        models.AgencyPlan.brief_id == brief_id,
        models.AgencyPlan.agency_id == current_user["agency_id"]
    ).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found or access denied.")

    # 2. Construct Path: brief_id/plan_id/raw/plan.xlsx
    # We enforce a standard filename 'plan.xlsx' to keep things simple and predictable.
    upload_path = f"{brief_id}/{plan.id}/raw/plan.xlsx"
    
    # 3. Generate Signed PUT URL
    upload_url = gcs.get_signed_url(upload_path, method="PUT", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    
    return {
        "uploadUrl": upload_url,
        "planId": plan.id,
        "expiresIn": "15 minutes"
    }


def _external_validation_service_mock(raw_path: str, brief_id: int, plan_id: int):
    """
    Simulates the External Validation Service (Validation Logic).
    - It now physically copies the RAW file to the FLAT path in GCS 
      so downstream testing (Step 3) works with real files.
    """
    import yaml
    flat_path = f"{brief_id}/{plan_id}/flat/plan_flat.xlsx"
    
    # 1. PHYSICAL FILE HANDSHAKE (Mocking the external service upload)
    try:
        # We use our gcs client to copy the file to simulate the service 'creating' it
        bucket = gcs._get_bucket()
        source_blob = bucket.blob(raw_path)
        # In reality, this would be a different file, but for testing, we just copy it.
        bucket.copy_blob(source_blob, bucket, flat_path)
        print(f"DEBUG: Mock service copied {raw_path} to {flat_path}")
    except Exception as e:
        print(f"DEBUG: Mock service failed to create flat file: {e}")

    # 2. Load Configuration from YAML
    yaml_path = os.path.join("app", "core", "columns.yaml")
    with open(yaml_path, "r") as f:
        config = yaml.safe_load(f)
    
    required_columns = config.get("required_columns", [])
    optional_columns = config.get("optional_columns", [])
    
    # 3. HARDCODED MOCK AI PREDICTIONS
    # These represent the mapping of [Standard Column] -> [Header in your file]
    ai_mappings = {
        "Date": "Campaign Date", 
        "Impressions": "Est. Impressions",
        "Cost": "Total Cost",
        "Channel": "Media Channel"
    }
    
    return {
        "flat_path": flat_path,
        "ai_mappings": ai_mappings,
        "required_columns": required_columns,
        "optional_columns": optional_columns
    }

@app.post("/briefs/{brief_id}/plans/{plan_id}/validate-columns", response_model=plan_schema.ValidateColumnsResponse)
def validate_columns(
    brief_id: int,
    plan_id: int,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.verify_agency)
):
    """
    Step 2: Trigger Senior API to validate raw file and generate mappings.
    """
    plan = db.query(models.AgencyPlan).filter(
        models.AgencyPlan.id == plan_id,
        models.AgencyPlan.brief_id == brief_id,
        models.AgencyPlan.agency_id == current_user["agency_id"]
    ).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    # 1. Check if RAW file exists (skipped for now, assumed flow)
    raw_path = f"{brief_id}/{plan.id}/raw/plan.xlsx"
    
    # 2. Call External Validation Service (Mock)
    validation_result = _external_validation_service_mock(raw_path, brief_id, plan.id)
    
    # 3. STRICT VALIDATION: Check if all REQUIRED columns are present in the AI Mappings
    # (i.e., did the AI find a match for every required column?)
    # or simple check if the FILE has the potential to map to them. 
    # For this mock, we assume 'ai_mappings' keys are the Standard Columns found.
    
    found_columns = validation_result["ai_mappings"].keys() # keys are the Standard Names
    missing_required = [col for col in validation_result["required_columns"] if col not in found_columns]
    
    if missing_required:
        raise HTTPException(
            status_code=400, 
            detail=f"Validation Failed: Missing required columns: {', '.join(missing_required)}"
        )
    
    # 4. Update DB
    plan.flat_file_path = validation_result["flat_path"]
    plan.ai_mappings = validation_result["ai_mappings"]
    plan.raw_file_path = raw_path # Persist the raw path
    plan.updated_at = models.get_utc_now()
    plan.updated_by = current_user["id"]
    
    # 5. Log History
    history = models.HistoryTrail(
        agency_plan_id=plan.id,
        action="COLUMNS_VALIDATED",
        user_id=current_user["id"],
        details="AI Validation completed. Columns mapped."
    )
    db.add(history)
    db.commit()
    
    # 6. Generate View URL
    flat_url = gcs.get_signed_url(plan.flat_file_path, method="GET")
    
    return {
        "flatFileUrl": flat_url,
        "aiMappings": plan.ai_mappings,
        "requiredColumns": validation_result["required_columns"],
        "optionalColumns": validation_result["optional_columns"]
    }

@app.post("/briefs/{brief_id}/plans/{plan_id}/update-columns", response_model=plan_schema.UpdateColumnsResponse)
def update_columns(
    brief_id: int,
    plan_id: int,
    payload: plan_schema.UpdateColumnsRequest,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.verify_agency)
):
    """
    Step 3: Confirm mappings, rename columns, and finalize the file.
    """
    plan = db.query(models.AgencyPlan).filter(
        models.AgencyPlan.id == plan_id,
        models.AgencyPlan.brief_id == brief_id,
        models.AgencyPlan.agency_id == current_user["agency_id"]
    ).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found.")

    if not plan.flat_file_path:
        raise exceptions.ValidationException("Flat file not found. Please run validation first.")

    # 1. Read Flat File (Simulated Read)
    # Ideally: content = gcs.read_file(plan.flat_file_path)
    # df = pd.read_excel(io.BytesIO(content))
    # df.rename(columns=payload.human_mappings, inplace=True)
    
    # 2. Upload Validated File (Simulated Upload)
    validated_path = f"{brief_id}/{plan.id}/validated_column/plan_final.xlsx"
    
    # gcs.upload_file_from_memory(df.to_excel(), validated_path) # Future implementation
    
    
    # Store the final file path
    plan.validated_column_file_path = validated_path # New Column Name
    plan.plan_file_url = validated_path # Point legacy URL to the latest validated version
    plan.plan_file_name = validated_path.split("/")[-1]
    
    plan.status = "DRAFT" # Still draft until submitted
    plan.updated_at = models.get_utc_now()
    plan.updated_by = current_user["id"]
    
    # 4. Log History
    history = models.HistoryTrail(
        agency_plan_id=plan.id,
        action="COLUMNS_UPDATED",
        user_id=current_user["id"],
        details="User confirmed/updated column mappings."
    )
    db.add(history)
    db.commit()
    
    # 5. Return Final URL
    final_url = gcs.get_signed_url(validated_path, method="GET")
    
    return {
        "validatedFileUrl": final_url,
        "status": "success"
    }

# Removed old endpoints: request_upload_url, confirm_upload, validate_rows

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
    if plan.validated_file_path:
        view_url = gcs.get_signed_url(plan.validated_file_path, method="GET")
    elif plan.flat_file_path:
        view_url = gcs.get_signed_url(plan.flat_file_path, method="GET") # Fallback

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

# validate columns and rows replaced by new flow

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
