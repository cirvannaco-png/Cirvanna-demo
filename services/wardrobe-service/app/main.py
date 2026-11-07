"""Authenticated Wardrobe API; user scope must be bound by trusted internal ingress."""
from __future__ import annotations
import hashlib, hmac, json, os, sys, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, inspect, select, text
from sqlalchemy.orm import Session

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"packages"))
from wardrobe import WardrobeItem, WardrobeItemStatus
from app.store import Base, WardrobeConflict, WardrobeNotFound, WardrobeStore, WardrobeDeletionQueue, WardrobeFeedbackEventRow, WardrobeOutfitRow, WardrobeOutfitWearEventRow, WardrobeRow, engine_for_url
from app.learning import LearningIntegrationError, deliver_learning_event

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


class VerifiedPurchaseIn(StrictModel):
    """Trusted Sync-service handoff from a verified Commerce paid-order event."""
    event_id: str = Field(min_length=36, max_length=36)
    event_type: Literal["commerce.order.paid"]
    schema_version: Literal[1]
    ownership_authority: Literal["verified_payment"]
    owner_user_id: str = Field(min_length=1, max_length=128)
    order_id: str = Field(min_length=36, max_length=36)
    order_item_id: str = Field(min_length=36, max_length=36)
    catalog_product_id: str = Field(min_length=1, max_length=128)
    product_name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, le=50)
    currency: str = Field(min_length=3, max_length=3)
    unit_price_minor: int = Field(ge=0)
    paid_at: str = Field(min_length=20, max_length=64)


class FeedbackCreate(StrictModel):
    """Explicit user interaction. The BFF must bind owner_user_id to Commerce /me."""
    owner_user_id: str = Field(min_length=1, max_length=128)
    item_id: str = Field(min_length=3, max_length=128)
    event_id: str = Field(min_length=8, max_length=128)
    signal: Literal["like", "dislike", "avoid", "modify", "wear"]
    consent_receipt_id: str = Field(min_length=8, max_length=128)
    target_type: Literal["item", "attribute"] | None = None
    target_value: str | None = Field(default=None, min_length=1, max_length=180)
    observed_at: str = Field(min_length=20, max_length=64)

class TransitionItem(StrictModel):
    owner_user_id:str=Field(min_length=1,max_length=128)
    expected_version:int=Field(ge=1)
    target_status:Literal["active","archived","deleted"]
    command_id:str=Field(min_length=3,max_length=128)

class EditItem(StrictModel):
    """Version-checked edits to user-owned garment metadata; Catalog facts remain canonical."""
    owner_user_id: str = Field(min_length=1, max_length=128)
    expected_version: int = Field(ge=1)
    command_id: str = Field(min_length=3, max_length=128)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    attributes: list[str] | None = Field(default=None, max_length=100)

class OutfitPieceInput(StrictModel):
    slot_id: str = Field(min_length=3, max_length=128)
    wardrobe_item_id: str = Field(min_length=3, max_length=128)


class CreateOutfit(StrictModel):
    owner_user_id: str = Field(min_length=1, max_length=128)
    outfit_id: str = Field(min_length=3, max_length=128)
    name: str = Field(min_length=1, max_length=160)
    pieces: list[OutfitPieceInput] = Field(min_length=1, max_length=20)


class RecordOutfitWear(StrictModel):
    owner_user_id: str = Field(min_length=1, max_length=128)
    event_id: str = Field(min_length=8, max_length=128)
    expected_outfit_version: int = Field(ge=1)
    consent_receipt_id: str = Field(min_length=8, max_length=128)
    observed_at: str = Field(min_length=20, max_length=64)
    context: dict[str, str] = Field(default_factory=dict, max_length=8)


class AddOutfitPiece(StrictModel):
    owner_user_id: str = Field(min_length=1, max_length=128)
    expected_version: int = Field(ge=1)
    command_id: str = Field(min_length=8, max_length=128)
    slot_id: str = Field(min_length=3, max_length=128)
    wardrobe_item_id: str = Field(min_length=3, max_length=128)


