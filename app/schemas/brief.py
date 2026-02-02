from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date, datetime

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

    model_config = {
        "populate_by_name": True,
        "alias_generator": lambda s: "".join(
            word.capitalize() if i > 0 else word for i, word in enumerate(s.split("_"))
        ),
    }

from app.schemas.submission import SubmissionSummary, SubmissionDetail
from typing import Dict

class BriefCreate(BriefBase):
    pass

class BriefResponse(BaseModel):
    id: str
    brandName: str
    division: str
    creativeName: str
    status: str
    createdDate: str

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
