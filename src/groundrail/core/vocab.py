"""Global vocabulary — the controlled enums every artifact must use.

These mirror ``docs/02_CONTRACTS_AND_ARTIFACTS.md`` and ``AGENTS.md``. Strict
validation rejects any value outside these sets, so producers and consumers
share one trust language.

Deviation from the original plan (per docs/09 review): the AI analysis schema
uses ``behavioral_notes`` instead of ``business_rules`` — "business rule"
implies authoritative domain knowledge an AI cannot reliably infer.
"""

from __future__ import annotations

# --- Status: the source-evidence state of a record ---------------------------
STATUS_VERIFIED = "verified"
STATUS_INFERRED = "inferred"
STATUS_UNSUPPORTED = "unsupported"
STATUS_STALE = "stale"
STATUS_CONTRADICTED = "contradicted"
STATUS_PARTIAL = "partial"
STATUS_UNKNOWN = "unknown"

STATUSES: frozenset[str] = frozenset(
    {
        STATUS_VERIFIED,
        STATUS_INFERRED,
        STATUS_UNSUPPORTED,
        STATUS_STALE,
        STATUS_CONTRADICTED,
        STATUS_PARTIAL,
        STATUS_UNKNOWN,
    }
)

# --- Confidence: a Groundrail policy bucket (not a model self-score) ----------
CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_NONE = "none"

CONFIDENCES: frozenset[str] = frozenset(
    {CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW, CONFIDENCE_NONE}
)

# --- Review status: orthogonal to status -------------------------------------
REVIEW_UNREVIEWED = "unreviewed"
REVIEW_NEEDS_REVIEW = "needs_review"
REVIEW_DEV_CONFIRMED = "dev_confirmed"
REVIEW_DEV_REJECTED = "dev_rejected"
REVIEW_STALE_CONFIRMATION = "stale_confirmation"
REVIEW_DISPUTED = "disputed"

REVIEW_STATUSES: frozenset[str] = frozenset(
    {
        REVIEW_UNREVIEWED,
        REVIEW_NEEDS_REVIEW,
        REVIEW_DEV_CONFIRMED,
        REVIEW_DEV_REJECTED,
        REVIEW_STALE_CONFIRMATION,
        REVIEW_DISPUTED,
    }
)

# --- Evidence kinds ----------------------------------------------------------
EVIDENCE_KINDS: frozenset[str] = frozenset(
    {
        "source_span",
        "unit_span",
        "import_reference",
        "call_candidate",
        "endpoint_candidate",
        "route_candidate",
        "test_definition",
        "test_result",
        "runtime_trace",
        "config_value",
        "generated_artifact",
        "human_review",
        "ai_analysis",
        "external_finding",
    }
)

# --- Unit kinds --------------------------------------------------------------
UNIT_KINDS: frozenset[str] = frozenset(
    {
        "python_function",
        "python_method",
        "python_class",
        "fastapi_endpoint_handler",
        "pydantic_model",
        "typescript_function",
        "react_component",
        "react_hook",
        "api_client_function",
        "test_function",
        "unknown_unit",
    }
)

# --- AI note types -----------------------------------------------------------
NOTE_TYPES: frozenset[str] = frozenset(
    {
        "complexity",
        "potential_bug",
        "refactor_opportunity",
        "test_gap",
        "naming_confusion",
        "dead_code_candidate",
        "missing_error_handling",
        "unclear_intent",
        "security_concern",
        "performance_concern",
        "library_gap",
        "documentation_gap",
    }
)

# --- Review scopes -----------------------------------------------------------
REVIEW_SCOPES: frozenset[str] = frozenset(
    {
        "unit_summary",
        "individual_claim",
        "behavioral_note",
        "ai_note",
        "uncertainty",
        "flow_edge",
        "impact_finding",
    }
)

# --- Complexity buckets ------------------------------------------------------
COMPLEXITY_SIMPLE = "simple"
COMPLEXITY_MODERATE = "moderate"
COMPLEXITY_COMPLEX = "complex"
COMPLEXITY_STATES: frozenset[str] = frozenset(
    {COMPLEXITY_SIMPLE, COMPLEXITY_MODERATE, COMPLEXITY_COMPLEX}
)

# --- Context-pack modes ------------------------------------------------------
CONTEXT_MODES: frozenset[str] = frozenset(
    {"ask", "debug", "review", "plan", "implement"}
)

# Phrase Kiro must use for any claim Groundrail does not support.
UNSUPPORTED_PHRASE = "Not confirmed by Groundrail"
CITATION_BLOCK_TAG = "groundrail_citations"
