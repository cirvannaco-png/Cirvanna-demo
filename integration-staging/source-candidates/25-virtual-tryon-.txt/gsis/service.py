from typing import List, Optional, Tuple

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from shared.garment import GarmentDescriptor
from .exceptions import DatabaseError
from .models import Garment


class GarmentService:
    """Garment CRUD operations."""

    def __init__(self, db: Session):
        self.db = db

    def create_garment(self, gdo: GarmentDescriptor) -> Garment:
        """Create a new garment version."""
        try:
            existing = (
                self.db.query(Garment)
                .filter_by(garment_id=gdo.garment_id)
                .order_by(desc(Garment.version))
                .first()
            )
            version = existing.version + 1 if existing else 1

            garment = Garment(
                garment_id=gdo.garment_id,
                version=version,
                size=gdo.size,
                pattern_dimensions=gdo.pattern_dimensions.dict(),
                stretch_ratio=gdo.stretch_ratio,
                fit_class=gdo.fit_class.value,
                fabric_weight=gdo.fabric_weight.value,
                ease_allowance=gdo.ease_allowance.dict(),
                cad_pattern=gdo.optional_CAD_pattern,
            )

            self.db.add(garment)
            self.db.commit()
            self.db.refresh(garment)
            return garment
        except Exception as exc:
            self.db.rollback()
            raise DatabaseError(f"Failed to create garment: {exc}") from exc

    def get_garment(self, garment_id: str) -> Optional[Garment]:
        """Get the latest version of a garment."""
        try:
            return (
                self.db.query(Garment)
                .filter_by(garment_id=garment_id)
                .order_by(desc(Garment.version))
                .first()
            )
        except Exception as exc:
            raise DatabaseError(f"Failed to retrieve garment: {exc}") from exc

    def get_garment_version(self, garment_id: str, version: int) -> Optional[Garment]:
        """Get a specific garment version."""
        try:
            return (
                self.db.query(Garment)
                .filter_by(garment_id=garment_id, version=version)
                .first()
            )
        except Exception as exc:
            raise DatabaseError(f"Failed to retrieve garment version: {exc}") from exc

    def list_garments(self, skip: int = 0, limit: int = 100) -> Tuple[List[Garment], int]:
        """List the latest version of each garment with pagination."""
        if skip < 0:
            raise ValueError("skip must be non-negative")
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        try:
            subquery = (
                self.db.query(
                    Garment.garment_id,
                    func.max(Garment.version).label("max_version"),
                )
                .group_by(Garment.garment_id)
                .subquery()
            )
            query = (
                self.db.query(Garment)
                .join(
                    subquery,
                    (Garment.garment_id == subquery.c.garment_id)
                    & (Garment.version == subquery.c.max_version),
                )
                .order_by(Garment.created_at.desc())
            )
            total = query.count()
            garments = query.offset(skip).limit(limit).all()
            return garments, total
        except Exception as exc:
            raise DatabaseError(f"Failed to list garments: {exc}") from exc

    def delete_garment(self, garment_id: str) -> bool:
        """Delete all versions of a garment."""
        try:
            result = self.db.query(Garment).filter_by(garment_id=garment_id).delete()
            self.db.commit()
            return result > 0
        except Exception as exc:
            self.db.rollback()
            raise DatabaseError(f"Failed to delete garment: {exc}") from exc
