"""Persistent explicit-declaration service for cultural identity policy."""
from __future__ import annotations
import hashlib,hmac,os,sys
from pathlib import Path
from typing import Annotated,Literal
from fastapi import Depends,FastAPI,HTTPException,Query
from fastapi.security import HTTPAuthorizationCredentials,HTTPBearer
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import inspect,text

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"packages"/"identity-intelligence"))
from cultural_identity import (CulturalRequirement,RequirementKind,canonical_cultural_evidence_payload,requirement_payload)
from app.store import Base,CulturalIdentityStore,DeclarationConflict,DeclarationNotFound,engine_for_url

SERVICE="cirvanna-cultural-identity-service"
bearer=HTTPBearer(auto_error=False)
app=FastAPI(title="Cirvanna Cultural Identity Service",version="0.1.0",description="Explicit user-declaration lifecycle and signed candidate-bound cultural policy evidence.")

class StrictModel(BaseModel):
    model_config=ConfigDict(extra="forbid")
class RequirementIn(StrictModel):
    requirement_id:str=Field(min_length=1,max_length=128)
    attribute:str=Field(min_length=1,max_length=160)
    kind:Literal["required_attribute","forbidden_attribute"]
    hard:bool=True
class DeclarationCreate(StrictModel):
    user_id:str=Field(min_length=1,max_length=128)
    declaration_id:str=Field(min_length=1,max_length=128)
    confirmation_version:str=Field(min_length=1,max_length=80)
    user_confirmation:bool
    requirements:list[RequirementIn]=Field(min_length=1,max_length=60)
class Retraction(StrictModel):
    user_id:str=Field(min_length=1,max_length=128)
    correction_event_id:str=Field(min_length=1,max_length=128)
    user_confirmation:bool
class EvaluationRequest(StrictModel):
    request_id:str=Field(min_length=1,max_length=128)
    user_id:str=Field(min_length=1,max_length=128)
    candidate_id:str=Field(min_length=1,max_length=128)
    candidate_attributes:list[str]=Field(max_length=250)
    candidate_attributes_complete:bool

