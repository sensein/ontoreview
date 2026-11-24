"""ontoreview: beautiful, self-contained documentation for OWL, RDFS, SKOS and LinkML models.

Quick start::

    import ontoreview
    ontoreview.build("ontology.ttl", out="docs/")
"""

__version__ = "1.0.4"

from .build import BuildResult, build, build_single_file, check  # noqa: E402
from .config import Config, load_config  # noqa: E402
from .diff import compare_files  # noqa: E402

__all__ = ["BuildResult", "Config", "build", "build_single_file", "check", "compare_files", "load_config", "__version__"]
