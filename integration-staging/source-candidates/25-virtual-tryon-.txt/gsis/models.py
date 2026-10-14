from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, UniqueConstraint
from sqlalchemy.sql import func

from .database import Base

class Garment(Base):
    __tablename__ = "garments"

    id = Column(Integer, primary_key=True, index=True)
    garment_id = Column(String, index=True, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    size = Column(String, nullable=False)
    pattern_dimensions = Column(JSON, nullable=False)
    stretch_ratio = Column(Float, nullable=False)
    fit_class = Column(String, nullable=False)
    fabric_weight = Column(String, nullable=False)
    ease_allowance = Column(JSON, nullable=False)
    cad_pattern = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('garment_id', 'version', name='uix_garment_version'),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "garment_id": self.garment_id,
            "version": self.version,
            "size": self.size,
            "pattern_dimensions": self.pattern_dimensions,
            "stretch_ratio": self.stretch_ratio,
            "fit_class": self.fit_class,
            "fabric_weight": self.fabric_weight,
            "ease_allowance": self.ease_allowance,
            "cad_pattern": self.cad_pattern,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