class EditOutfitPiece(StrictModel):
    owner_user_id: str = Field(min_length=1, max_length=128)
    expected_version: int = Field(ge=1)
    command_id: str = Field(min_length=8, max_length=128)
    wardrobe_item_id: str | None = Field(default=None, min_length=3, max_length=128)


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
    return {"item_id":item.item_id,"owner_user_id":item.owner_user_id,"display_name":item.display_name,"category":item.category,"attributes":list(item.attributes),"catalog_product_id":item.catalog_product_id,"commerce_order_id":item.commerce_order_id,"commerce_order_item_id":item.commerce_order_item_id,"purchase_event_id":item.purchase_event_id,"purchase_quantity":item.purchase_quantity,"purchase_currency":item.purchase_currency,"purchase_unit_price_minor":item.purchase_unit_price_minor,"purchase_paid_at":item.purchase_paid_at,"ownership_source":"verified_purchase" if item.commerce_order_item_id else "user_added","image_asset_id":item.image_asset_id,"image_storage_consent":item.image_storage_consent,"status":item.status.value,"version":item.version,"last_command_id":item.last_command_id}

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
        required_tables={"wardrobe_items","wardrobe_asset_deletion_outbox","wardrobe_learning_events","wardrobe_outfits","wardrobe_outfit_wear_events"}
        wardrobe_columns={column["name"] for column in inspect(engine).get_columns("wardrobe_items")} if "wardrobe_items" in tables else set()
        required_purchase_columns={"commerce_order_id","commerce_order_item_id","purchase_event_id","purchase_quantity","purchase_currency","purchase_unit_price_minor","purchase_paid_at"}
        schema_ready=required_tables.issubset(tables) and required_purchase_columns.issubset(wardrobe_columns)
        db_ready=schema_ready
    except Exception as exc: db_error=type(exc).__name__
    worker_enabled=os.getenv("WARDROBE_ASSET_DELETION_READY","").lower()=="true"
    worker_heartbeat_fresh=False
    if db_ready and worker_enabled:
        try:
            worker_heartbeat_fresh=WardrobeDeletionQueue(engine).has_fresh_heartbeat(max_age_seconds=90)
        except Exception:
            worker_heartbeat_fresh=False
    deletion_worker_ready=worker_enabled and worker_heartbeat_fresh
    ready=token_ready and db_ready and deletion_worker_ready
    data={"status":"ready" if ready else "not_ready","service":SERVICE,"api_authentication_configured":token_ready,"database_connected":db_ready,"schema_ready":schema_ready,"asset_deletion_worker_configured":worker_enabled,"asset_deletion_worker_heartbeat_fresh":worker_heartbeat_fresh,"database_error":db_error,"ready":ready}
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


@app.post("/v1/purchases/verified", status_code=201, dependencies=[Depends(require_internal_token)], tags=["purchase ownership"])
def ingest_verified_purchase(payload: VerifiedPurchaseIn) -> dict[str, object]:
    """Idempotently materialize a verified paid line item; caller must be the trusted Sync worker."""
    owner = payload.owner_user_id.strip()
    try:
        paid_at = datetime.fromisoformat(payload.paid_at.replace("Z", "+00:00"))
        if paid_at.tzinfo is None:
            raise ValueError("paid_at requires timezone")
        paid_at = paid_at.astimezone(timezone.utc)
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "INVALID_PURCHASE_TIMESTAMP"}) from exc
    if payload.currency != payload.currency.upper() or not payload.currency.isalpha():
        raise HTTPException(422, detail={"code": "INVALID_PURCHASE_CURRENCY"})
    # Stable item identity per order line. Quantity remains an attribute of this
    # owned line so repeated purchases of the same product remain distinct.
    item_id = "purchase-" + uuid.uuid5(uuid.NAMESPACE_URL, f"cirvanna:wardrobe:{owner}:{payload.order_item_id}").hex
    try:
        with Session(store().engine) as session, session.begin():
            existing = session.scalar(select(WardrobeRow).where(
                WardrobeRow.owner_user_id == owner,
                WardrobeRow.commerce_order_item_id == payload.order_item_id,
            ).with_for_update())
            if existing is not None:
                same = (
                    existing.commerce_order_id == payload.order_id
                    and existing.purchase_event_id == payload.event_id
                    and existing.catalog_product_id == payload.catalog_product_id
                    and existing.purchase_quantity == payload.quantity
                    and existing.purchase_currency == payload.currency
                    and existing.purchase_unit_price_minor == payload.unit_price_minor
                    and existing.purchase_paid_at == paid_at.isoformat()
                    and existing.display_name == payload.product_name.strip()
                )
                if not same:
                    raise HTTPException(409, detail={"code": "PURCHASE_OWNERSHIP_EVENT_CONFLICT"})
                return {"status": "replayed", "item": model_json(WardrobeItem(
                    item_id=existing.item_id, owner_user_id=existing.owner_user_id,
                    display_name=existing.display_name, category=existing.category,
                    attributes=tuple(existing.attributes or ()), catalog_product_id=existing.catalog_product_id,
                    status=WardrobeItemStatus(existing.status), version=existing.version,
                    last_command_id=existing.last_command_id, commerce_order_id=existing.commerce_order_id,
                    commerce_order_item_id=existing.commerce_order_item_id,
                    purchase_event_id=existing.purchase_event_id, purchase_quantity=existing.purchase_quantity,
                    purchase_currency=existing.purchase_currency, purchase_unit_price_minor=existing.purchase_unit_price_minor,
                    purchase_paid_at=existing.purchase_paid_at,
                ))}
            row = WardrobeRow(
                owner_user_id=owner, item_id=item_id, display_name=payload.product_name.strip(),
                category="other", attributes=["purchase_category_review_required"],
                catalog_product_id=payload.catalog_product_id.strip(),
                commerce_order_id=payload.order_id, commerce_order_item_id=payload.order_item_id,
                purchase_event_id=payload.event_id, purchase_quantity=payload.quantity,
                purchase_currency=payload.currency, purchase_unit_price_minor=payload.unit_price_minor,
                purchase_paid_at=paid_at.isoformat(),
                image_asset_id=None, image_storage_consent=False, status="active", version=1,
            )
            session.add(row)
            session.flush()
            return {"status": "created", "item": model_json(WardrobeItem(
                item_id=row.item_id, owner_user_id=row.owner_user_id, display_name=row.display_name,
                category=row.category, attributes=tuple(row.attributes), catalog_product_id=row.catalog_product_id,
                status=WardrobeItemStatus(row.status), version=row.version, commerce_order_id=row.commerce_order_id,
                commerce_order_item_id=row.commerce_order_item_id, purchase_event_id=row.purchase_event_id,
                purchase_quantity=row.purchase_quantity, purchase_currency=row.purchase_currency,
                purchase_unit_price_minor=row.purchase_unit_price_minor, purchase_paid_at=row.purchase_paid_at,
            ))}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "PURCHASE_OWNERSHIP_STORE_UNAVAILABLE"}) from exc


