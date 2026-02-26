import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy import Column, String, Text, DateTime, Integer
from database import Base


class HTMLPage(Base):
    __tablename__ = "html_pages"

    id = Column(String(16), primary_key=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=True)  # NULL = indefinite
    content_size = Column(Integer, nullable=False)

    @staticmethod
    def generate_id() -> str:
        return secrets.token_urlsafe(12)

    @staticmethod
    def calculate_expiration(days: int | None) -> datetime | None:
        if days is None or days <= 0:
            return None  # Indefinite
        return datetime.now(timezone.utc) + timedelta(days=days)

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def time_remaining(self) -> str:
        if self.expires_at is None:
            return "Never expires"
        delta = self.expires_at - datetime.now(timezone.utc)
        if delta.total_seconds() <= 0:
            return "Expired"
        days = delta.days
        hours = delta.seconds // 3600
        if days > 0:
            return f"{days} day(s), {hours} hour(s)"
        return f"{hours} hour(s)"
