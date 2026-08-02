"""Configuration management package.

This package provides configuration loading and management for the application.
"""

from .settings import Settings, get_index_configs

__all__ = ["Settings", "get_index_configs"]
