"""Keep the terminal clean: hide harmless warnings and progress bars from libraries.

Nothing here hides OntoReview's own messages or real errors; only known noise:

* NiceGUI "An element has been deleted but is still being used": a background task finished after its
  page was left (switching pages, Skip, Build docs). NiceGUI already ignores the update; the warning
  and its stack trace are noise for users.
* NiceGUI "Event listeners changed after initial definition": an internal re-render notice.
* torch "Redirects are currently not supported in MacOs" (printed when torch is imported).
* transformers / Hugging Face Hub progress bars ("Loading weights …") and advisory warnings.

``ONTOREVIEW_DEBUG=1`` shows all of it again.
"""

from __future__ import annotations

import logging
import os

_NOISE = ("An element has been deleted but is still being used",
          "Event listeners changed after initial definition",
          "Redirects are currently not supported")


class _DropNoise(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        return not any(n in msg for n in _NOISE)


_done = False


def quiet() -> None:
    """Install the filters (idempotent). Call before NiceGUI, torch or transformers do their logging."""
    global _done
    if _done or (os.environ.get("ONTOREVIEW_DEBUG") or "").strip() in ("1", "true", "on"):
        return
    _done = True
    flt = _DropNoise()
    for name in ("nicegui", "torch.distributed.elastic.multiprocessing.redirects", "torch.distributed.elastic"):
        logging.getLogger(name).addFilter(flt)
    logging.getLogger("torch.distributed.elastic.multiprocessing.redirects").setLevel(logging.ERROR)
    for h in logging.getLogger().handlers:     # a filter on the root handlers catches child loggers too
        h.addFilter(flt)
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def quiet_transformers() -> None:
    """After transformers is imported: no progress bars, errors only (its own switches)."""
    if (os.environ.get("ONTOREVIEW_DEBUG") or "").strip() in ("1", "true", "on"):
        return
    try:
        from transformers.utils import logging as tlog

        tlog.disable_progress_bar()
        tlog.set_verbosity_error()
    except Exception:  # noqa: BLE001 - transformers missing or older
        pass
