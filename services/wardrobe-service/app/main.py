"""Authenticated Wardrobe API; user scope must be bound by trusted internal ingress."""
from __future__ import annotations
import hmac, os, sys
from pathlib import Path
from typing import Annotated, Literal
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import inspect, text

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"packages"))
from wardrobe import WardrobeItem, WardrobeItemStatus
from app.store import Base, WardrobeConflict, WardrobeNotFound, WardrobeStore, engine_for_url

SERVICE="cirvanna-wardrobe-service"
bearer=HTTPBearer(auto_error=False)
app=FastAPI(title="Cirvanna Wardrobe API",version="0.1.0",description="User-scoped wardrobe record and lifecycle service.")

class StrictModel(BaseModel):
    model_config=ConfigDict(extra="forbid")

class CreateItem(StrictModel):
    owner_user_id:str=Field(min_length=1,max_length=128)
    item_id:str=Field(min_length=3,max_length=128)
    display_name:str=Field(min_length=1,max_length=200)
    category:str=Field(min_length=1,max_length=80)
    attributes:list[str]=Field(default_factory=list,max_length=100)
    catalog_product_id:str|None=Field(default=None,max_length=128)
    image_asset_id:str|None=Field(default=None,max_length=160)
    image_storage_consent:bool=False

class TransitionItem(StrictModel):
    owner_user_id:str=Field(min_length=1,max_length=128)
    expected_version:int=Field(ge=1)
    target_status:Literal["active","archived","deleted"]
    command_id:str=Field(min_length=3,max_length=128)

def require_internal_token(credentials:Annotated[HTTPAuthorizationCredentials|None,Depends(bearer)])->None:
    expected=os.getenv("WARDROBE_SERVICE_TOKEN","")
    if len(expected.encode())<32:
        raise HTTPException(503,detail={"code":"WARDROBE_SERVICE_TOKEN_NOT_CONFIGURED"})
    if credentials is None or not hmac.compare_digest(credentials.credentials,expected):
        raise HTTPException(401,detail="Valid internal bearer authentication is required.",headers={"WWW-Authenticate":"Bearer"})

def store()->WardrobeStore:
    url=os.getenv("WARDROBE_DATABASE_URL","").strip()
    if not url: raise HTTPException(503,detail={"code":"WARDROBE_DATABASE_NOT_CONFIGURED"})
    if url.startswith("sqlite:///") and os.getenv("WARDROBE_ALLOW_SQLITE_TESTS")!="1":
        raise HTTPException(503,detail={"code":"WARDROBE_SQLITE_TEST_MODE_REQUIRED"})
    try: return WardrobeStore(engine_for_url(url))
    except ValueError as exc: raise HTTPException(503,detail={"code":"WARDROBE_DATABASE_CONFIGURATION_INVALID"}) from exc

def model_json(item:WardrobeItem)->dict[str,object]:
    return {"item_id":item.item_id,"owner_user_id":item.owner_user_id,"display_name":item.display_name,"category":item.category,"attributes":list(item.attributes),"catalog_product_id":item.catalog_product_id,"image_asset_id":item.image_asset_id,"image_storage_consent":item.image_storage_consent,"status":item.status.value,"version":item.version,"last_command_id":item.last_command_id}

def domain_error(exc:Exception):
    if isinstance(exc,WardrobeNotFound): raise HTTPException(404,detail={"code":"WARDROBE_ITEM_NOT_FOUND"}) from exc
    if isinstance(exc,WardrobeConflict): raise HTTPException(409,detail={"code":"WARDROBE_CONFLICT","detail":str(exc)}) from exc
    if isinstance(exc,PermissionError): raise HTTPException(403,detail={"code":"WARDROBE_FORBIDDEN"}) from exc
    if isinstance(exc,ValueError): raise HTTPException(422,detail={"code":"INVALID_WARDROBE_COMMAND","detail":str(exc)}) from exc
    raise exc

@app.get("/health",tags=["operations"])
def health()->dict[str,str]: return {"status":"alive","service":SERVICE}

