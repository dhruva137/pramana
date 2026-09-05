"""Sandboxed simulated-merchant catalog for Pramana adversary evaluation.

All merchants are labelled simulations. Payloads are seeded only into this
service. Permanent banner: SIMULATED MERCHANT — INJECTION TEST ENVIRONMENT.
"""

from merchants.catalog import BANNER, MERCHANTS, get_item, list_items, search_catalog
from merchants.service import router

__all__ = [
    "BANNER",
    "MERCHANTS",
    "get_item",
    "list_items",
    "router",
    "search_catalog",
]
