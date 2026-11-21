"""Fixing quality findings: suggestions the user reviews, written to a new ontology file.

* :mod:`.model`: suggestions, options (triples to add/remove), form fields.
* :mod:`.rules`: fixers for the built-in rules (exact edits, values only the user knows, manual).
* :mod:`.session`: findings → suggestions → decisions → ``a-v1.ttl`` + patch + record.
* :mod:`.ai`: AI drafts (definitions, refinements, description) from Hugging Face, Ollama or an API.

The source ontology is never changed, and nothing is applied without the user's acceptance.
"""

from __future__ import annotations

from .model import Field_, Option, Suggestion
from .session import (
                      FixError,
                      FixSession,
                      MissingMetadata,
                      WriteResult,
                      check_required,
                      fixes_record,
                      next_version,
                      required_missing,
)

__all__ = ["MissingMetadata", "check_required", "Field_", "FixError", "FixSession", "Option", "Suggestion", "WriteResult", "fixes_record", "next_version",
           "required_missing"]
