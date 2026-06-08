"""Weakest-link semantics for confidence and state propagation."""

from __future__ import annotations

from typing import Iterable

from ..core import vocab

# Higher rank = more trustworthy. Weakest-link picks the minimum.
_CONFIDENCE_RANK = {
    vocab.CONFIDENCE_HIGH: 3,
    vocab.CONFIDENCE_MEDIUM: 2,
    vocab.CONFIDENCE_LOW: 1,
    vocab.CONFIDENCE_NONE: 0,
}
_CONFIDENCE_BY_RANK = {rank: name for name, rank in _CONFIDENCE_RANK.items()}

_STATE_RANK = {
    vocab.STATUS_VERIFIED: 6,
    vocab.STATUS_INFERRED: 5,
    vocab.STATUS_PARTIAL: 4,
    vocab.STATUS_UNSUPPORTED: 3,
    vocab.STATUS_UNKNOWN: 2,
    vocab.STATUS_CONTRADICTED: 1,
    vocab.STATUS_STALE: 0,
}
_STATE_BY_RANK = {rank: name for name, rank in _STATE_RANK.items()}


def weakest_confidence(values: Iterable[str]) -> str:
    ranks = [_CONFIDENCE_RANK.get(v, 0) for v in values]
    if not ranks:
        return vocab.CONFIDENCE_NONE
    return _CONFIDENCE_BY_RANK[min(ranks)]


def weakest_state(values: Iterable[str]) -> str:
    ranks = [_STATE_RANK.get(v, 2) for v in values]
    if not ranks:
        return vocab.STATUS_UNKNOWN
    return _STATE_BY_RANK[min(ranks)]


def cap_at_inferred(state: str) -> str:
    """A composed/derived claim can never exceed ``inferred`` trust.

    Even when every node boundary is ``verified``, the *relationships* between
    them are heuristically resolved, so a flow's behavioural claim tops out at
    inferred (or worse, never better).
    """
    if _STATE_RANK.get(state, 2) > _STATE_RANK[vocab.STATUS_INFERRED]:
        return vocab.STATUS_INFERRED
    return state
