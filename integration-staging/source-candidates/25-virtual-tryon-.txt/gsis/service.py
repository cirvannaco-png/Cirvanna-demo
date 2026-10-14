from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from typing import List, Optional, Tuple

from shared.garment import GarmentDescriptor
from .models import Garment
from .exceptions import DatabaseError

class GarmentService:
    """Garment CRUD operations"""

    def __init__(self, db: Session):
        self.db = db

    def create_garment(self, gdo: GarmentDescriptor) -> Garment:
        """Create new garment version"""
        try:
            # Check if exists
            existing = self.db.query(Garment).filter_by(
                garment_id=gdo.garment_id
            ).order_by(desc(Garment.version)).first()

            if existing:
                version = existing.version + 1
            else:
                version = 1

            # Create garment
            garment = Garment(
                garment_id=gdo.garment_id,
                version=version,
                size=gdo.size,
                pattern_dimensions=gdo.pattern_dimensions.dict(),
                stretch_ratio=gdo.stretch_ratio,
                fit_class=gdo.fit_class.value,
                fabric_weight=gdo.fabric_weight.value,
                ease_allowance=gdo.ease_allowance.dict(),
                cad_pattern=gdo.optional_CAD_pattern
            )

            self.db.add(garment)
            self.db.commit()
            self.db.refresh(garment)

            return garment

        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to create garment: {str(e)}")

    def get_garment(self, garment_id: str) -> Optional[Garment]:
        """Get latest version of garment"""
        try:
            return self.db.query(Garment).filter_by(
                garment_id=garment_id
            ).order_by(desc(Garment.version)).first()
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve garment: {str(e)}")

    def get_garment_version(self, garment_id: str, version: int) -> Optional[Garment]:
        """Get specific version of garment"""
        try:
            return self.db.query(Garment).filter_by(
                garment_id=garment_id,
                version=version
            ).first()
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve garment version: {str(e)}")

    def list_garments(self, skip: int = 0, limit: int = 100) -> Tuple[List[Garment], int]:
        """List latest versions of all garments with pagination"""
        try:
            # Subquery to get max version per garment_id
            subquery = self.db.query(
                Garment.garment_id,
                func.max(Garment.version).label('max_version')
            ).group_by(Garment.garment_id).subquery()

            # Join to get full rows
            query = self.db.query(Garment).join(
                subquery,
                (Garment.garment_id == subquery.c.garment_id) &
                (Garment.version == subquery.c.max_version)
            ).order_by(Garment.created_at.desc())

            total = query.count()
            garments = query.offset(skip).limit(limit).all(
