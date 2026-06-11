"""Pytest bootstrap for chatbot-api.

Ensures the service root (the directory containing the ``app`` package) is at the
*front* of sys.path so ``import app...`` resolves to this service and never to the
repo-root ``app.py`` (the Dash entrypoint), regardless of where pytest is invoked.
"""

import os
import sys

# app/tests/conftest.py -> parents: tests -> app -> <service root>
_SERVICE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if sys.path[:1] != [_SERVICE_ROOT]:
    if _SERVICE_ROOT in sys.path:
        sys.path.remove(_SERVICE_ROOT)
    sys.path.insert(0, _SERVICE_ROOT)

# Keep auth disabled for unit tests (matches sibling-service default).
os.environ.setdefault("API_AUTH_REQUIRED", "false")
