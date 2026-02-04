from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Optional, Dict
from datetime import date, datetime, timedelta, timezone
import uuid

def convert_to_ist(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    # Assuming input is already UTC or naive (stored as IST in DB but Python might see it as naive)
    # The requirement was to store in IST. If stored as IST, we just format it.
    return dt.strftime("%Y-%m-%d %H:%M:%S")

class BriefBase(BaseModel):
    brand_name: str = Field(alias="brandName")
    division: str
    creative_name: str = Field(alias="creativeName")
    objective: str = Field(alias="campaignObjective")
    brief_type: str = Field(alias="type")
    total_budget: str = Field(alias="totalBudget")
    start_date: date = Field(alias="startDate")
    end_date: date = Field(alias="endDate")
    target_agency_ids: List[int] = Field(alias="targetAgencies")
    
    # --- Production Fields ---
    demographics_age: Optional[str] = Field(None, alias="demographicsAge")
    demographics_gender: Optional[str] = Field(None, alias="demographicsGender")
    demographics_nccs: Optional[str] = Field(None, alias="demographicsNccs")
    demographics_etc: Optional[str] = Field(None, alias="demographicsEtc")
    psychographics: Optional[str] = None
    key_markets: Optional[str] = Field(None, alias="keyMarkets")
    p1_markets: Optional[str] = Field(None, alias="p1Markets")
    p2_markets: Optional[str] = Field(None, alias="p2Markets")
    edit_durations: Optional[str] = Field(None, alias="editDurations")
    acd: Optional[str] = None
    dispersion: Optional[str] = None
    advertisement_link: Optional[str] = Field(None, alias="advertisementLink")
    creative_languages: Optional[str] = Field(None, alias="creativeLanguages")
    scheduling_preference: Optional[str] = Field(None, alias="schedulingPreference")
    miscellaneous: Optional[str] = None
    remarks: Optional[str] = None

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=None # We use explicit aliases for clarity
    )

class BriefCreate(BriefBase):
    pass

from app.schemas.submission import AgencyPlanSummary

class AgencyTarget(BaseModel):
    id: int
    name: str

class BriefResponse(BriefBase):
    id: int
    status: str
    
    # Override: Return objects, not just IDs
    target_agency_ids: List[AgencyTarget] = Field(alias="targetAgencies")
    
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    created_by: Optional[int] = Field(None, alias="createdBy")
    updated_by: Optional[int] = Field(None, alias="updatedBy")
    
    agency_plans: List[AgencyPlanSummary] = Field(alias="agencyPlans")

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def format_datetime(cls, v):
        if isinstance(v, datetime):
            return convert_to_ist(v)
        return v

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

# Dashboard view is now same as Detailed view (Flattened)
DashboardBrief = BriefResponse
BriefFullDetail = BriefResponse
