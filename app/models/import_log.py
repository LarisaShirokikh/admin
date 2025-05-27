from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime
from app.core.database import Base

class ImportLog(Base):
    __tablename__ = "import_logs"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    rows = Column(Integer, nullable=False)
    status = Column(String, default="in_progress")  # success / failed / in_progress
    message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)