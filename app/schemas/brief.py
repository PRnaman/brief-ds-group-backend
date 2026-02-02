from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict
from datetime import date, datetime
import uuid

class BriefBase(BaseModel):
    brand_name: str
    division: str
    creative_name: str
    objective: str = Field(alias="campaignObjective")
    brief_type: str = Field(alias="type")
    total_budget: str
    start_date: date
    end_date: date
    target_agencies: List[str]
    
    # --- New Production Fields ---
    demographics_age: Optional[str] = None
    demographics_gender: Optional[str] = None
    demographics_nccs: Optional[str] = None
    demographics_etc: Optional[str] = None
    psychographics: Optional[str] = None
    key_markets: Optional[str] = None
    p1_markets: Optional[str] = None
    p2_markets: Optional[str] = None
    edit_durations: Optional[str] = None
    acd: Optional[str] = None
    dispersion: Optional[str] = None
    advertisement_link: Optional[str] = None
    creative_languages: Optional[str] = None
    scheduling_preference: Optional[str] = None
    miscellaneous: Optional[str] = None
    remarks: Optional[str] = None

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=lambda s: "".join(
            word.capitalize() if i > 0 else word for i, word in enumerate(s.split("_"))
        )
    )

class BriefCreate(BriefBase):
    pass

class BriefResponse(BaseModel):
    id: str
    brandName: str
    division: str
    creativeName: str
    status: str
    createdDate: str

    model_config = ConfigDict(from_attributes=True)

from app.schemas.submission import SubmissionSummary, SubmissionDetail

class DashboardBrief(BaseModel):
    id: str
    title: str
    client: str
    totalBudget: str
    startDate: str
    endDate: str
    brandName: str
    targetAgencies: List[str]
    submissions: Dict[str, SubmissionSummary]

class BriefFullDetail(BaseModel):
    id: str
    title: str
    client: str
    totalBudget: str
    startDate: str
    endDate: str
    description: str
    brandName: str
    targetAgencies: List[str]
    submissions: Dict[str, SubmissionDetail]
    
    # Include new fields in full detail
    demographicsAge: Optional[str] = None
    demographicsGender: Optional[str] = None
    demographicsNccs: Optional[str] = None
    demographicsEtc: Optional[str] = None
    psychographics: Optional[str] = None
    keyMarkets: Optional[str] = None
    p1Markets: Optional[str] = None
    p2Markets: Optional[str] = None
    editDurations: Optional[str] = None
    acd: Optional[str] = None
    dispersion: Optional[str] = None
    advertisementLink: Optional[str] = None
    creativeLanguages: Optional[str] = None
    schedulingPreference: Optional[str] = None
    miscellaneous: Optional[str] = None
    remarks: Optional[str] = None
