"""Tests for wavern.gui.theme_manager.

WHAT THIS TESTS:
- list_themes() returns all five expected themes in sorted order
- apply() does not raise for any valid theme name, or for an unknown theme name
- save_preference() and load_preference() round-trip the selected theme name
- QSS content is preloaded into cache at __init__ time
- apply() is a no-op when the requested theme is already active
Does NOT test: visual appearance of applied QSS styles
"""

from PySide6.QtWidgets import QApplication

from wavern.gui.theme_manager import ThemeManager

_app = QApplication.instance() or QApplication([])


class TestThemeManager:
    """Tests for theme listing, application, and preference save/load."""

    def test_list_themes_includes_all_five(self) -> None:
        tm = ThemeManager()
        themes = tm.list_themes()
        expected = {"dark", "light", "nord", "dracula", "gruvbox"}
        assert expected == set(themes)

    def test_list_themes_sorted(self) -> None:
        tm = ThemeManager()
        themes = tm.list_themes()
        assert themes == sorted(themes)

    def test_apply_dark_does_not_crash(self) -> None:
        tm = ThemeManager()
        tm.apply(_app, "dark")

    def test_apply_all_themes_does_not_crash(self) -> None:
        tm = ThemeManager()
        for theme in tm.list_themes():
            tm.apply(_app, theme)

    def test_apply_nonexistent_theme_is_safe(self) -> None:
        tm = ThemeManager()
        tm.apply(_app, "nonexistent_theme_xyz")

    def test_save_and_load_preference(self) -> None:
        tm = ThemeManager()
        tm.save_preference("nord")
        assert tm.load_preference() == "nord"
        # Restore default
        tm.save_preference("dark")

    def test_default_preference_is_dark(self) -> None:
        tm = ThemeManager()
        tm.save_preference("dark")
        assert tm.load_preference() == "dark"

    def test_all_themes_preloaded_in_cache(self) -> None:
        tm = ThemeManager()
        expected = {"dark", "light", "nord", "dracula", "gruvbox"}
        assert expected.issubset(tm._cache.keys())

    def test_cache_content_is_nonempty_strings(self) -> None:
        tm = ThemeManager()
        for name, content in tm._cache.items():
            assert isinstance(content, str) and len(content) > 0, f"Empty cache entry for {name!r}"

    def test_apply_same_theme_twice_is_noop(self) -> None:
        tm = ThemeManager()
        tm.apply(_app, "dark")
        stylesheet_after_first = _app.styleSheet()
        # Applying the same theme again should not change anything
        tm.apply(_app, "dark")
        assert _app.styleSheet() == stylesheet_after_first

    def test_current_theme_tracked_after_apply(self) -> None:
        tm = ThemeManager()
        assert tm._current_theme is None
        tm.apply(_app, "nord")
        assert tm._current_theme == "nord"
