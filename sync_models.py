from app.db.models import Base
from app.db.session import engine

print("Creating tables defined in models.py...")
Base.metadata.create_all(bind=engine)
print("Finished creating tables.")