@app.get("/ready",tags=["operations"])
def ready()->dict[str,object]:
    token_ready=len(os.getenv("WARDROBE_SERVICE_TOKEN","").encode())>=32
    url=os.getenv("WARDROBE_DATABASE_URL","").strip()
    db_ready=False;schema_ready=False;db_error=None
    try:
        if url.startswith("sqlite:///") and os.getenv("WARDROBE_ALLOW_SQLITE_TESTS")!="1":
            raise ValueError("SQLite test configuration is not allowed for service readiness")
        engine=engine_for_url(url)
        with engine.connect() as conn: conn.execute(text("SELECT 1"))
        tables=set(inspect(engine).get_table_names())
        schema_ready={"wardrobe_items","wardrobe_asset_deletion_outbox"}.issubset(tables)
        db_ready=schema_ready
    except Exception as exc: db_error=type(exc).__name__
    deletion_worker_ready=os.getenv("WARDROBE_ASSET_DELETION_READY","").lower()=="true"
    ready=token_ready and db_ready and deletion_worker_ready
    data={"status":"ready" if ready else "not_ready","service":SERVICE,"api_authentication_configured":token_ready,"database_connected":db_ready,"schema_ready":schema_ready,"asset_deletion_worker_configured":deletion_worker_ready,"database_error":db_error,"ready":ready}
    if not ready: raise HTTPException(503,detail=data)
    return data

@app.get("/v1/items",dependencies=[Depends(require_internal_token)],tags=["wardrobe"])
def list_items(owner_user_id:Annotated[str,Query(min_length=1,max_length=128)], include_archived:bool=True)->dict[str,object]:
    try:
        items=store().list(owner_user_id.strip(),include_archived=include_archived)
        return {"owner_user_id":owner_user_id.strip(),"items":[model_json(item) for item in items]}
    except HTTPException: raise
    except Exception as exc: raise HTTPException(503,detail={"code":"WARDROBE_STORE_UNAVAILABLE"}) from exc

@app.get("/v1/items/{item_id}",dependencies=[Depends(require_internal_token)],tags=["wardrobe"])
def get_item(item_id:str,owner_user_id:Annotated[str,Query(min_length=1,max_length=128)])->dict[str,object]:
    try: return {"item":model_json(store().get(owner_user_id.strip(),item_id))}
    except (WardrobeNotFound,WardrobeConflict,PermissionError,ValueError) as exc: domain_error(exc)
    except HTTPException: raise
    except Exception as exc: raise HTTPException(503,detail={"code":"WARDROBE_STORE_UNAVAILABLE"}) from exc

@app.post("/v1/items",status_code=201,dependencies=[Depends(require_internal_token)],tags=["wardrobe"])
def create_item(payload:CreateItem)->dict[str,object]:
    try:
        item=WardrobeItem(item_id=payload.item_id.strip(),owner_user_id=payload.owner_user_id.strip(),display_name=payload.display_name.strip(),category=payload.category.strip(),attributes=tuple(payload.attributes),catalog_product_id=payload.catalog_product_id,image_asset_id=payload.image_asset_id,image_storage_consent=payload.image_storage_consent)
        return {"item":model_json(store().create(item))}
    except (WardrobeConflict,PermissionError,ValueError) as exc: domain_error(exc)
    except HTTPException: raise
    except Exception as exc: raise HTTPException(503,detail={"code":"WARDROBE_STORE_UNAVAILABLE"}) from exc

@app.post("/v1/items/{item_id}/transition",dependencies=[Depends(require_internal_token)],tags=["wardrobe"])
def transition(item_id:str,payload:TransitionItem)->dict[str,object]:
    try:
        updated=store().transition(owner_user_id=payload.owner_user_id.strip(),item_id=item_id,expected_version=payload.expected_version,target_status=WardrobeItemStatus(payload.target_status),command_id=payload.command_id.strip())
        return {"item":model_json(updated),"asset_deletion_queued":updated.status is WardrobeItemStatus.DELETED and updated.image_asset_id is not None}
    except (WardrobeNotFound,WardrobeConflict,PermissionError,ValueError) as exc: domain_error(exc)
    except HTTPException: raise
    except Exception as exc: raise HTTPException(503,detail={"code":"WARDROBE_STORE_UNAVAILABLE"}) from exc