@app.post("/v1/feedback", status_code=201, dependencies=[Depends(require_internal_token)], tags=["wardrobe intelligence"])
def record_feedback(payload: FeedbackCreate) -> dict[str, object]:
    """Commit an explicit wardrobe signal through the consented USI/TAL and NPL contracts."""
    owner = payload.owner_user_id.strip()
    try:
        wardrobe = store()
        item = wardrobe.get(owner, payload.item_id.strip())
        if item.status is not WardrobeItemStatus.ACTIVE:
            raise HTTPException(409, detail={"code": "WARDROBE_ITEM_NOT_ACTIVE"})

        target_type = payload.target_type
        target_value = payload.target_value.strip() if payload.target_value else None
        if payload.signal in {"dislike", "avoid"}:
            if target_type is None:
                target_type, target_value = "item", item.item_id
            if target_type == "item":
                if target_value not in {None, item.item_id}:
                    raise HTTPException(422, detail={"code": "FEEDBACK_TARGET_NOT_IN_WARDROBE_ITEM"})
                target_value = item.item_id
            else:
                allowed = {value.strip().casefold() for value in item.attributes}
                allowed.add(item.category.strip().casefold())
                if target_value is None or target_value.casefold() not in allowed:
                    raise HTTPException(422, detail={"code": "FEEDBACK_ATTRIBUTE_NOT_PRESENT_ON_ITEM"})
        elif target_type is not None or target_value is not None:
            raise HTTPException(422, detail={"code": "TARGET_ONLY_VALID_FOR_NEGATIVE_FEEDBACK"})

        try:
            observed = datetime.fromisoformat(payload.observed_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "INVALID_FEEDBACK_TIMESTAMP"}) from exc
        if observed.tzinfo is None:
            raise HTTPException(422, detail={"code": "FEEDBACK_TIMESTAMP_REQUIRES_TIMEZONE"})
        observed = observed.astimezone(timezone.utc)

        document = {
            "owner_user_id": owner,
            "item_id": item.item_id,
            "item_version": item.version,
            "event_id": payload.event_id.strip(),
            "signal": payload.signal,
            "target_type": target_type,
            "target_value": target_value,
            "consent_receipt_id": payload.consent_receipt_id.strip(),
            "observed_at": observed.isoformat(),
        }
        digest = hashlib.sha256(json.dumps(
            document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")).hexdigest()

        with Session(wardrobe.engine) as session:
            existing = session.get(WardrobeFeedbackEventRow, (owner, payload.event_id.strip()))
            if existing is not None:
                if existing.payload_hash != digest:
                    raise HTTPException(409, detail={"code": "WARDROBE_FEEDBACK_EVENT_CONFLICT"})
                if existing.delivery_state == "delivered":
                    return {
                        "status": "replayed",
                        "event_id": existing.event_id,
                        "delivery_state": "delivered",
                        "learning": existing.delivery_result,
                    }

        learning_result = deliver_learning_event(
            owner_user_id=owner,
            item_id=item.item_id,
            item_version=item.version,
            display_name=item.display_name,
            category=item.category,
            attributes=list(item.attributes),
            event_id=payload.event_id.strip(),
            signal=payload.signal,
            target_type=target_type,
            target_value=target_value,
            consent_receipt_id=payload.consent_receipt_id.strip(),
            observed_at=observed,
        )

        with Session(wardrobe.engine) as session, session.begin():
            existing = session.get(WardrobeFeedbackEventRow, (owner, payload.event_id.strip()))
            if existing is None:
                session.add(WardrobeFeedbackEventRow(
                    owner_user_id=owner,
                    event_id=payload.event_id.strip(),
                    item_id=item.item_id,
                    item_version=item.version,
                    signal=payload.signal,
                    target_type=target_type,
                    target_value=target_value,
                    consent_receipt_id=payload.consent_receipt_id.strip(),
                    payload_hash=digest,
                    delivery_state="delivered",
                    delivery_result=learning_result,
                    error_code=None,
                    observed_at=observed,
                ))
            elif existing.payload_hash != digest:
                raise HTTPException(409, detail={"code": "WARDROBE_FEEDBACK_EVENT_CONFLICT"})
            else:
                existing.delivery_state = "delivered"
                existing.delivery_result = learning_result
                existing.error_code = None

        return {
            "status": "recorded",
            "event_id": payload.event_id,
            "delivery_state": "delivered",
            "learning": learning_result,
        }
    except HTTPException:
        raise
    except (WardrobeNotFound, WardrobeConflict, PermissionError, ValueError) as exc:
        domain_error(exc)
    except LearningIntegrationError as exc:
        raise HTTPException(exc.status_code, detail={"code": exc.code}) from exc
    except Exception as exc:
        raise HTTPException(503, detail={"code": "WARDROBE_LEARNING_UNAVAILABLE"}) from exc


@app.get("/v1/feedback", dependencies=[Depends(require_internal_token)], tags=["wardrobe intelligence"])
def list_feedback(
    owner_user_id: Annotated[str, Query(min_length=1, max_length=128)],
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, object]:
    """Return an owner's own feedback audit trail only."""
    try:
        with Session(store().engine) as session:
            rows = session.query(WardrobeFeedbackEventRow).filter(
                WardrobeFeedbackEventRow.owner_user_id == owner_user_id.strip()
            ).order_by(WardrobeFeedbackEventRow.observed_at.desc()).limit(limit).all()
            return {
                "owner_user_id": owner_user_id.strip(),
                "items": [{
                    "event_id": row.event_id,
                    "item_id": row.item_id,
                    "item_version": row.item_version,
                    "signal": row.signal,
                    "target_type": row.target_type,
                    "target_value": row.target_value,
                    "consent_receipt_id": row.consent_receipt_id,
                    "delivery_state": row.delivery_state,
                    "observed_at": row.observed_at.isoformat(),
                    "learning": row.delivery_result,
                } for row in rows],
            }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "WARDROBE_FEEDBACK_STORE_UNAVAILABLE"}) from exc

