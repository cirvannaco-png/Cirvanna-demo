"""Persistent user-declared cultural requirement repository."""
from __future__ import annotations
from datetime import datetime,timezone
from typing import Any
from sqlalchemy import Boolean,CheckConstraint,DateTime,ForeignKeyConstraint,Index,Integer,String,UniqueConstraint,create_engine,func,select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase,Mapped,Session,mapped_column
from cultural_identity import CulturalRequirement,RequirementKind,RequirementVerdict,evaluate

class Base(DeclarativeBase): pass
class DeclarationRow(Base):
    __tablename__="cultural_declarations"
    __table_args__=(CheckConstraint("status IN ('active','retracted')",name="ck_cultural_declaration_status"),UniqueConstraint("user_id","correction_event_id",name="uq_cultural_user_correction"),Index("ix_cultural_declarations_user_status","user_id","status"))
    user_id:Mapped[str]=mapped_column(String(128),primary_key=True)
    declaration_id:Mapped[str]=mapped_column(String(128),primary_key=True)
    confirmation_version:Mapped[str]=mapped_column(String(80),nullable=False)
    status:Mapped[str]=mapped_column(String(16),nullable=False,default="active")
    correction_event_id:Mapped[str|None]=mapped_column(String(128),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.current_timestamp())
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.current_timestamp(),onupdate=func.current_timestamp())
class RequirementRow(Base):
    __tablename__="cultural_requirements"
    __table_args__=(CheckConstraint("kind IN ('required_attribute','forbidden_attribute')",name="ck_cultural_requirement_kind"),ForeignKeyConstraint(["user_id","declaration_id"],["cultural_declarations.user_id","cultural_declarations.declaration_id"],ondelete="CASCADE"),Index("ix_cultural_requirements_declaration","user_id","declaration_id"))
    user_id:Mapped[str]=mapped_column(String(128),primary_key=True)
    requirement_id:Mapped[str]=mapped_column(String(128),primary_key=True)
    declaration_id:Mapped[str]=mapped_column(String(128),nullable=False)
    attribute:Mapped[str]=mapped_column(String(160),nullable=False)
    kind:Mapped[str]=mapped_column(String(32),nullable=False)
    hard:Mapped[bool]=mapped_column(Boolean,nullable=False,default=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.current_timestamp())
class CorrectionRow(Base):
    __tablename__="cultural_correction_events"
    __table_args__=(UniqueConstraint("user_id","correction_event_id",name="uq_cultural_correction_event"),ForeignKeyConstraint(["user_id","declaration_id"],["cultural_declarations.user_id","cultural_declarations.declaration_id"],ondelete="CASCADE"))
    event_id:Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    user_id:Mapped[str]=mapped_column(String(128),nullable=False)
    declaration_id:Mapped[str]=mapped_column(String(128),nullable=False)
    correction_event_id:Mapped[str]=mapped_column(String(128),nullable=False)
    occurred_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,server_default=func.current_timestamp())

class DeclarationNotFound(Exception): pass
class DeclarationConflict(Exception): pass

def _domain(row:RequirementRow)->CulturalRequirement:
    return CulturalRequirement(requirement_id=row.requirement_id,declaration_id=row.declaration_id,user_id=row.user_id,attribute=row.attribute,kind=RequirementKind(row.kind),hard=row.hard,active=True)

