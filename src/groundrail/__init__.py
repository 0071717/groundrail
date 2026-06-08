"""Groundrail: local evidence and context-routing framework for AI-assisted code work.

Architecture is organised as three components (see docs/09):

- ``indexer``  : deterministic source snapshot + unit index (no AI).
- ``analyzer`` : AI unit analysis with explicit provenance and uncertainty.
- ``router``   : retrieval, context packs, Kiro runner, and answer audit.

``core`` holds the shared trust contract: vocabulary, artifact envelope,
evidence/provenance, storage, and strict validation. Lower components never
import higher ones.
"""

__version__ = "0.1.0"