@app.delete("/v1/feedback", dependencies=[Depends(require_internal_token)], tags=["wardrobe intelligence"])
def delete_feedback(
    owner_user_id: Annotated[str, Query(min_length=1, max_length=128)],
) -> dict[str, object]:
    """Delete one verified owner's local learning-audit mirror after upstream erasure."""
    owner = owner_user_id.strip()
    if not owner:
        raise HTTPException(422, detail={"code": "INVALID_WARDROBE_OWNER_ID"})
    try:
        with Session(store().engine) as session, session.begin():
            result = session.execute(
                delete(WardrobeFeedbackEventRow).where(WardrobeFeedbackEventRow.owner_user_id == owner)
            )
            deleted = int(result.rowcount or 0)
        return {"status": "deleted", "deleted_feedback_events": deleted}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "WARDROBE_FEEDBACK_DELETE_UNAVAILABLE"}) from exc


@app.post("/v1/items/{item_id}/transition",dependencies=[Depends(require_internal_token)],tags=["wardrobe"])
def transition(item_id:str,payload:TransitionItem)->dict[str,object]:
    try:
        updated=store().transition(owner_user_id=payload.owner_user_id.strip(),item_id=item_id,expected_version=payload.expected_version,target_status=WardrobeItemStatus(payload.target_status),command_id=payload.command_id.strip())
        return {"item":model_json(updated),"asset_deletion_queued":updated.status is WardrobeItemStatus.DELETED and updated.image_asset_id is not None}
    except (WardrobeNotFound,WardrobeConflict,PermissionError,ValueError) as exc: domain_error(exc)
    except HTTPException: raise
    except Exception as exc: raise HTTPException(503,detail={"code":"WARDROBE_STORE_UNAVAILABLE"}) from exc


