"""Tests for SELLABLE_HOST_BASED_ENABLED runtime flag."""
from __future__ import annotations

import os

import pytest

from shared.sellable.config import host_based_sellable_enabled


@pytest.fixture(autouse=True)
def _clear_host_based_env(monkeypatch):
    monkeypatch.delenv("SELLABLE_HOST_BASED_ENABLED", raising=False)


def test_host_based_sellable_disabled_by_default():
    assert host_based_sellable_enabled() is False


@pytest.mark.parametrize("value", ["true", "True", "1", "yes", "YES"])
def test_host_based_sellable_enabled_truthy(monkeypatch, value):
    monkeypatch.setenv("SELLABLE_HOST_BASED_ENABLED", value)
    assert host_based_sellable_enabled() is True


@pytest.mark.parametrize("value", ["false", "0", "no", ""])
def test_host_based_sellable_enabled_falsy(monkeypatch, value):
    monkeypatch.setenv("SELLABLE_HOST_BASED_ENABLED", value)
    assert host_based_sellable_enabled() is False
