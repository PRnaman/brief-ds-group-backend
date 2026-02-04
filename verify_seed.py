from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
import os
from dotenv import load_dotenv
import sys

# Add the project root to sys.path
sys.path.append(os.getcwd())

from app.db import models
from app.db.session import SessionLocal

def verify_seed():
    db = SessionLocal()
    try:
        print("Checking Database Records:")
        
        print("\n--- Clients ---")
        clients = db.query(models.Client).all()
        for c in clients:
            print(f"ID: {c.id}, Name: {c.name}")

        print("\n--- Agencies ---")
        agencies = db.query(models.Agency).all()
        for a in agencies:
            print(f"ID: {a.id}, Name: {a.name}")

        print("\n--- Users ---")
        users = db.query(models.User).all()
        for u in users:
            print(f"ID: {u.id}, Email: {u.email}, Role: {u.role}, Client: {u.client_id}, Agency: {u.agency_id}")

    finally:
        db.close()

if __name__ == "__main__":
    verify_seed()