@app.patch("/v1/items/{item_id}", dependencies=[Depends(require_internal_token)], tags=["wardrobe"])
def edit_item(item_id: str, payload: EditItem) -> dict[str, object]:
    """Edit one owned wardrobe item with optimistic concurrency and replay safety."""
    owner = payload.owner_user_id.strip()
    changes = payload.model_dump(exclude={"owner_user_id", "expected_version", "command_id"}, exclude_unset=True)
    if not changes or all(value is None for value in changes.values()):
        raise HTTPException(422, detail={"code": "WARDROBE_EDIT_EMPTY"})
    if not payload.command_id.strip():
        raise HTTPException(422, detail={"code": "WARDROBE_EDIT_COMMAND_ID_EMPTY"})
    if "display_name" in changes and changes["display_name"] is not None:
        changes["display_name"] = changes["display_name"].strip()
        if not changes["display_name"]:
            raise HTTPException(422, detail={"code": "WARDROBE_DISPLAY_NAME_EMPTY"})
    if "category" in changes and changes["category"] is not None:
        changes["category"] = changes["category"].strip()
        if not changes["category"]:
            raise HTTPException(422, detail={"code": "WARDROBE_CATEGORY_EMPTY"})
    if "attributes" in changes and changes["attributes"] is not None:
        changes["attributes"] = [value.strip() for value in changes["attributes"]]
    try:
        with Session(store().engine) as session, session.begin():
            row = session.scalar(select(WardrobeRow).where(
                WardrobeRow.owner_user_id == owner,
                WardrobeRow.item_id == item_id,
            ).with_for_update())
            if row is None:
                raise HTTPException(404, detail={"code": "WARDROBE_ITEM_NOT_FOUND"})
            if row.status == WardrobeItemStatus.DELETED.value:
                raise HTTPException(409, detail={"code": "WARDROBE_ITEM_DELETED"})
            if row.version != payload.expected_version:
                same_command = row.last_command_id == payload.command_id
                same_values = all(getattr(row, key) == value for key, value in changes.items())
                if same_command and same_values:
                    return {"item": model_json(WardrobeItem(
                        item_id=row.item_id, owner_user_id=row.owner_user_id,
                        display_name=row.display_name, category=row.category,
                        attributes=tuple(row.attributes or ()), catalog_product_id=row.catalog_product_id,
                        image_asset_id=row.image_asset_id, image_storage_consent=row.image_storage_consent,
                        status=WardrobeItemStatus(row.status), version=row.version,
                        last_command_id=row.last_command_id,
                    )), "status": "replayed"}
                raise HTTPException(409, detail={"code": "WARDROBE_VERSION_CONFLICT", "current_version": row.version})
            candidate = WardrobeItem(
                item_id=row.item_id, owner_user_id=row.owner_user_id,
                display_name=changes.get("display_name", row.display_name) or row.display_name,
                category=changes.get("category", row.category) or row.category,
                attributes=tuple(changes.get("attributes", row.attributes or ())),
                catalog_product_id=row.catalog_product_id, image_asset_id=row.image_asset_id,
                image_storage_consent=row.image_storage_consent,
                status=WardrobeItemStatus(row.status), version=row.version + 1,
                last_command_id=payload.command_id.strip(),
            )
            row.display_name = candidate.display_name
            row.category = candidate.category
            row.attributes = list(candidate.attributes)
            row.version = candidate.version
            row.last_command_id = candidate.last_command_id
            row.updated_at = datetime.now(timezone.utc)
            session.flush()
            return {"item": model_json(candidate), "status": "updated"}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "INVALID_WARDROBE_EDIT", "detail": str(exc)}) from exc
    except Exception as exc:
        raise HTTPException(503, detail={"code": "WARDROBE_STORE_UNAVAILABLE"}) from exc



def _outfit_json(session: Session, row: WardrobeOutfitRow) -> dict[str, object]:
    pieces = []
    for piece in row.pieces or []:
        item = session.get(WardrobeRow, (row.owner_user_id, piece["wardrobe_item_id"]))
        item_payload = None
        if item is not None and item.status == WardrobeItemStatus.ACTIVE.value:
            item_payload = {
                "item_id": item.item_id,
                "display_name": item.display_name,
                "category": item.category,
                "attributes": list(item.attributes or []),
                "version": item.version,
            }
        pieces.append({
            "slot_id": piece["slot_id"],
            "wardrobe_item_id": piece["wardrobe_item_id"],
            "item": item_payload,
            "availability": "available" if item_payload else "unavailable",
        })
    return {
        "outfit_id": row.outfit_id,
        "owner_user_id": row.owner_user_id,
        "name": row.name,
        "pieces": pieces,
        "status": row.status,
        "version": row.version,
        "last_command_id": row.last_command_id,
    }


