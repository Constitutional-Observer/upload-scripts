"""Search backend abstraction layer.

This package provides an abstraction over different search backends (Meilisearch,
Elasticsearch, etc.) to reduce coupling and make switching backends easier.
"""

from .base import SearchBackend

__all__ = ["SearchBackend"]
