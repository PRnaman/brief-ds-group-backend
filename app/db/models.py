from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Date
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, index=True) # UUID or hardcoded ID
    email = Column(String, unique=True, index=True)
    name = Column(String)
    role = Column(String) # DS_GROUP or AGENCY
    agency_name = Column(String, nullable=True) # Only for agencies

class Brief(Base):
    __tablename__ = "briefs"
    
    id = Column(String, primary_key=True, index=True) # e.g., DS-CATCH-2025-01
    brand_name = Column(String, index=True)
    division = Column(String)
    creative_name = Column(String)
    objective = Column(Text)
    brief_type = Column(String) # multimedia, digital, etc.
    total_budget = Column(String) # e.g., "₹8,50,00,000"
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(String, default="Active")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # JSON list of agency IDs targeted for this brief
    target_agencies = Column(JSON, nullable=True) 
    
    submissions = relationship("Submission", back_populates="brief")

class Submission(Base):
    __tablename__ = "submissions"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    brief_id = Column(String, ForeignKey("briefs.id"))
    agency_id = Column(String) # Maps to agencyName in Postman examples
    status = Column(String, default="PendingReview") # PendingReview, Approved, Rejected
    plan_file_name = Column(String, nullable=True)
    plan_file_url = Column(String, nullable=True) # GCS link
    submitted_at = Column(DateTime, default=datetime.utcnow)
    
    brief = relationship("Brief", back_populates="submissions")
    history = relationship("HistoryTrail", back_populates="submission")

class HistoryTrail(Base):
    __tablename__ = "history_trail"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    submission_id = Column(Integer, ForeignKey("submissions.id"))
    action = Column(String) # Created, Plan Uploaded, Changes Requested, Approved
    user_id = Column(String)
    user_name = Column(String)
    user_role = Column(String)
    details = Column(Text, nullable=True) # Comments/Reasons
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    submission = relationship("Submission", back_populates="history")