def require_internal_token(credentials:Annotated[HTTPAuthorizationCredentials|None,Depends(bearer)])->None:
    expected=os.getenv("CULTURAL_IDENTITY_SERVICE_TOKEN","")
    if len(expected.encode("utf-8"))<32:
        raise HTTPException(503,detail={"code":"CULTURAL_IDENTITY_TOKEN_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials,expected):
        raise HTTPException(401,detail="Valid internal bearer authentication is required.",headers={"WWW-Authenticate":"Bearer"})

def _engine():
    url=os.getenv("CULTURAL_IDENTITY_DATABASE_URL","").strip()
    if not url:raise HTTPException(503,detail={"code":"CULTURAL_IDENTITY_DATABASE_NOT_CONFIGURED"})
    if url.startswith("sqlite:///") and os.getenv("CULTURAL_IDENTITY_ALLOW_SQLITE_TESTS")!="1":
        raise HTTPException(503,detail={"code":"CULTURAL_IDENTITY_SQLITE_TEST_MODE_REQUIRED"})
    try:return engine_for_url(url)
    except ValueError as exc:raise HTTPException(503,detail={"code":"CULTURAL_IDENTITY_DATABASE_CONFIGURATION_INVALID"}) from exc

def _store()->CulturalIdentityStore:return CulturalIdentityStore(_engine())

def _requirements_json(values:tuple[CulturalRequirement,...])->list[dict[str,object]]:
    return [requirement_payload(value) for value in values]

def _domain_error(exc:Exception):
    if isinstance(exc,DeclarationNotFound):raise HTTPException(404,detail={"code":"CULTURAL_DECLARATION_NOT_FOUND"}) from exc
    if isinstance(exc,DeclarationConflict):raise HTTPException(409,detail={"code":"CULTURAL_DECLARATION_CONFLICT"}) from exc
    if isinstance(exc,ValueError):raise HTTPException(422,detail={"code":"INVALID_CULTURAL_DECLARATION"}) from exc
    raise exc

@app.get("/health",tags=["operations"])
def health()->dict[str,str]:return {"status":"alive","service":SERVICE}

@app.get("/ready",tags=["operations"])
def readiness()->dict[str,object]:
    token_ready=len(os.getenv("CULTURAL_IDENTITY_SERVICE_TOKEN","").encode())>=32
    signing_ready=len(os.getenv("CULTURAL_IDENTITY_HMAC_SECRET","").encode())>=32
    db_ready=False;schema_ready=False;db_error=None
    try:
        url=os.getenv("CULTURAL_IDENTITY_DATABASE_URL","").strip()
        if url.startswith("sqlite:///") and os.getenv("CULTURAL_IDENTITY_ALLOW_SQLITE_TESTS")!="1":
            raise ValueError("SQLite is test-only")
        engine=engine_for_url(url)
        with engine.connect() as conn:conn.execute(text("SELECT 1"))
        tables=set(inspect(engine).get_table_names())
        schema_ready={"cultural_declarations","cultural_requirements","cultural_correction_events"}.issubset(tables)
        db_ready=schema_ready
    except Exception as exc:db_error=type(exc).__name__
    ready=token_ready and signing_ready and db_ready
    data={"status":"ready" if ready else "not_ready","service":SERVICE,"api_authentication_configured":token_ready,"evidence_signing_configured":signing_ready,"database_connected":db_ready,"schema_ready":schema_ready,"database_error":db_error,"ready":ready}
    if not ready:raise HTTPException(503,detail=data)
    return data

@app.post("/v1/declarations",status_code=201,dependencies=[Depends(require_internal_token)],tags=["declarations"])
def create_declaration(payload:DeclarationCreate)->dict[str,object]:
    if not payload.user_confirmation:
        raise HTTPException(400,detail={"code":"EXPLICIT_DECLARATION_CONFIRMATION_REQUIRED"})
    if len({item.requirement_id for item in payload.requirements})!=len(payload.requirements):
        raise HTTPException(422,detail={"code":"DUPLICATE_CULTURAL_REQUIREMENT_ID"})
    user_id=payload.user_id.strip();declaration_id=payload.declaration_id.strip()
    requirements=tuple(CulturalRequirement(
        requirement_id=item.requirement_id.strip(),declaration_id=declaration_id,user_id=user_id,
        attribute=item.attribute.strip(),kind=RequirementKind(item.kind),hard=item.hard,active=True,
    ) for item in payload.requirements)
    try:
        values=_store().create(user_id=user_id,declaration_id=declaration_id,confirmation_version=payload.confirmation_version.strip(),requirements=requirements)
        return {"declaration_id":declaration_id,"user_id":user_id,"status":"active","confirmation_version":payload.confirmation_version,"requirements":_requirements_json(values)}
    except (ValueError,DeclarationConflict,DeclarationNotFound) as exc:_domain_error(exc)

@app.get("/v1/declarations",dependencies=[Depends(require_internal_token)],tags=["declarations"])
def list_declarations(user_id:Annotated[str,Query(min_length=1,max_length=128)])->dict[str,object]:
    try:return {"user_id":user_id.strip(),"declarations":_store().list_declarations(user_id.strip())}
    except HTTPException:raise
    except Exception as exc:raise HTTPException(503,detail={"code":"CULTURAL_DECLARATION_STORE_UNAVAILABLE"}) from exc

@app.post("/v1/declarations/{declaration_id}/retract",dependencies=[Depends(require_internal_token)],tags=["declarations"])
def retract_declaration(declaration_id:str,payload:Retraction)->dict[str,object]:
    if not payload.user_confirmation:
        raise HTTPException(400,detail={"code":"EXPLICIT_RETRACTION_CONFIRMATION_REQUIRED"})
    try:return _store().retract(user_id=payload.user_id.strip(),declaration_id=declaration_id,correction_event_id=payload.correction_event_id.strip())
    except (ValueError,DeclarationConflict,DeclarationNotFound) as exc:_domain_error(exc)
    except HTTPException:raise
    except Exception as exc:raise HTTPException(503,detail={"code":"CULTURAL_DECLARATION_STORE_UNAVAILABLE"}) from exc

@app.post("/v1/evaluate",dependencies=[Depends(require_internal_token)],tags=["evaluation"])
def evaluate_candidate(payload:EvaluationRequest)->dict[str,object]:
    secret=os.getenv("CULTURAL_IDENTITY_HMAC_SECRET","")
    if len(secret.encode("utf-8"))<32:raise HTTPException(503,detail={"code":"CULTURAL_EVIDENCE_SIGNING_NOT_CONFIGURED"})
    try:
        store=_store()
        result,requirements=store.evaluate(user_id=payload.user_id.strip(),candidate_id=payload.candidate_id.strip(),attributes=tuple(payload.candidate_attributes),complete=payload.candidate_attributes_complete)
        canonical=canonical_cultural_evidence_payload(payload.request_id,payload.user_id,payload.candidate_id,payload.candidate_attributes,payload.candidate_attributes_complete,requirements)
        signature=hmac.new(secret.encode("utf-8"),canonical,hashlib.sha256).hexdigest()
        return {
            "request_id":payload.request_id,"user_id":payload.user_id,"candidate_id":payload.candidate_id,
            "contract_version":result.contract_version,"verdict":result.verdict.value,
            "reason_codes":list(result.reason_codes),"hard_conflict_ids":list(result.hard_conflict_ids),
            "soft_conflict_ids":list(result.soft_conflict_ids),"cultural_requirements":_requirements_json(requirements),
            "cultural_evidence_signature":signature,
        }
    except ValueError as exc:raise HTTPException(422,detail={"code":"INVALID_CULTURAL_EVIDENCE"}) from exc
    except HTTPException:raise
    except Exception as exc:raise HTTPException(503,detail={"code":"CULTURAL_DECLARATION_STORE_UNAVAILABLE"}) from exc
