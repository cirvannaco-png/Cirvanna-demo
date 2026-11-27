"""Shared privacy-safe HTTP request and dependency observability."""

from .observability import RequestMetrics, install_observability

__all__ = ["RequestMetrics", "install_observability"]
