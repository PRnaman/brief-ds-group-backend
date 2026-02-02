from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Any, Dict
from datetime import datetime

# History Trail Schemas
class HistoryTrailBase(BaseModel):
    action: str
    details: Optional[str] = None

class HistoryTrail(HistoryTrailBase):
    id: int
    user_name: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)

# Submission Schemas
class SubmissionBase(BaseModel):
    agency_id: str
    status: str

class Submission(SubmissionBase):
    id: str
    brief_id: str
    version_number: int
    plan_file_name: Optional[str] = None
    plan_file_url: Optional[str] = None
    submitted_at: Optional[datetime] = None
    last_updated: datetime
    history: List[HistoryTrail] = []

    model_config = ConfigDict(from_attributes=True)

class SubmissionSummary(BaseModel):
    id: Optional[str] = None
    agencyId: str
    status: str
    submittedDate: Optional[str] = None

class SubmissionDetail(SubmissionSummary):
    planFileName: Optional[str] = None
    versionNumber: int
    history: List[Dict[str, Any]] = []

# Request Schemas for the Agency Workflow
class UploadPlanRequest(BaseModel):
    file_url: str

class ColumnMapping(BaseModel):
    header_name: str
    mapped_field: str

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
    status: str # CLIENT_REVIEW, AGENCY_REVISION, APPROVED
    reason: Optional[str] = None
