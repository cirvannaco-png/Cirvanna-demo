"""Deterministic, evidence-governed appearance specialist primitives."""
from .contracts import AppearanceContext, CandidateEvaluation, CatalogProduct, CatalogSnapshot, EvaluationStatus, SpecialistId, SpecialistResult
from .engine import evaluate_candidate, run_specialist
from .registry import SPECIALISTS, SpecialistDescriptor
from .composer import LookCompositionResult, LookOption, build_look

__all__ = ["AppearanceContext", "CandidateEvaluation", "CatalogProduct", "CatalogSnapshot", "EvaluationStatus", "SpecialistId", "SpecialistResult", "SPECIALISTS", "SpecialistDescriptor", "evaluate_candidate", "run_specialist", "LookCompositionResult", "LookOption", "build_look"]
