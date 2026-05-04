"""pytest bootstrap for crm-engine.

Runtime layout: the crm-engine container's `app/` is a layered copy of
`customer-api/app/` plus the crm-engine specific `routers/` and `main.py`
(see services/crm-engine/Dockerfile). To run the same import paths from
source we:

1. Put crm-engine first on sys.path so `import app` resolves to the
   crm-engine package (which contains the relocated CRM routers).
2. Append customer-api's `app/` directory to ``app.__path__`` so siblings
   like ``app.services``, ``app.db``, ``app.models``, ``app.core``,
   ``app.utils`` and ``app.adapters`` (only present in customer-api) keep
   importing without copying or symlinking.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_CRM_ENGINE_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
_CUSTOMER_API_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", "customer-api"))
_GUI_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))

if _CRM_ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _CRM_ENGINE_ROOT)
if _CUSTOMER_API_ROOT not in sys.path:
    sys.path.append(_CUSTOMER_API_ROOT)
if _GUI_ROOT not in sys.path:
    sys.path.append(_GUI_ROOT)

# Merge customer-api/app/ into the crm-engine `app` package so app.services,
# app.db, app.models, app.core, app.utils and app.adapters resolve without
# duplicating code in source tree.
import app  # noqa: E402

_CUST_APP = os.path.join(_CUSTOMER_API_ROOT, "app")
if _CUST_APP not in app.__path__:
    app.__path__.append(_CUST_APP)
