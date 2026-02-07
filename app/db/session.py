from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Database Configuration Logic
# 1. First check if individual components are provided (common for Secret Manager)
db_user = os.getenv("DB_USER")
db_pass = os.getenv("DB_PASS")
db_host = os.getenv("DB_HOST", "34.131.195.115") # Fallback to your IP from .env
db_name = os.getenv("DB_NAME", "mediaflow")
db_port = os.getenv("DB_PORT", "5432")
instance_name = os.getenv("INSTANCE_CONNECTION_NAME") # Found in GCP Cloud SQL Overview

if db_user and db_pass:
    if instance_name:
        # CLOUD RUN (Socket connection) - Best for security/reliability
        # Format: postgresql://user:pass@/dbname?host=/cloudsql/connection_name
        SQLALCHEMY_DATABASE_URL = f"postgresql://{db_user}:{db_pass}@/{db_name}?host=/cloudsql/{instance_name}"
    else:
        # CLOUD RUN / EXTERNAL (Public IP connection with SSL)
        SQLALCHEMY_DATABASE_URL = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}?sslmode=require"
else:
    # 2. Fallback to full DATABASE_URL (Local/Testing or single secret)
    # The user mentioned this specific socket-based full URL:
    # postgresql://postgres:Havas-CSA2026@/mediaflow?host=/cloudsql/mediaflow-485607:asia-south2:mediaflow-db
    SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/brief_ds")

# The 'engine' is the core interface to the database.
# It handles the connection pool and the actual SQL execution.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,  # Check connection liveness before usage
    pool_recycle=1800    # Recycle connections every 30 mins
)

# 'SessionLocal' is a factory for creating database sessions.
# Each request to our API will get its own session.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# This function is a 'dependency'. It ensures each request gets a DB session
# and that the session is closed once the request is finished.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