def _require_active_outfit_item(session: Session, owner: str, item_id: str) -> WardrobeRow:
    item = session.get(WardrobeRow, (owner, item_id))
    if item is None:
        raise HTTPException(404, detail={"code": "WARDROBE_ITEM_NOT_FOUND"})
    if item.status != WardrobeItemStatus.ACTIVE.value:
        raise HTTPException(409, detail={"code": "OUTFIT_ITEM_NOT_ACTIVE"})
    return item


@app.get("/v1/outfits", dependencies=[Depends(require_internal_token)], tags=["saved outfits"])
def list_outfits(owner_user_id: Annotated[str, Query(min_length=1, max_length=128)]) -> dict[str, object]:
    owner = owner_user_id.strip()
    try:
        with Session(store().engine) as session:
            rows = session.scalars(
                select(WardrobeOutfitRow)
                .where(WardrobeOutfitRow.owner_user_id == owner, WardrobeOutfitRow.status == "active")
                .order_by(WardrobeOutfitRow.updated_at.desc())
            ).all()
            return {"owner_user_id": owner, "outfits": [_outfit_json(session, row) for row in rows]}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "WARDROBE_OUTFIT_STORE_UNAVAILABLE"}) from exc


@app.post("/v1/outfits", status_code=201, dependencies=[Depends(require_internal_token)], tags=["saved outfits"])
def create_outfit(payload: CreateOutfit) -> dict[str, object]:
    owner = payload.owner_user_id.strip()
    pieces = [{"slot_id": p.slot_id.strip(), "wardrobe_item_id": p.wardrobe_item_id.strip()} for p in payload.pieces]
    if len({p["slot_id"] for p in pieces}) != len(pieces):
        raise HTTPException(422, detail={"code": "OUTFIT_SLOT_DUPLICATE"})
    if len({p["wardrobe_item_id"] for p in pieces}) != len(pieces):
        raise HTTPException(422, detail={"code": "OUTFIT_ITEM_DUPLICATE"})
    try:
        with Session(store().engine) as session, session.begin():
            for piece in pieces:
                _require_active_outfit_item(session, owner, piece["wardrobe_item_id"])
            row = WardrobeOutfitRow(
                owner_user_id=owner, outfit_id=payload.outfit_id.strip(),
                name=payload.name.strip(), pieces=pieces, status="active", version=1,
            )
            if not row.name:
                raise HTTPException(422, detail={"code": "OUTFIT_NAME_EMPTY"})
            session.add(row)
            session.flush()
            return {"outfit": _outfit_json(session, row), "status": "created"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "WARDROBE_OUTFIT_STORE_UNAVAILABLE"}) from exc


