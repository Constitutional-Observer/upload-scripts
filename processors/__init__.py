"""Document processors for legislative debate data.

This module provides a pluggable processor architecture for different data sources
(e.g., pre-existing files, API-based fetchers like Lok Sabha).
"""

from .base import BaseProcessor
from .filesystem import FilesystemProcessor

__all__ = ["BaseProcessor", "FilesystemProcessor"]
