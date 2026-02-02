import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.session import engine, get_db
from app.db.models import Base
from app.core import security

client = TestClient(app)

# Test data for a full brief
FULL_BRIEF_DATA = {
    "brand_name": "Catch Spices",
    "division": "Spices",
    "creative_name": "Sprint 2025",
    "campaignObjective": "Increase market share by 5%",
    "type": "Multimedia",
    "total_budget": "INR 50,00,000",
    "start_date": "2025-01-01",
    "end_date": "2025-03-31",
    "target_agencies": ["Agency Alpha", "Agency Beta"],
    "demographics_age": "18-45",
    "demographics_gender": "All",
    "key_markets": "North India",
    "remarks": "Priority campaign"
}

def test_create_brief_and_auto_slots():
    """Verify that creating a brief automatically creates plan slots for targeted agencies."""
    headers = {"Authorization": "token_ds_admin"}
    response = client.post("/briefs", json=FULL_BRIEF_DATA, headers=headers)
    
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["brandName"] == "Catch Spices"
    
    # Now check if slots exist in the list
    list_response = client.get("/briefs", headers=headers)
    briefs = list_response.json()
    
    # Find our specific brief
    target_brief = next(b for b in briefs if b["id"] == data["id"])
    assert "Agency Alpha" in target_brief["submissions"]
    assert "Agency Beta" in target_brief["submissions"]
    assert target_brief["submissions"]["Agency Alpha"]["status"] == "DRAFT"

def test_agency_isolation():
    """Verify that Agency Alpha cannot see Agency Beta's information or other briefs."""
    # 1. Create a brief targeting only Agency Alpha
    headers_admin = {"Authorization": "token_ds_admin"}
    brief_alpha_only = FULL_BRIEF_DATA.copy()
    brief_alpha_only["target_agencies"] = ["Agency Alpha"]
    
    res = client.post("/briefs", json=brief_alpha_only, headers=headers_admin)
    brief_id = res.json()["id"]
    
    # 2. Agency Alpha should see it
    headers_alpha = {"Authorization": "token_agency_alpha"}
    res_alpha = client.get("/briefs", headers=headers_alpha)
    assert any(b["id"] == brief_id for b in res_alpha.json())
    
    # 3. Agency Beta should NOT see it
    headers_beta = {"Authorization": "token_agency_beta"}
    res_beta = client.get("/briefs", headers=headers_beta)
    assert not any(b["id"] == brief_id for b in res_beta.json())

def test_get_brief_detail_new_fields():
    """Verify that all new fields are correctly returned in the detail view."""
    headers = {"Authorization": "token_ds_admin"}
    res = client.post("/briefs", json=FULL_BRIEF_DATA, headers=headers)
    brief_id = res.json()["id"]
    
    detail_res = client.get(f"/briefs/{brief_id}", headers=headers)
    assert detail_res.status_code == 200
    data = detail_res.json()
    
    assert data["demographicsAge"] == "18-45"
    assert data["keyMarkets"] == "North India"
    assert data["remarks"] == "Priority campaign"

def test_presigned_url_access():
    """Verify that only the assigned agency can request an upload URL."""
    headers_admin = {"Authorization": "token_ds_admin"}
    res = client.post("/briefs", json=FULL_BRIEF_DATA, headers=headers_admin)
    brief_id = res.json()["id"]
    
    # Get the submission ID for Agency Alpha
    detail = client.get(f"/briefs/{brief_id}", headers=headers_admin).json()
    submission_id = detail["submissions"]["Agency Alpha"]["id"]
    
    # 1. Agency Alpha (Owner) should get a URL
    headers_alpha = {"Authorization": "token_agency_alpha"}
    url_res = client.get(f"/submissions/{submission_id}/upload", headers=headers_alpha)
    assert url_res.status_code == 200
    assert "uploadUrl" in url_res.json()
    
    # 2. Agency Beta (Stranger) should be blocked (404/403)
    headers_beta = {"Authorization": "token_agency_beta"}
    bad_res = client.get(f"/submissions/{submission_id}/upload", headers=headers_beta)
    assert bad_res.status_code == 404

def test_audit_history_creation():
    """Verify that history rows are created automatically."""
    headers_admin = {"Authorization": "token_ds_admin"}
    res = client.post("/briefs", json=FULL_BRIEF_DATA, headers=headers_admin)
    brief_id = res.json()["id"]
    
    detail = client.get(f"/briefs/{brief_id}", headers=headers_admin).json()
    submission_alpha = detail["submissions"]["Agency Alpha"]
    
    assert len(submission_alpha["history"]) > 0
    assert submission_alpha["history"][0]["action"] == "SLOT_CREATED"
