from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# This is the database URL. In production, this would be an environment variable.
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/brief_ds")

# The 'engine' is the core interface to the database.
# It handles the connection pool and the actual SQL execution.
engine = create_engine(SQLALCHEMY_DATABASE_URL)

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
