from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import List, Optional, Any, Dict, Union, Literal
from app.schemas.user import User
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
    user_name: str = Field(alias="userName") 
    comment: Optional[str] = None 
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
    raw_file_url: Optional[str] = Field(None, alias="rawFileUrl")

    @field_validator("submitted_at", mode="before")
    @classmethod
    def format_datetime(cls, v):
        if isinstance(v, datetime):
            return convert_to_ist(v)
        return v

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class AgencyPlanDetail(AgencyPlanSummary):
    plan_file_name: Optional[str] = Field(None, alias="planFileName")
    plan_file_url: Optional[str] = Field(None, alias="planFileUrl") 
    version_number: int = Field(alias="versionNumber")
    
    # New Fields
    flat_file_path: Optional[str] = Field(None, alias="flatFilePath")
    validated_file_path: Optional[str] = Field(None, alias="validatedFilePath")
    ai_mappings: Optional[Dict] = Field(None, alias="aiMappings")
    human_mappings: Optional[Dict] = Field(None, alias="humanMappings")

    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    creator: Optional[User] = Field(None, alias="createdBy")
    updater: Optional[User] = Field(None, alias="updatedBy")
    history: List[HistoryTrail] = []

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def format_all_dates(cls, v):
        if isinstance(v, datetime):
            return convert_to_ist(v)
        return v

# --- NEW SCHEMAS FOR GCS FLOW ---

class UploadUrlResponse(BaseModel):
    upload_url: str = Field(alias="uploadUrl")
    plan_id: int = Field(alias="planId")
    expires_in: str = Field(alias="expiresIn")

class ValidateColumnsResponse(BaseModel):
    flat_file_url: str = Field(alias="flatFileUrl")
    ai_mappings: Dict[str, str] = Field(alias="aiMappings")
    required_columns: List[str] = Field(alias="requiredColumns")
    optional_columns: List[str] = Field(alias="optionalColumns")

class UpdateColumnsRequest(BaseModel):
    human_mappings: Dict[str, str] = Field(alias="humanMappings")

class UpdateColumnsResponse(BaseModel):
    validated_file_url: str = Field(alias="validatedFileUrl")
    status: str
    
class ReviewSubmissionRequest(BaseModel):
    status: Optional[Literal["APPROVED", "REJECTED"]] = None
    comment: Optional[str] = None

    @model_validator(mode="after")
    def check_exclusive_or(self) -> "ReviewSubmissionRequest":
        if self.status and self.comment:
            raise ValueError("Provide either status or comment, not both.")
        if not self.status and not self.comment:
            raise ValueError("Either status or comment must be provided.")
        return self

class SubmitPlanRequest(BaseModel):
    data: Optional[Dict[str, Any]] = None
    comment: Optional[str] = None

class ReviewResponse(BaseModel):
    status: str
    newPlanStatus: str = Field(alias="newPlanStatus")
    newBriefStatus: Optional[str] = Field(None, alias="newBriefStatus")
    history: HistoryTrail

    model_config = ConfigDict(populate_by_name=True)
