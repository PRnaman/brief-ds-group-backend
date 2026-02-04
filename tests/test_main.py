import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import engine, get_db
from app.db.models import Base
from app.core import security
from datetime import datetime

client = TestClient(app)

@pytest.fixture(scope="session", autouse=True)
def setup_database():
    # Only for testing: Create tables
    Base.metadata.create_all(bind=engine)
    
    # Seed data for tests
    db = session.SessionLocal()
    try:
        # 1. Clients
        ds_client = models.Client(id=security.ID_DS_GROUP, name="DS Group")
        db.add(ds_client)
        
        # 2. Agencies
        ag_alpha = models.Agency(id=security.ID_AG_ALPHA, name="Agency Alpha")
        ag_beta = models.Agency(id=security.ID_AG_BETA, name="Agency Beta")
        db.add_all([ag_alpha, ag_beta])
        
        # 3. Users
        usr_ds = models.User(
            id=security.USERS_DB["admin@dsgroup.com"]["user_info"]["id"],
            email="admin@dsgroup.com",
            name="DS Admin",
            role="DS_GROUP",
            client_id=security.ID_DS_GROUP
        )
        usr_alpha = models.User(
            id=security.USERS_DB["alpha@agency.com"]["user_info"]["id"],
            email="alpha@agency.com",
            name="Alpha Agent",
            role="AGENCY",
            agency_id=security.ID_AG_ALPHA
        )
        db.add_all([usr_ds, usr_alpha])
        
        db.commit()
    finally:
        db.close()
        
    yield
    # Optional: Base.metadata.drop_all(bind=engine)

# Test data for a full brief
FULL_BRIEF_DATA = {
    "brandName": "Catch Spices",
    "division": "Spices",
    "creativeName": "Sprint 2025",
    "campaignObjective": "Increase market share by 5%",
    "type": "Multimedia",
    "totalBudget": "INR 50,0,000",
    "startDate": "2025-01-01",
    "endDate": "2025-03-31",
    "targetAgencies": ["Agency Alpha", "Agency Beta"],
    "demographicsAge": "18-45",
    "demographicsGender": "All",
    "keyMarkets": "North India",
    "remarks": "Priority campaign"
}

def test_create_brief_and_auto_plans():
    """Verify that creating a brief automatically creates AgencyPlan slots."""
    headers = {"Authorization": "token_ds_admin"}
    response = client.post("/briefs", json=FULL_BRIEF_DATA, headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["brandName"] == "Catch Spices"
    # Verify IST timestamp format in response
    assert "createdAt" in data
    assert len(data["createdAt"]) == 19 # YYYY-MM-DD HH:MM:SS
    
    # Now check if plans exist in the list (FLATTENED structure)
    list_response = client.get("/briefs", headers=headers)
    briefs = list_response.json()
    
    # Find our specific brief
    target_brief = next(b for b in briefs if b["id"] == data["id"])
    assert isinstance(target_brief["agencyPlans"], list)
    assert len(target_brief["agencyPlans"]) == 2
    assert target_brief["agencyPlans"][0]["status"] == "DRAFT"

def test_agency_isolation_flattened():
    """Verify that Agencies only see their own plan within the brief list."""
    # 1. Create a brief targeting both
    headers_admin = {"Authorization": "token_ds_admin"}
    res = client.post("/briefs", json=FULL_BRIEF_DATA, headers=headers_admin)
    brief_id = res.json()["id"]
    
    # 2. Agency Alpha should see the brief and ONLY their plan
    headers_alpha = {"Authorization": "token_agency_alpha"}
    res_alpha = client.get("/briefs", headers=headers_alpha)
    briefs_alpha = res_alpha.json()
    target_alpha = next(b for b in briefs_alpha if b["id"] == brief_id)
    assert len(target_alpha["agencyPlans"]) == 1
    assert target_alpha["agencyPlans"][0]["agencyName"] == "Agency Alpha"

def test_deep_dive_plan_endpoint():
    """Verify the new nested detailed plan endpoint."""
    headers_admin = {"Authorization": "token_ds_admin"}
    res = client.post("/briefs", json=FULL_BRIEF_DATA, headers=headers_admin)
    brief_id = res.json()["id"]
    
    # Get the plan ID
    brief_detail = client.get(f"/briefs/{brief_id}", headers=headers_admin).json()
    plan_id = brief_detail["agencyPlans"][0]["id"]
    
    # Test nested detail endpoint
    plan_res = client.get(f"/briefs/{brief_id}/plans/{plan_id}", headers=headers_admin)
    assert plan_res.status_code == 200
    plan_data = plan_res.json()
    assert plan_data["id"] == plan_id
    assert "history" in plan_data
    assert plan_data["history"][0]["action"] == "SLOT_CREATED"
    assert "updatedAt" in plan_data
    assert "updatedBy" in plan_data

def test_gcs_handshake_brief_centric():
    """Verify the refined GCS handshake using /briefs/{id}/upload."""
    headers_admin = {"Authorization": "token_ds_admin"}
    res = client.post("/briefs", json=FULL_BRIEF_DATA, headers=headers_admin)
    brief_id = res.json()["id"]
    
    headers_alpha = {"Authorization": "token_agency_alpha"}
    
    # 1. Request Upload URL (Uses Brief Context)
    up_res = client.get(f"/briefs/{brief_id}/upload", headers=headers_alpha)
    assert up_res.status_code == 200
    assert brief_id in up_res.json()["uploadUrl"]
    
    # 2. Confirm Upload (Uses Brief Context)
    confirm_res = client.post(
        f"/briefs/{brief_id}/upload", 
        json={"fileUrl": f"{brief_id}/mock_plan_id/plan.xlsx"},
        headers=headers_alpha
    )
    assert confirm_res.status_code == 200
    assert confirm_res.json()["newStatus"] == "CLIENT_REVIEW"

def test_audit_fields_in_history():
    """Verify that user_id (UUID) is captured in history."""
    headers_admin = {"Authorization": "token_ds_admin"}
    res = client.post("/briefs", json=FULL_BRIEF_DATA, headers=headers_admin)
    brief_id = res.json()["id"]
    
    # Get the plan ID to call the Deep Dive
    brief_detail = client.get(f"/briefs/{brief_id}", headers=headers_admin).json()
    plan_id = brief_detail["agencyPlans"][0]["id"]
    
    # Deep Dive
    plan_detail = client.get(f"/briefs/{brief_id}/plans/{plan_id}", headers=headers_admin).json()
    
    assert plan_detail["history"][0]["userName"] == "DS Admin"
