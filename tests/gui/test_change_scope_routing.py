"""Tests for ChangeScope enum.

WHAT THIS TESTS:
- ChangeScope enum members are importable and distinct
Does NOT test: routing logic (tested via integration)
"""

from wavern.gui.change_scope import ChangeScope


def test_all_scopes_distinct():
    values = [s.value for s in ChangeScope]
    assert len(values) == len(set(values))


def test_full_scope_exists():
    assert ChangeScope.FULL.value == "full"
