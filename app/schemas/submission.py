from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from datetime import datetime

# History Trail Schemas
class HistoryTrailBase(BaseModel):
    action: str
    details: Optional[str] = None

class HistoryTrail(HistoryTrailBase):
    id: int
    user_name: str
    user_role: str
    timestamp: datetime

    class Config:
        from_attributes = True

# Submission Schemas
class SubmissionBase(BaseModel):
    agency_id: str
    status: str

class Submission(SubmissionBase):
    id: int
    brief_id: str
    plan_file_name: Optional[str] = None
    plan_file_url: Optional[str] = None
    submitted_at: datetime
    history: List[HistoryTrail] = []

    class Config:
        from_attributes = True

class SubmissionSummary(BaseModel):
    agencyId: str
    status: str
    submittedDate: Optional[str] = None

class SubmissionDetail(SubmissionSummary):
    planFileName: Optional[str] = None
    history: List[Dict[str, str]] = []

# Request Schemas for the Agency Workflow
class UploadPlanRequest(BaseModel):
    file_url: str
    
    model_config = {
        "populate_by_name": True,
        "alias_generator": lambda s: "".join(
            word.capitalize() if i > 0 else word for i, word in enumerate(s.split("_"))
        ),
    }

class ColumnMapping(BaseModel):
    header_name: str
    mapped_field: str
    
    model_config = {
        "populate_by_name": True,
        "alias_generator": lambda s: "".join(
            word.capitalize() if i > 0 else word for i, word in enumerate(s.split("_"))
        ),
    }

class ValidateColumnsRequest(BaseModel):
    mappings: List[ColumnMapping]

class SubmitPlanRequest(BaseModel):
    data: Dict[str, Any]
    comment: Optional[str] = None

class AddCommentRequest(BaseModel):
    comment: str

# Request Schema for DS Review
class ReviewSubmissionRequest(BaseModel):
    agency_id: str 
    status: str
    reason: Optional[str] = None

    model_config = {
        "populate_by_name": True,
        "alias_generator": lambda s: "".join(
            word.capitalize() if i > 0 else word for i, word in enumerate(s.split("_"))
        ),
    }