class CulturalIdentityStore:
    def __init__(self,engine:Engine): self.engine=engine
    def create(self,*,user_id:str,declaration_id:str,confirmation_version:str,requirements:tuple[CulturalRequirement,...])->tuple[CulturalRequirement,...]:
        try:
            with Session(self.engine) as s,s.begin():
                s.add(DeclarationRow(user_id=user_id,declaration_id=declaration_id,confirmation_version=confirmation_version,status="active"))
                for item in requirements:
                    if item.user_id!=user_id or item.declaration_id!=declaration_id: raise ValueError("requirements must belong to this confirmed declaration")
                    s.add(RequirementRow(user_id=user_id,requirement_id=item.requirement_id,declaration_id=declaration_id,attribute=item.attribute,kind=item.kind.value,hard=item.hard))
                s.flush()
        except IntegrityError as exc: raise DeclarationConflict("declaration or requirement ID already exists") from exc
        return requirements
    def list_active(self,user_id:str)->tuple[CulturalRequirement,...]:
        with Session(self.engine) as s:
            rows=s.scalars(select(RequirementRow).join(DeclarationRow,(RequirementRow.user_id==DeclarationRow.user_id)&(RequirementRow.declaration_id==DeclarationRow.declaration_id)).where(RequirementRow.user_id==user_id,DeclarationRow.status=="active").order_by(RequirementRow.declaration_id,RequirementRow.requirement_id)).all()
            return tuple(_domain(row) for row in rows)
    def list_declarations(self,user_id:str)->list[dict[str,Any]]:
        with Session(self.engine) as s:
            rows=s.scalars(select(DeclarationRow).where(DeclarationRow.user_id==user_id).order_by(DeclarationRow.created_at,DeclarationRow.declaration_id)).all()
            output=[]
            for row in rows:
                reqs=s.scalars(select(RequirementRow).where(RequirementRow.user_id==user_id,RequirementRow.declaration_id==row.declaration_id).order_by(RequirementRow.requirement_id)).all()
                output.append({"declaration_id":row.declaration_id,"user_id":row.user_id,"confirmation_version":row.confirmation_version,"status":row.status,"correction_event_id":row.correction_event_id,"requirements":[{"requirement_id":r.requirement_id,"declaration_id":r.declaration_id,"user_id":r.user_id,"attribute":r.attribute,"kind":r.kind,"hard":r.hard,"active":row.status=="active"} for r in reqs]})
            return output
    def retract(self,*,user_id:str,declaration_id:str,correction_event_id:str)->dict[str,Any]:
        try:
            with Session(self.engine) as s,s.begin():
                row=s.scalar(select(DeclarationRow).where(DeclarationRow.user_id==user_id,DeclarationRow.declaration_id==declaration_id).with_for_update())
                if row is None: raise DeclarationNotFound("declaration not found for this user")
                if row.status=="retracted":
                    if row.correction_event_id==correction_event_id: return {"declaration_id":declaration_id,"user_id":user_id,"status":"retracted","correction_event_id":correction_event_id,"idempotent":True}
                    raise DeclarationConflict("declaration was already retracted by another correction")
                duplicate=s.scalar(select(CorrectionRow).where(CorrectionRow.user_id==user_id,CorrectionRow.correction_event_id==correction_event_id))
                if duplicate is not None:
                    raise DeclarationConflict("correction event ID was already used")
                s.add(CorrectionRow(user_id=user_id,declaration_id=declaration_id,correction_event_id=correction_event_id))
                row.status="retracted";row.correction_event_id=correction_event_id;row.updated_at=datetime.now(timezone.utc);s.flush()
                return {"declaration_id":declaration_id,"user_id":user_id,"status":"retracted","correction_event_id":correction_event_id,"idempotent":False}
        except IntegrityError as exc: raise DeclarationConflict("correction event ID conflict") from exc
    def evaluate(self,*,user_id:str,candidate_id:str,attributes:tuple[str,...],complete:bool):
        requirements=self.list_active(user_id)
        return evaluate(user_id,candidate_id,attributes,requirements,candidate_attributes_complete=complete),requirements

def engine_for_url(url:str)->Engine:
    if not url.startswith(("postgresql+psycopg://","sqlite:///")): raise ValueError("CULTURAL_IDENTITY_DATABASE_URL must use postgresql+psycopg://; SQLite is test-only")
    kwargs:dict[str,Any]={"pool_pre_ping":True}
    if url.startswith("sqlite:///"):kwargs["connect_args"]={"check_same_thread":False}
    return create_engine(url,**kwargs)
