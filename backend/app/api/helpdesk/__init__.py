"""Helpdesk API package — re-exports the combined router."""

from .tickets import router

__all__ = ["router"]
