"""Canonical signed evidence envelope for explicit cultural declarations."""
from __future__ import annotations
import json
from collections.abc import Mapping
from typing import Any
EVIDENCE_CONTRACT_VERSION="1.0.0"

def _get(value:Any,key:str,default:Any=None)->Any:
    if isinstance(value,Mapping): return value.get(key,default)
    return getattr(value,key,default)

def _enum(item:Any)->Any:
    return item.value if hasattr(item,"value") else item

def requirement_payload(value:Any)->dict[str,Any]:
    return {
        "requirement_id":str(_get(value,"requirement_id","")).strip(),
        "declaration_id":str(_get(value,"declaration_id","")).strip(),
        "user_id":str(_get(value,"user_id","")).strip(),
        "attribute":str(_get(value,"attribute","")).strip(),
        "kind":_enum(_get(value,"kind","")),
        "hard":bool(_get(value,"hard",True)),
        "active":bool(_get(value,"active",True)),
    }

def canonical_cultural_evidence_payload(
    request_id:str,
    user_id:str,
    candidate_id:str,
    candidate_attributes:tuple[str,...]|list[str],
    candidate_attributes_complete:bool,
    requirements:tuple[Any,...]|list[Any],
)->bytes:
    """Canonicalize the exact explicit-declaration evidence evaluated by CAL."""
    for label,value in (("request_id",request_id),("user_id",user_id),("candidate_id",candidate_id)):
        if not isinstance(value,str) or not value.strip(): raise ValueError(f"{label} must not be empty")
    if not isinstance(candidate_attributes,(tuple,list)): raise ValueError("candidate_attributes must be a tuple or list")
    if any(not isinstance(value,str) or not value.strip() for value in candidate_attributes):
        raise ValueError("candidate attributes must be non-empty strings")
    if not isinstance(candidate_attributes_complete,bool): raise ValueError("candidate_attributes_complete must be a boolean")
    if not isinstance(requirements,(tuple,list)): raise ValueError("requirements must be a tuple or list")
    parsed=[requirement_payload(item) for item in requirements]
    for item in parsed:
        if not all(item[key] for key in ("requirement_id","declaration_id","user_id","attribute","kind")):
            raise ValueError("cultural requirements must contain explicit declaration identifiers and attributes")
        if item["user_id"]!=user_id.strip():
            raise ValueError("all cultural declarations must belong to the evaluated user")
        if item["kind"] not in {"required_attribute","forbidden_attribute"}:
            raise ValueError("unknown cultural requirement kind")
    parsed.sort(key=lambda item:(item["user_id"],item["declaration_id"],item["requirement_id"]))
    if len({item["requirement_id"] for item in parsed}) != len(parsed):
        raise ValueError("duplicate cultural requirement IDs")
    document={
        "contract_version":EVIDENCE_CONTRACT_VERSION,
        "request_id":request_id.strip(),
        "user_id":user_id.strip(),
        "candidate_id":candidate_id.strip(),
        "candidate_attributes":sorted({item.strip().casefold() for item in candidate_attributes}),
        "candidate_attributes_complete":candidate_attributes_complete,
        "cultural_requirements":parsed,
    }
    return json.dumps(document,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
