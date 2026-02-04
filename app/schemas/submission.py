from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import List, Optional, Any, Dict
from datetime import datetime

def convert_to_ist(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    return dt.strftime("%Y-%m-%d %H:%M:%S")

# History Trail Schemas
class HistoryTrailBase(BaseModel):
    action: str
    details: Optional[str] = None

class HistoryTrail(HistoryTrailBase):
    id: int
    user_name: str = Field(alias="userName") # Derive from property
    comment: Optional[str] = None # Added comment field
    created_at: datetime = Field(alias="createdAt")

    @field_validator("created_at", mode="before")
    @classmethod
    def format_datetime(cls, v):
        if isinstance(v, datetime):
            return convert_to_ist(v)
        return v

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

# Agency Plan Schemas
class AgencyPlanSummary(BaseModel):
    id: Optional[int] = None
    agency_id: int = Field(alias="agencyId")
    agency_name: str = Field(alias="agencyName")
    status: str
    submitted_at: Optional[datetime] = Field(None, alias="submittedAt")

    @field_validator("submitted_at", mode="before")
    @classmethod
    def format_datetime(cls, v):
        if isinstance(v, datetime):
            return convert_to_ist(v)
        return v

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class AgencyPlanDetail(AgencyPlanSummary):
    plan_file_name: Optional[str] = Field(None, alias="planFileName")
    plan_file_url: Optional[str] = Field(None, alias="planFileUrl") # This will be the VIEW URL
    version_number: int = Field(alias="versionNumber")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    created_by: Optional[int] = Field(None, alias="createdBy")
    updated_by: Optional[int] = Field(None, alias="updatedBy")
    history: List[HistoryTrail] = []

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def format_all_dates(cls, v):
        if isinstance(v, datetime):
            return convert_to_ist(v)
        return v

# Request Schemas
class ConfirmUploadRequest(BaseModel):
    file_url: str = Field(alias="fileUrl")

class ColumnMapping(BaseModel):
    header_name: str = Field(alias="headerName")
    mapped_field: str = Field(alias="mappedField")

class ValidateColumnsRequest(BaseModel):
    mappings: List[ColumnMapping]

class SubmitPlanRequest(BaseModel):
    data: Dict[str, Any]
    comment: Optional[str] = None

class AddCommentRequest(BaseModel):
    comment: str

class ReviewSubmissionRequest(BaseModel):
    status: str 
    reason: Optional[str] = None
