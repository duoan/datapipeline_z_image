"""
conftest.py — Patch missing runtime dependencies for the test environment.

This file is executed by pytest before any test collection, making the patches
available to all test modules regardless of import order.
"""

import sys
import types
from datetime import timezone
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Backport datetime.UTC for Python 3.10 (the project targets Python 3.11+).
# ---------------------------------------------------------------------------
import datetime as _dt

if not hasattr(_dt, "UTC"):
    _dt.UTC = timezone.utc

# ---------------------------------------------------------------------------
# Stub out optional heavy dependencies that are not installed in the CI
# environment used for unit tests.  Tests that actually exercise these
# modules are skipped separately with pytest.importorskip / pytest.mark.
# ---------------------------------------------------------------------------


def _make_package(name: str) -> types.ModuleType:
    """Create a real (but empty) module and register it in sys.modules."""
    mod = types.ModuleType(name)
    mod.__package__ = name
    mod.__path__ = []  # type: ignore[assignment]  # marks it as a package
    sys.modules[name] = mod
    return mod


def _make_module(name: str, parent: types.ModuleType | None = None) -> types.ModuleType:
    mod = types.ModuleType(name)
    mod.__package__ = name.rsplit(".", 1)[0] if "." in name else name
    sys.modules[name] = mod
    if parent is not None:
        setattr(parent, name.rsplit(".", 1)[-1], mod)
    return mod


# resiliparse stubs
_rs = _make_package("resiliparse")
_rs_extract = _make_package("resiliparse.extract")
_rs.extract = _rs_extract  # type: ignore[attr-defined]

_rs_extract_html = _make_module("resiliparse.extract.html2text", _rs_extract)
_rs_extract_html.extract_plain_text = MagicMock(return_value="")

_rs_parse = _make_package("resiliparse.parse")
_rs.parse = _rs_parse  # type: ignore[attr-defined]

_rs_parse_enc = _make_module("resiliparse.parse.encoding", _rs_parse)
_rs_parse_enc.bytes_to_str = MagicMock(return_value="")
_rs_parse_enc.detect_encoding = MagicMock(return_value="utf-8")

_rs_parse_lang = _make_module("resiliparse.parse.lang", _rs_parse)
_rs_parse_lang.detect_fast = MagicMock(return_value="en")
