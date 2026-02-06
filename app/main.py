from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
import yaml
import openpyxl
from openpyxl.utils import get_column_letter
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
                
                # Convert to Pydantic Model explicitly to ensure fields are populated
                p_model = plan_schema.AgencyPlanSummary.model_validate(p)
                
                # Logic: If DB has no plan_file_url, use hardcoded RAW link for testing
                if not p.plan_file_url:
                    signed_url = "https://storage.googleapis.com/brief-ecosystem-bucket/brief_media_files/1/1/raw/plan.xlsx?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=brief-ecosystem-service-account%40brief-ecosystem.iam.gserviceaccount.com%2F20260206%2Fauto%2Fstorage%2Fgoog4_request&X-Goog-Date=20260206T113515Z&X-Goog-Expires=864000&X-Goog-SignedHeaders=host&X-Goog-Signature=1f52b7b51079d8544f514b7e9b38029d5926ec39d5e30538a7985be0b1d3d63b27b049d10e527d498c894200782782161f5f24f56847849e757d590494025aa74068571003714b6c7028104d498305886361664e723055415714392661331776ce35384728518868984920251326402431713508486001888062829023180415"
                    p_model.plan_file_url = signed_url
                
                if not p.plan_file_name:
                    p_model.plan_file_name = "Plan"

                filtered_plans.append(p_model)
        
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
            
            # Convert to Pydantic Model explicitly
            p_model = plan_schema.AgencyPlanSummary.model_validate(p)

            # Logic: If DB has no plan_file_url, use hardcoded RAW link for testing
            if not p.plan_file_url:
                signed_url = "https://storage.googleapis.com/brief-ecosystem-bucket/brief_media_files/1/1/raw/plan.xlsx?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=brief-ecosystem-service-account%40brief-ecosystem.iam.gserviceaccount.com%2F20260206%2Fauto%2Fstorage%2Fgoog4_request&X-Goog-Date=20260206T113515Z&X-Goog-Expires=864000&X-Goog-SignedHeaders=host&X-Goog-Signature=1f52b7b51079d8544f514b7e9b38029d5926ec39d5e30538a7985be0b1d3d63b27b049d10e527d498c894200782782161f5f24f56847849e757d590494025aa74068571003714b6c7028104d498305886361664e723055415714392661331776ce35384728518868984920251326402431713508486001888062829023180415"
                p_model.plan_file_url = signed_url
            
            if not p.plan_file_name:
                p_model.plan_file_name = "Plan"
            
            filtered_plans.append(p_model)
    
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

    # 2. Construct Path: brief_media_files/brief_id/plan_id/raw/plan.xlsx
    upload_path = f"brief_media_files/{brief_id}/{plan.id}/raw/plan.xlsx"
    
    # 3. Generate Signed PUT URL
    upload_url = gcs.get_signed_url(upload_path, method="PUT", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    
    # 4. PERSIST the intended raw path for downstream steps
    plan.raw_file_path = upload_path
    db.commit()

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
    # ... (existing mock implementation - we might deprecate this but keeping for now if needed)
    pass

# --- HELPER: SENIOR API MOCK ---
def _mock_senior_api_extract(gcs_path: str):
    """
    Mocks the Senior API 'map-columns' command with detailed response.
    """
    print(f"DEBUG: Calling Mock Senior API for {gcs_path}")
    # Detailed mock response provided by the user
    return {
      "file_id": "9a130afc-85a9-46c0-921b-ba10ccd407b4",
      "file_path": gcs_path,
      "mappings": [
        {"source_column": "prog_name.sony_sab", "source_column_index": 0, "target_field": "programme", "confidence": 0.9, "match_type": "exact", "reasoning": "Exact match with 'programme'."},
        {"source_column": "ch_name", "source_column_index": 1, "target_field": "channel_name", "confidence": 0.9, "match_type": "exact", "reasoning": "Exact match with 'channel_name'."},
        {"source_column": "day", "source_column_index": 2, "target_field": "day", "confidence": 1.0, "match_type": "exact", "reasoning": "Exact match with 'day'."},
        {"source_column": "vlo.time", "source_column_index": 3, "target_field": "time", "confidence": 0.8, "match_type": "semantic", "reasoning": "Semantic match with 'time'."},
        {"source_column": "avg.dur", "source_column_index": 12, "target_field": "average_duration", "confidence": 1.0, "match_type": "exact", "reasoning": "Exact match with 'average_duration'."},
        {"source_column": "week_1", "source_column_index": 6, "target_field": "week1", "confidence": 1.0, "match_type": "exact", "reasoning": "Exact match with 'week1'."},
        {"source_column": "spots", "source_column_index": 11, "target_field": "spots", "confidence": 1.0, "match_type": "exact", "reasoning": "Exact match with 'spots'."},
        {"source_column": "p1_p2.fct", "source_column_index": 12, "target_field": "fct", "confidence": 0.9, "match_type": "abbreviation", "reasoning": "Abbreviation match with 'fct'."},
        {"source_column": "gross.cost", "source_column_index": 14, "target_field": "gross.cost", "confidence": 1.0, "match_type": "exact", "reasoning": "Exact match with 'gross.cost'."},
        {"source_column": "rate_10_secs", "source_column_index": 15, "target_field": "gross.rate", "confidence": 0.8, "match_type": "semantic", "reasoning": "Semantic match with 'gross.rate'."},
        {"source_column": "nett.cost", "source_column_index": 16, "target_field": "nett.cost", "confidence": 1.0, "match_type": "exact", "reasoning": "Exact match with 'nett.cost'."},
        {"source_column": "nett.rate_10_secs", "source_column_index": 17, "target_field": "nett.rate", "confidence": 0.8, "match_type": "semantic", "reasoning": "Semantic match with 'nett.rate'."},
        {"source_column": "disp", "source_column_index": 18, "target_field": "disp", "confidence": 1.0, "match_type": "exact", "reasoning": "Exact match with 'disp'."},
        {"source_column": "as_per_brk_tvr_hsm.tvr", "source_column_index": 19, "target_field": "as_per_brk_tvr_hsm.tvr", "confidence": 1.0, "match_type": "exact", "reasoning": "Exact match with 'as_per_brk_tvr_hsm.tvr'."},
        {"source_column": "as_per_brk_tvr_hsm.grp", "source_column_index": 20, "target_field": "as_per_brk_tvr_hsm.grp", "confidence": 1.0, "match_type": "exact", "reasoning": "Exact match with 'as_per_brk_tvr_hsm.grp'."},
        {"source_column": "as_per_brk_tvr_hsm.10_secs_grp", "source_column_index": 21, "target_field": "as_per_brk_tvr_hsm.10secgrp", "confidence": 0.9, "match_type": "abbreviation", "reasoning": "Abbreviation match with 'as_per_brk_tvr_hsm.10secgrp'."},
        {"source_column": "as_per_brk_tvr_hsm.cprp", "source_column_index": 22, "target_field": "as_per_brk_tvr_hsm.cprp", "confidence": 1.0, "match_type": "exact", "reasoning": "Exact match with 'as_per_brk_tvr_hsm.cprp'."},
        {"source_column": "hsm_market_details.aots", "source_column_index": 23, "target_field": "hsm_market_details.aots", "confidence": 1.0, "match_type": "exact", "reasoning": "Exact match with 'hsm_market_details.aots'."},
        {"source_column": "hsm_market_details.reach", "source_column_index": 24, "target_field": "hsm_market_details.reach", "confidence": 1.0, "match_type": "exact", "reasoning": "Exact match with 'hsm_market_details.reach'."},
        {"source_column": "hsm_market_details.cpt", "source_column_index": 25, "target_field": "hsm_market_details.cpt", "confidence": 1.0, "match_type": "exact", "reasoning": "Exact match with 'hsm_market_details.cpt'."},
        {"source_column": "hsm_market_details.1", "source_column_index": 26, "target_field": "hsm_market_details.1", "confidence": 1.0, "match_type": "exact", "reasoning": "Exact match with 'hsm_market_details.1'."},
        {"source_column": "hsm_market_details.2", "source_column_index": 27, "target_field": "hsm_market_details.2", "confidence": 1.0, "match_type": "exact", "reasoning": "Exact match with 'hsm_market_details.2'."},
        {"source_column": "hsm_market_details.3", "source_column_index": 28, "target_field": "hsm_market_details.3", "confidence": 1.0, "match_type": "exact", "reasoning": "Exact match with 'hsm_market_details.3'."},
        {"source_column": "hsm_market_details.4", "source_column_index": 29, "target_field": "hsm_market_details.4", "confidence": 1.0, "match_type": "exact", "reasoning": "Exact match with 'hsm_market_details.4'."},
        {"source_column": "hsm_market_details.5", "source_column_index": 30, "target_field": "hsm_market_details.5", "confidence": 1.0, "match_type": "exact", "reasoning": "Exact match with 'hsm_market_details.5'."},
        {"source_column": "as_per_brk_tvr_p1_market.tvr", "source_column_index": 31, "target_field": "as_per_brk_tvr_p1_market.tvr", "confidence": 1.0, "match_type": "exact", "reasoning": "Exact match with 'as_per_brk_tvr_p1_market.tvr'."},
        {"source_column": "as_per_brk_tvr_p1_market.grp", "source_column_index": 32, "target_field": "as_per_brk_tvr_p1_market.grp", "confidence": 1.0, "match_type": "exact", "reasoning": "Exact match with 'as_per_brk_tvr_p1_market.grp'."},
        {"source_column": "as_per_brk_tvr_p1_market.10_secs_grp", "source_column_index": 33, "target_field": "as_per_brk_tvr_p1_market.10secgrp", "confidence": 0.9, "match_type": "abbreviation", "reasoning": "Abbreviation match with 'as_per_brk_tvr_p1_market.10secgrp'."},
        {"source_column": "as_per_brk_tvr_p1_market.cprp", "source_column_index": 34, "target_field": "as_per_brk_tvr_p1_market.cprp", "confidence": 1.0, "match_type": "exact", "reasoning": "Exact match with 'as_per_brk_tvr_p1_market.cprp'."}
      ],
      "unmapped_source_columns": [
        {"source_column": "advertiser_name", "source_column_index": 4, "target_field": "", "confidence": 0.0, "match_type": "unmapped", "reasoning": "Source column 'advertiser_name' has no matching target field"},
        {"source_column": "agency", "source_column_index": 5, "target_field": "", "confidence": 0.0, "match_type": "unmapped", "reasoning": "Source column 'agency' has no matching target field"},
        {"source_column": "wk_2", "source_column_index": 7, "target_field": "", "confidence": 0.0, "match_type": "unmapped", "reasoning": "Source column 'wk_2' has no matching target field"},
        {"source_column": "wk_3", "source_column_index": 8, "target_field": "", "confidence": 0.0, "match_type": "unmapped", "reasoning": "Source column 'wk_3' has no matching target field"},
        {"source_column": "wk_4", "source_column_index": 9, "target_field": "", "confidence": 0.0, "match_type": "unmapped", "reasoning": "Source column 'wk_4' has no matching target field"},
        {"source_column": "wk_5", "source_column_index": 10, "target_field": "", "confidence": 0.0, "match_type": "unmapped", "reasoning": "Source column 'wk_5' has no matching target field"}
      ],
      "data_start_row": 5 
    }

def _transform_senior_api_response(agent_resp: dict):
    """
    Adapts the detailed Senior API response to the format needed by our backend.
    """
    ai_mappings = {}
    
    # Process 'mappings' (Successfully mapped columns)
    for c in agent_resp.get("mappings", []):
         idx = c["source_column_index"]
         target = c["target_field"]
         # We map Index -> Standard Name
         ai_mappings[idx] = target

    # Process 'unmapped_source_columns' (We keep them but mapped to "")
    # UPDATE: User requested NOT to map them to empty strings.
    # If we skip them here, _process_excel_extract won't rename them, 
    # so they will keep their ORIGINAL headers from the raw file.
    
    # for c in agent_resp.get("unmapped_source_columns", []):
    #     idx = c["source_column_index"]
    #     target = c["target_field"] # This is "" in the JSON
    #     ai_mappings[idx] = target

    return {
        "header_row": agent_resp.get("data_start_row", 0) - 1, # Heuristic: Header is usually 1 row before data?
        # User JSON says "data_start_row": 5. Usually user said header is 4. So 5-1 = 4. match.
        "ai_mappings": ai_mappings
    }

# --- HELPER: OPENPYXL TRANSFORMATION ---
def _process_excel_extract(local_input_path: str, local_output_path: str, header_row: int, mappings: Dict[int, str]):
    """
    Uses OpenPyXL to:
    1. Delete rows before the header_row (so header becomes Row 1).
    2. Rename headers in the new Row 1 based on mappings.
    3. Preserve formulas and styles.
    """
    wb = openpyxl.load_workbook(local_input_path)
    ws = wb.active
    
    # 1. Crop Rows: Move data UP instead of deleting rows (to preserve formulas)
    # header_row is 1-based. If header is at 4, we want to move Row 4 to Row 1.
    if header_row > 1:
        offset = header_row - 1
        max_row = ws.max_row
        max_col = ws.max_column
        max_col_letter = get_column_letter(max_col)
        
        # Range to move: From [header_row, 1] to [max_row, max_col]
        move_ref = f"A{header_row}:{max_col_letter}{max_row}"
        
        # Move UP by 'offset' rows
        ws.move_range(move_ref, rows=-offset, translate=True)
        
        # Now delete the empty rows at the bottom (Optional but good for file size)
        # The data that was at [max_row] is now at [max_row - offset].
        # So rows from [max_row - offset + 1] to [max_row] are empty/trash.
        # Actually, ws.max_row might update? Let's treat it safely.
        # We delete from the END.
        ws.delete_rows(max_row - offset + 1, amount=offset)
        
    # 2. Rename Headers (Now at Row 1)
    # mappings is {col_index_0_based: "NewName"}
    for col_idx, new_name in mappings.items():
        cell = ws.cell(row=1, column=col_idx + 1) 
        cell.value = new_name
        
    wb.save(local_output_path)
    return True

# --- HELPER: READ SCHEMA YAML ---
def _get_schema_columns():
    """Reads mandatory/optional columns from local yaml."""
    try:
        with open("schemas_plan.yaml", "r") as f:
            data = yaml.safe_load(f)
            mandatory = [c["name"] for c in data["columns"]["mandatory"]]
            optional = [c["name"] for c in data["columns"].get("optional", [])]
            return mandatory, optional
    except Exception as e:
        print(f"Error reading schema yaml: {e}")
        return [], []

@app.get("/briefs/{brief_id}/plans/{plan_id}/extract-columns", response_model=plan_schema.ValidateColumnsResponse)
def extract_columns(
    brief_id: int,
    plan_id: int,
    db: Session = Depends(session.get_db),
    current_user: dict = Depends(security.verify_agency)
):
    """
    Step 2: Extract Columns (Replaces Validate Columns)
    - Mocks Senior API to parse headers.
    - Transforms file (Crop + Rename) maintaining formulas.
    - Returns AI mappings and Flat File URL.
    """
    # 1. Verify Plan
    plan = db.query(models.AgencyPlan).filter(
        models.AgencyPlan.id == plan_id,
        models.AgencyPlan.brief_id == brief_id,
        models.AgencyPlan.agency_id == current_user["agency_id"]
    ).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # 2. Define Paths
    # Input: brief_media_files/{brief_id}/{plan_id}/raw/plan.xlsx
    # But wait, previous step used: {brief_id}/{plan_id}/raw/plan.xlsx
    # The user asked to CHANGE the path prefix in the implementation plan.
    # We should support the file wherever it was uploaded.
    # For now, let's assume the upload URL generation uses the NEW prefix 'brief_media_files'
    # IF we haven't updated upload-url code yet, we need to handle that.
    # Let's start using the NEW prefix structure for this flow.
    
    raw_blob_name = f"brief_media_files/{brief_id}/{plan_id}/raw/plan.xlsx"
    flat_blob_name = f"brief_media_files/{brief_id}/{plan_id}/flat/plan_flat.xlsx"
    
    local_raw_path = f"tmp/{brief_id}_{plan_id}_raw.xlsx"
    local_flat_path = f"tmp/{brief_id}_{plan_id}_flat.xlsx"
    
    # Ensure tmp directory exists
    os.makedirs("tmp", exist_ok=True)

    # 3. Download Raw
    try:
        gcs.download_file(raw_blob_name, local_raw_path)
    except Exception:
        # Fallback for older upload path without prefix, just in case? 
        # Or better, just Try the old path if new fails for backward compatibility during dev.
        raw_blob_name_old = f"{brief_id}/{plan.id}/raw/plan.xlsx"
        try:
            gcs.download_file(raw_blob_name_old, local_raw_path)
            raw_blob_name = raw_blob_name_old # Update reference
        except Exception as e:
            raise HTTPException(status_code=404, detail="Raw file not found. Please upload first.")

    # 4. Mock Senior API
    senior_response_raw = _mock_senior_api_extract(f"gs://{gcs.BUCKET_NAME}/{raw_blob_name}")
    
    # 5. Transform Response Format
    transformed_resp = _transform_senior_api_response(senior_response_raw)
    header_row = transformed_resp["header_row"]
    ai_mappings = transformed_resp["ai_mappings"] # {0: "name", ...}

    # 6. Transform File (OpenPyXL)
    try:
        _process_excel_extract(local_raw_path, local_flat_path, header_row, ai_mappings)
    except Exception as e:
        print(f"Excel processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process Excel file: {str(e)}")
        
    # 6. Upload Flat File
    try:
        gcs.upload_file(local_flat_path, flat_blob_name, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload flat file: {str(e)}")

    # 7. Update DB
    plan.flat_file_path = flat_blob_name
    # Pydantic/SQLAlchemy expects keys as strings for JSON usually, let's ensure compatibility
    # ai_mappings keys are ints (0, 1, 2). JSON supports string keys primarily.
    # Convert keys to string for DB storage to be safe
    db_mappings = {str(k): v for k, v in ai_mappings.items()}
    plan.ai_mappings = db_mappings
    db.commit()
    
    # 8. Get Schema Columns
    mandatory, optional = _get_schema_columns()
    
    # 9. Generate Signed URL for Flat File
    flat_url = gcs.get_signed_url(flat_blob_name, method="GET")
    
    # 10. Return Response
    # Convert int keys back to string for Pydantic response if schema says Dict[str, str]
    response_mappings = {str(k): v for k, v in ai_mappings.items()} 
    
    # Clean up local files
    if os.path.exists(local_raw_path): os.remove(local_raw_path)
    if os.path.exists(local_flat_path): os.remove(local_flat_path)

    return {
        "flatFileUrl": flat_url,
        "aiMappings": response_mappings,
        "requiredColumns": mandatory,
        "optionalColumns": optional
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
    plan.raw_file_path = f"brief_media_files/{brief_id}/{plan.id}/raw/plan.xlsx" # Consistent prefix
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

    # 1. Define Paths Dynamically
    raw_path = f"brief_media_files/{brief_id}/{plan.id}/raw/plan.xlsx"
    local_raw = f"tmp/update_raw_{plan.id}.xlsx"
    local_validated = f"tmp/update_validated_{plan.id}.xlsx"
    os.makedirs("tmp", exist_ok=True)

    # 2. Merge Mappings
    # The payload 'human_mappings' is likely { "0": "programme", ... }
    final_mappings = (plan.ai_mappings or {}).copy()
    for k, v in payload.human_mappings.items():
        if v:
            final_mappings[str(k)] = v 

    try:
        # 3. Download Raw File
        gcs.download_file(raw_path, local_raw)
        
        # 3. Re-process (Crop rows + Rename + DELETE UNMAPPED)
        # We use header_row=4 (Row 5) as per current Mock logic.
        _process_excel_extract(
            local_raw, 
            local_validated, 
            header_row=4, 
            mappings={int(k): v for k, v in final_mappings.items()}
        )
        
        # 4. Upload to GCS
        validated_blob = f"brief_media_files/{brief_id}/{plan.id}/validated/plan_final.xlsx"
        gcs.upload_file(local_validated, validated_blob)
        
        # 5. Update DB
        plan.human_mappings = payload.human_mappings
        plan.validated_column_file_path = validated_blob
        plan.plan_file_url = validated_blob
        plan.plan_file_name = "plan_final.xlsx"
        plan.updated_at = models.get_utc_now()
        
        # 6. History
        history = models.HistoryTrail(
            agency_plan_id=plan.id,
            action="COLUMNS_UPDATED",
            user_id=current_user["id"],
            details="User confirmed/updated column mappings. Final file generated."
        )
        db.add(history)
        db.commit()
        
        # 7. Generate Signed URL
        final_url = gcs.get_signed_url(validated_blob, method="GET")
        
        return {
            "validatedFileUrl": final_url,
            "status": "success"
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")
    finally:
        if os.path.exists(local_raw): os.remove(local_raw)
        if os.path.exists(local_validated): os.remove(local_validated)

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

    print(plan)    
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    if current_user["role"] == "AGENCY" and plan.agency_id != current_user["agency_id"]:
        raise HTTPException(status_code=403, detail="Forbidden: You can only view your own plans.")

    # Generate Production VIEW URL if file exists
    view_url = None
    
    # if plan.validated_file_path:
    #     view_url = gcs.get_signed_url(plan.validated_file_path, method="GET")
    # elif plan.flat_file_path:
    #     view_url = gcs.get_signed_url(plan.flat_file_path, method="GET") # Fallback

    # Logic: If DB has no plan_file_url, use hardcoded RAW link for testing
    final_plan_url = plan.plan_file_url
    if not final_plan_url:
        final_plan_url = "https://storage.googleapis.com/brief-ecosystem-bucket/brief_media_files/1/1/raw/plan.xlsx?X-Goog-Algorithm=GOOG4-RSA-SHA256&X-Goog-Credential=brief-ecosystem-service-account%40brief-ecosystem.iam.gserviceaccount.com%2F20260206%2Fauto%2Fstorage%2Fgoog4_request&X-Goog-Date=20260206T113515Z&X-Goog-Expires=864000&X-Goog-SignedHeaders=host&X-Goog-Signature=1f52b7b51079d8544f514b7e9b38029d5926ec39d5e30538a7985be0b1d3d63b27b049d10e527d498c894200782782161f5f24f56847849e757d590494025aa74068571003714b6c7028104d498305886361664e723055415714392661331776ce35384728518868984920251326402431713508486001888062829023180415"

    final_plan_name = plan.plan_file_name or "Plan"

    return {
        "id": plan.id,
        "agencyId": plan.agency.id,
        "agencyName": plan.agency.name,
        "status": plan.status,
        "submittedAt": plan.submitted_at,
        "planFileName": final_plan_name,
        "planFileUrl": final_plan_url,
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
    current_user: dict = Depends(security.get_current_user)
):
    """
    Unified Review/Comment endpoint.
    - DS_GROUP: Can change status (APPROVE/REJECT) and add comments.
    - AGENCY: Can ONLY add comments (Status change forbidden), and only on THEIR OWN plan.
    """
    plan = db.query(models.AgencyPlan).filter(
        models.AgencyPlan.id == plan_id,
        models.AgencyPlan.brief_id == brief_id
    ).first()
    
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    # --- PERMISSION CHECK ---
    is_ds_group = current_user["role"] == "DS_GROUP"
    is_agency_owner = current_user["role"] == "AGENCY" and plan.agency_id == current_user["agency_id"]
    
    if not (is_ds_group or is_agency_owner):
        raise HTTPException(status_code=403, detail="Forbidden: You cannot review/comment on this plan.")

    # --- STATUS CHANGE CHECK ---
    has_status_change = review.status is not None
    
    # Agency cannot change status
    if not is_ds_group and has_status_change:
        raise HTTPException(status_code=403, detail="Forbidden: Agency users cannot change plan status.")
        
    old_status = plan.status
    
    if has_status_change:
        plan.status = review.status
        action_name = "STATUS_CHANGE"
        details_text = f"Status changed from {old_status} to {review.status}."
        history_comment = review.comment # Comment is optional with status change
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
    
    # Update Brief Status ONLY if the plan status actually changed AND user is DS_GROUP (Redundant check but safe)
    brief = None
    if has_status_change and is_ds_group:
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
