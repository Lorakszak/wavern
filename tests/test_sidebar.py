"""Tests for SidebarWidget — tabs, switching, and split mode."""

from PySide6.QtWidgets import QApplication, QLabel

from wavern.gui.sidebar import SidebarWidget

_app = QApplication.instance() or QApplication([])


class TestSidebarWidget:
    """Tests for tab management and split toggle."""

    def test_add_tab_returns_index(self) -> None:
        sidebar = SidebarWidget()
        idx = sidebar.add_tab("Tab A", QLabel("A"))
        assert idx == 0
        idx2 = sidebar.add_tab("Tab B", QLabel("B"))
        assert idx2 == 1

    def test_tab_count(self) -> None:
        sidebar = SidebarWidget()
        assert sidebar.tab_count() == 0
        sidebar.add_tab("Tab A", QLabel("A"))
        sidebar.add_tab("Tab B", QLabel("B"))
        assert sidebar.tab_count() == 2

    def test_current_index_default(self) -> None:
        sidebar = SidebarWidget()
        sidebar.add_tab("Tab A", QLabel("A"))
        sidebar.add_tab("Tab B", QLabel("B"))
        assert sidebar.current_index() == 0

    def test_set_current_index(self) -> None:
        sidebar = SidebarWidget()
        sidebar.add_tab("Tab A", QLabel("A"))
        sidebar.add_tab("Tab B", QLabel("B"))
        sidebar.set_current_index(1)
        assert sidebar.current_index() == 1

    def test_split_default_off(self) -> None:
        sidebar = SidebarWidget()
        assert sidebar.is_split is False
        assert sidebar.lower.isHidden() is True

    def test_toggle_split(self) -> None:
        sidebar = SidebarWidget()
        sidebar.add_tab("Upper", QLabel("U"))
        sidebar.add_lower_tab("Lower", QLabel("L"))
        sidebar.toggle_split()
        assert sidebar.is_split is True
        assert sidebar.lower.isHidden() is False
        sidebar.toggle_split()
        assert sidebar.is_split is False
        assert sidebar.lower.isHidden() is True

    def test_set_split(self) -> None:
        sidebar = SidebarWidget()
        sidebar.set_split(True)
        assert sidebar.is_split is True
        sidebar.set_split(False)
        assert sidebar.is_split is False

    def test_tab_changed_signal(self) -> None:
        sidebar = SidebarWidget()
        sidebar.add_tab("Tab A", QLabel("A"))
        sidebar.add_tab("Tab B", QLabel("B"))
        received: list[int] = []
        sidebar.tab_changed.connect(received.append)
        sidebar.set_current_index(1)
        assert received == [1]

    def test_lower_tab_independent(self) -> None:
        sidebar = SidebarWidget()
        sidebar.add_tab("Upper A", QLabel("UA"))
        sidebar.add_lower_tab("Lower A", QLabel("LA"))
        sidebar.add_lower_tab("Lower B", QLabel("LB"))
        assert sidebar.tab_count() == 1  # upper has 1
        assert sidebar.lower.tab_count() == 2
