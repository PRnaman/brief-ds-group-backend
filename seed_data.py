import sys
import os
from sqlalchemy.orm import Session

# Add the project root to sys.path to allow imports from 'app'
sys.path.append(os.getcwd())

from app.db.session import SessionLocal, engine
from app.db import models
from app.core.security import get_password_hash

def seed_data():
    db: Session = SessionLocal()
    try:
        print("Starting seeding process...")

        # 1. Create Client: DS Group
        ds_group = db.query(models.Client).filter(models.Client.name == "DS Group").first()
        if not ds_group:
            ds_group = models.Client(name="DS Group")
            db.add(ds_group)
            db.commit()
            db.refresh(ds_group)
            print(f"Created Client: {ds_group.name}")
        else:
            print(f"Client already exists: {ds_group.name}")

        # 2. Create Agencies: Pivot Roots, Havas
        agencies_data = ["Pivot Roots", "Havas"]
        agencies = {}
        for agency_name in agencies_data:
            agency = db.query(models.Agency).filter(models.Agency.name == agency_name).first()
            if not agency:
                agency = models.Agency(name=agency_name)
                db.add(agency)
                db.commit()
                db.refresh(agency)
                print(f"Created Agency: {agency.name}")
            else:
                print(f"Agency already exists: {agency.name}")
            agencies[agency_name] = agency

        # 3. Create Users
        users_data = [
            {
                "email": "admin@dsgroup.com",
                "name": "DS Group Admin",
                "password": "Password123",
                "role": "DS_GROUP",
                "client_id": ds_group.id,
                "agency_id": None
            },
            {
                "email": "user@pivotroots.com",
                "name": "Pivot Roots User",
                "password": "Password123",
                "role": "AGENCY",
                "client_id": None,
                "agency_id": agencies["Pivot Roots"].id
            },
            {
                "email": "user@havas.com",
                "name": "Havas User",
                "password": "Password123",
                "role": "AGENCY",
                "client_id": None,
                "agency_id": agencies["Havas"].id
            }
        ]

        for u_data in users_data:
            user = db.query(models.User).filter(models.User.email == u_data["email"]).first()
            if not user:
                user = models.User(
                    email=u_data["email"],
                    name=u_data["name"],
                    password=u_data["password"],
                    role=u_data["role"],
                    client_id=u_data["client_id"],
                    agency_id=u_data["agency_id"]
                )
                db.add(user)
                db.commit()
                print(f"Created User: {user.email} ({user.role})")
            else:
                print(f"User already exists: {user.email}")

        print("Seeding completed successfully!")

    except Exception as e:
        print(f"Error during seeding: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_data()