@app.post("/v1/outfits/{outfit_id}/pieces", status_code=201, dependencies=[Depends(require_internal_token)], tags=["saved outfits"])
def add_outfit_piece(outfit_id: str, payload: AddOutfitPiece) -> dict[str, object]:
    owner = payload.owner_user_id.strip()
    try:
        with Session(store().engine) as session, session.begin():
            row = session.scalar(select(WardrobeOutfitRow).where(
                WardrobeOutfitRow.owner_user_id == owner, WardrobeOutfitRow.outfit_id == outfit_id,
            ).with_for_update())
            if row is None:
                raise HTTPException(404, detail={"code": "SAVED_OUTFIT_NOT_FOUND"})
            if row.status != "active":
                raise HTTPException(409, detail={"code": "SAVED_OUTFIT_NOT_ACTIVE"})
            pieces = list(row.pieces or [])
            desired = {"slot_id": payload.slot_id.strip(), "wardrobe_item_id": payload.wardrobe_item_id.strip()}
            fingerprint = hashlib.sha256(json.dumps({
                "action": "add", "outfit_id": outfit_id, **desired,
            }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            if payload.expected_version != row.version:
                if row.last_command_id == payload.command_id and row.last_command_hash == fingerprint:
                    return {"outfit": _outfit_json(session, row), "status": "replayed"}
                raise HTTPException(409, detail={"code": "SAVED_OUTFIT_VERSION_CONFLICT", "current_version": row.version})
            if any(p["slot_id"] == desired["slot_id"] for p in pieces):
                raise HTTPException(409, detail={"code": "OUTFIT_SLOT_ALREADY_EXISTS"})
            if any(p["wardrobe_item_id"] == desired["wardrobe_item_id"] for p in pieces):
                raise HTTPException(409, detail={"code": "OUTFIT_ITEM_ALREADY_EXISTS"})
            _require_active_outfit_item(session, owner, desired["wardrobe_item_id"])
            row.pieces = pieces + [desired]
            row.version += 1
            row.last_command_id = payload.command_id.strip()
            row.last_command_hash = fingerprint
            row.updated_at = datetime.now(timezone.utc)
            session.flush()
            return {"outfit": _outfit_json(session, row), "status": "updated"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "WARDROBE_OUTFIT_STORE_UNAVAILABLE"}) from exc


@app.patch("/v1/outfits/{outfit_id}/pieces/{slot_id}", dependencies=[Depends(require_internal_token)], tags=["saved outfits"])
def edit_outfit_piece(outfit_id: str, slot_id: str, payload: EditOutfitPiece) -> dict[str, object]:
    """Replace or remove one slot; every other piece remains byte-for-byte unchanged."""
    if "wardrobe_item_id" not in payload.model_fields_set:
        raise HTTPException(422, detail={"code": "OUTFIT_PIECE_ACTION_REQUIRED"})
    owner = payload.owner_user_id.strip()
    try:
        with Session(store().engine) as session, session.begin():
            row = session.scalar(select(WardrobeOutfitRow).where(
                WardrobeOutfitRow.owner_user_id == owner, WardrobeOutfitRow.outfit_id == outfit_id,
            ).with_for_update())
            if row is None:
                raise HTTPException(404, detail={"code": "SAVED_OUTFIT_NOT_FOUND"})
            if row.status != "active":
                raise HTTPException(409, detail={"code": "SAVED_OUTFIT_NOT_ACTIVE"})
            pieces = list(row.pieces or [])
            desired = None if payload.wardrobe_item_id is None else payload.wardrobe_item_id.strip()
            fingerprint = hashlib.sha256(json.dumps({
                "action": "edit_piece", "outfit_id": outfit_id, "slot_id": slot_id,
                "wardrobe_item_id": desired,
            }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            if payload.expected_version != row.version:
                if row.last_command_id == payload.command_id and row.last_command_hash == fingerprint:
                    return {"outfit": _outfit_json(session, row), "status": "replayed"}
                raise HTTPException(409, detail={"code": "SAVED_OUTFIT_VERSION_CONFLICT", "current_version": row.version})
            index = next((i for i, p in enumerate(pieces) if p["slot_id"] == slot_id), None)
            if index is None:
                raise HTTPException(404, detail={"code": "SAVED_OUTFIT_PIECE_NOT_FOUND"})
            if desired is not None:
                _require_active_outfit_item(session, owner, desired)
                if any(i != index and p["wardrobe_item_id"] == desired for i, p in enumerate(pieces)):
                    raise HTTPException(409, detail={"code": "OUTFIT_ITEM_ALREADY_EXISTS"})
                pieces[index] = {**pieces[index], "wardrobe_item_id": desired}
            else:
                pieces.pop(index)
                if not pieces:
                    raise HTTPException(422, detail={"code": "SAVED_OUTFIT_CANNOT_BE_EMPTY"})
            row.pieces = pieces
            row.version += 1
            row.last_command_id = payload.command_id.strip()
            row.last_command_hash = fingerprint
            row.updated_at = datetime.now(timezone.utc)
            session.flush()
            return {"outfit": _outfit_json(session, row), "status": "updated"}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, detail={"code": "WARDROBE_OUTFIT_STORE_UNAVAILABLE"}) from exc


@app.post("/v1/outfits/{outfit_id}/wear", status_code=201, dependencies=[Depends(require_internal_token)], tags=["outfit history"])
def record_outfit_wear(outfit_id: str, payload: RecordOutfitWear) -> dict[str, object]:
    """Record a user-declared wear event and deliver item-level wear signals under consent."""
    owner = payload.owner_user_id.strip()
    event_id = payload.event_id.strip()
    try:
        observed = datetime.fromisoformat(payload.observed_at.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            raise ValueError("observed_at requires timezone")
        observed = observed.astimezone(timezone.utc)
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "INVALID_OUTFIT_WEAR_TIMESTAMP"}) from exc
    context = {str(k).strip(): str(v).strip() for k, v in payload.context.items()}
    if any(not k or not v or len(k) > 32 or len(v) > 80 for k, v in context.items()):
        raise HTTPException(422, detail={"code": "INVALID_OUTFIT_WEAR_CONTEXT"})
    document = {
        "owner_user_id": owner, "event_id": event_id, "outfit_id": outfit_id,
        "expected_outfit_version": payload.expected_outfit_version,
        "consent_receipt_id": payload.consent_receipt_id.strip(),
        "observed_at": observed.isoformat(), "context": context,
    }
    digest = hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    try:
        wardrobe = store()
        with Session(wardrobe.engine) as session:
            existing = session.get(WardrobeOutfitWearEventRow, (owner, event_id))
            if existing is not None:
                if existing.payload_hash != digest:
                    raise HTTPException(409, detail={"code": "OUTFIT_WEAR_EVENT_CONFLICT"})
                return {"status": "replayed", "event_id": event_id, "items": existing.items_snapshot,
                        "delivery": existing.delivery_result}
            outfit = session.scalar(select(WardrobeOutfitRow).where(
                WardrobeOutfitRow.owner_user_id == owner, WardrobeOutfitRow.outfit_id == outfit_id,
                WardrobeOutfitRow.status == "active",
            ))
            if outfit is None:
                raise HTTPException(404, detail={"code": "SAVED_OUTFIT_NOT_FOUND"})
            if outfit.version != payload.expected_outfit_version:
                raise HTTPException(409, detail={"code": "SAVED_OUTFIT_VERSION_CONFLICT", "current_version": outfit.version})
            items_snapshot = []
            items = []
            for piece in outfit.pieces or []:
                item = session.scalar(select(WardrobeRow).where(
                    WardrobeRow.owner_user_id == owner, WardrobeRow.item_id == piece["wardrobe_item_id"],
                ))
                if item is None or item.status != "active":
                    raise HTTPException(409, detail={"code": "OUTFIT_CONTAINS_INACTIVE_ITEM"})
                items.append(item)
                items_snapshot.append({
                    "slot_id": piece["slot_id"], "item_id": item.item_id, "item_version": item.version,
                    "display_name": item.display_name, "category": item.category,
                    "catalog_product_id": item.catalog_product_id,
                })
        deliveries = []
        for item in items:
            item_event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"cirvanna:outfit-wear:{owner}:{event_id}:{item.item_id}"))
            result = deliver_learning_event(
                owner_user_id=owner, item_id=item.item_id, item_version=item.version,
                display_name=item.display_name, category=item.category, attributes=list(item.attributes or []),
                event_id=item_event_id, signal="wear", target_type=None, target_value=None,
                consent_receipt_id=payload.consent_receipt_id.strip(), observed_at=observed,
            )
            deliveries.append({"item_id": item.item_id, "event_id": item_event_id, "result": result})
        with Session(wardrobe.engine) as session, session.begin():
            existing = session.get(WardrobeOutfitWearEventRow, (owner, event_id))
            if existing is None:
                session.add(WardrobeOutfitWearEventRow(
                    owner_user_id=owner, event_id=event_id, outfit_id=outfit_id,
                    outfit_version=payload.expected_outfit_version, items_snapshot=items_snapshot,
                    context=context, consent_receipt_id=payload.consent_receipt_id.strip(),
                    payload_hash=digest, delivery_result=deliveries, observed_at=observed,
                ))
            elif existing.payload_hash != digest:
                raise HTTPException(409, detail={"code": "OUTFIT_WEAR_EVENT_CONFLICT"})
        return {"status": "recorded", "event_id": event_id, "outfit_id": outfit_id,
                "outfit_version": payload.expected_outfit_version, "items": items_snapshot,
                "delivery": deliveries}
    except HTTPException:
        raise
    except LearningIntegrationError as exc:
        raise HTTPException(exc.status_code, detail={"code": exc.code}) from exc
    except Exception as exc:
        raise HTTPException(503, detail={"code": "OUTFIT_WEAR_HISTORY_UNAVAILABLE"}) from exc


@app.get("/v1/wear-history", dependencies=[Depends(require_internal_token)], tags=["outfit history"])
def list_wear_history(owner_user_id: Annotated[str, Query(min_length=1, max_length=128)],
                      limit: int = Query(default=50, ge=1, le=100)) -> dict[str, object]:
    owner = owner_user_id.strip()
    try:
        with Session(store().engine) as session:
            rows = session.scalars(select(WardrobeOutfitWearEventRow)
                .where(WardrobeOutfitWearEventRow.owner_user_id == owner)
                .order_by(WardrobeOutfitWearEventRow.observed_at.desc()).limit(limit)).all()
            return {"owner_user_id": owner, "items": [{
                "event_id": row.event_id, "outfit_id": row.outfit_id,
                "outfit_version": row.outfit_version, "items": row.items_snapshot,
                "context": row.context, "observed_at": row.observed_at.isoformat(),
            } for row in rows]}
    except Exception as exc:
        raise HTTPException(503, detail={"code": "OUTFIT_WEAR_HISTORY_UNAVAILABLE"}) from exc
