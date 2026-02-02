from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON, Date, Integer
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime
import uuid

Base = declarative_base()

def generate_uuid():
    return str(uuid.uuid4())

class Client(Base):
    __tablename__ = "clients"
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, unique=True, index=True)
    briefs = relationship("Brief", back_populates="client")

class Agency(Base):
    __tablename__ = "agencies"
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, unique=True, index=True)
    contact_email = Column(String)
    submissions = relationship("Submission", back_populates="agency")

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, index=True)
    name = Column(String)
    role = Column(String) # DS_GROUP or AGENCY
    client_id = Column(String, ForeignKey("clients.id"), nullable=True)
    agency_id = Column(String, ForeignKey("agencies.id"), nullable=True)

class Brief(Base):
    __tablename__ = "briefs"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    client_id = Column(String, ForeignKey("clients.id"))
    brand_name = Column(String, index=True)
    division = Column(String)
    creative_name = Column(String)
    objective = Column(Text)
    brief_type = Column(String)
    total_budget = Column(String)
    start_date = Column(Date)
    end_date = Column(Date)
    status = Column(String, default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # --- New Production Fields ---
    demographics_age = Column(String, nullable=True)
    demographics_gender = Column(String, nullable=True)
    demographics_nccs = Column(String, nullable=True)
    demographics_etc = Column(String, nullable=True)
    psychographics = Column(Text, nullable=True)
    key_markets = Column(Text, nullable=True)
    p1_markets = Column(Text, nullable=True)
    p2_markets = Column(Text, nullable=True)
    edit_durations = Column(String, nullable=True)
    acd = Column(String, nullable=True)
    dispersion = Column(String, nullable=True)
    advertisement_link = Column(String, nullable=True)
    creative_languages = Column(String, nullable=True)
    scheduling_preference = Column(Text, nullable=True)
    miscellaneous = Column(Text, nullable=True)
    remarks = Column(Text, nullable=True)
    
    # Helper to store names of targeted agencies (for UI preview)
    target_agency_names = Column(JSON, nullable=True) 

    client = relationship("Client", back_populates="briefs")
    submissions = relationship("Submission", back_populates="brief")

class Submission(Base):
    __tablename__ = "submissions"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    brief_id = Column(String, ForeignKey("briefs.id"))
    agency_id = Column(String, ForeignKey("agencies.id"))
    status = Column(String, default="DRAFT") # DRAFT, CLIENT_REVIEW, AGENCY_REVISION, APPROVED
    version_number = Column(Integer, default=1)
    plan_file_name = Column(String, nullable=True)
    plan_file_url = Column(String, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    brief = relationship("Brief", back_populates="submissions")
    agency = relationship("Agency", back_populates="submissions")
    history = relationship("HistoryTrail", back_populates="submission")

class HistoryTrail(Base):
    __tablename__ = "history_trail"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    submission_id = Column(String, ForeignKey("submissions.id"))
    action = Column(String) 
    user_id = Column(String)
    user_name = Column(String)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    submission = relationship("Submission", back_populates="history")
