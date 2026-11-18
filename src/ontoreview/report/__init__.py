"""Quality report generation: everything that turns check results into something to read.

* :mod:`.models`: result types (``Finding``, ``Report``, ``ExternalItem``, ``ExternalReport``) and
  the registry of external checkers (``TOOLS``).
* :mod:`.robot`, :mod:`.reasoner`, :mod:`.oops`: parse each external tool's output into findings.
* :mod:`.issues`: table rows for the app's Issues list.
* :mod:`.console`: terminal output; :mod:`.html`: a standalone HTML page.

The checks themselves are in :mod:`ontoreview.quality_checks`. The quality section of the
generated documentation is the theme template ``sections/quality.html``.
"""

from .models import (
                     SEVERITY_ORDER,
                     SEVERITY_RANK,
                     TOOLS,
                     ExternalItem,
                     ExternalReport,
                     Finding,
                     Report,
                     Severity,
                     curie_for,
                     new_report,
                     unavailable,
)

__all__ = ["SEVERITY_ORDER", "SEVERITY_RANK", "TOOLS", "ExternalItem", "ExternalReport", "Finding", "Report",
           "Severity", "curie_for", "new_report", "unavailable"]
