"""Video overlay settings section for the visual settings panel."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wavern.gui.drag_spinbox import DragSpinBox
from wavern.gui.help_button import make_help_button
from wavern.gui.no_scroll_combo import NoScrollComboBox
from wavern.presets.schema import OverlayBlendMode, Preset, VideoOverlayConfig


class OverlaySection(QWidget):
    """Editable video overlay configuration widget."""

    overlay_changed = Signal()
    preview_flags_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._preset: Preset | None = None
        self._rebuilding = False

    def build(self, preset: Preset) -> None:
        """Clear and rebuild the overlay form from the preset.

        Args:
            preset: The active preset whose video_overlay to display.
        """
        self._rebuilding = True
        self._preset = preset

        # Remove all existing child widgets.
        while self._layout.count():
            item = self._layout.takeAt(0)
            assert item is not None
            w = item.widget()
            if w is not None:
                w.deleteLater()
            else:
                sub = item.layout()
                if sub is not None and isinstance(sub, (QVBoxLayout, QHBoxLayout)):
                    _clear_layout(sub)

        content = QWidget()
        form = QFormLayout(content)
        form.setContentsMargins(4, 0, 4, 0)

        overlay = preset.video_overlay

        self._overlay_enabled = QCheckBox()
        self._overlay_enabled.setChecked(overlay.enabled)
        self._overlay_enabled.toggled.connect(self._on_overlay_changed)
        wrapped_enabled = self._wrap_with_buttons(
            self._overlay_enabled,
            description="Enable video overlay compositing on top of the visualization.",
            default_callback=lambda: self._overlay_enabled.setChecked(False),
            default_label="off",
        )
        form.addRow("Enabled:", wrapped_enabled)

        self._overlay_disable_preview = QCheckBox()
        self._overlay_disable_preview.setChecked(False)
        self._overlay_disable_preview.toggled.connect(
            self._on_preview_flags_changed
        )
        wrapped_disable_preview = self._wrap_with_buttons(
            self._overlay_disable_preview,
            description=(
                "Skip rendering the video overlay in the preview.\n"
                "The overlay will still be included in the final export.\n"
                "Useful to save resources during editing."
            ),
            default_callback=lambda: self._overlay_disable_preview.setChecked(
                False
            ),
            default_label="off",
        )
        form.addRow("Disable Preview:", wrapped_disable_preview)

        self._overlay_video_label = QLabel(
            overlay.video_path or "No video selected"
        )
        self._overlay_video_label.setWordWrap(True)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_overlay_video_pick)
        row = QHBoxLayout()
        row.addWidget(self._overlay_video_label, stretch=1)
        row.addWidget(browse_btn)
        form.addRow("Video:", row)

        blend_desc = (
            "Controls how the overlay video blends with the scene.\n\n"
            "- alpha: standard transparency blending\n"
            "- additive: bright areas glow, black becomes transparent\n"
            "  (best for particles on black background)\n"
            "- screen: like additive but prevents over-exposure"
        )
        self._overlay_blend_combo = NoScrollComboBox()
        self._overlay_blend_combo.blockSignals(True)
        for mode in OverlayBlendMode:
            self._overlay_blend_combo.addItem(mode.value, mode)
        idx = self._overlay_blend_combo.findData(overlay.blend_mode)
        if idx >= 0:
            self._overlay_blend_combo.setCurrentIndex(idx)
        self._overlay_blend_combo.blockSignals(False)
        self._overlay_blend_combo.currentIndexChanged.connect(
            self._on_overlay_changed
        )
        wrapped_blend = self._wrap_with_buttons(
            self._overlay_blend_combo,
            description=blend_desc,
            default_callback=lambda: self._overlay_blend_combo.setCurrentIndex(
                self._overlay_blend_combo.findData(OverlayBlendMode.ADDITIVE)
            ),
            default_label="additive",
        )
        form.addRow("Blend:", wrapped_blend)

        self._overlay_opacity = DragSpinBox(
            minimum=0.0,
            maximum=1.0,
            step=0.05,
            decimals=2,
            description="Controls the transparency of the video overlay.",
            default_value=1.0,
        )
        self._overlay_opacity.setValue(overlay.opacity)
        self._overlay_opacity.valueChanged.connect(self._on_overlay_changed)
        form.addRow("Opacity:", self._overlay_opacity)

        self._overlay_rotation = DragSpinBox(
            minimum=0.0,
            maximum=360.0,
            step=1.0,
            decimals=0,
            description=(
                "Rotation angle in degrees applied to the overlay video."
            ),
            default_value=0.0,
        )
        self._overlay_rotation.setValue(overlay.rotation)
        self._overlay_rotation.valueChanged.connect(self._on_overlay_changed)
        form.addRow("Rotation:", self._overlay_rotation)

        self._overlay_mirror_x = QCheckBox()
        self._overlay_mirror_x.setChecked(overlay.mirror_x)
        self._overlay_mirror_x.toggled.connect(self._on_overlay_changed)
        wrapped_mirror_x = self._wrap_with_buttons(
            self._overlay_mirror_x,
            description="Mirror the overlay video horizontally.",
            default_callback=lambda: self._overlay_mirror_x.setChecked(False),
            default_label="off",
        )
        form.addRow("Mirror X:", wrapped_mirror_x)

        self._overlay_mirror_y = QCheckBox()
        self._overlay_mirror_y.setChecked(overlay.mirror_y)
        self._overlay_mirror_y.toggled.connect(self._on_overlay_changed)
        wrapped_mirror_y = self._wrap_with_buttons(
            self._overlay_mirror_y,
            description="Mirror the overlay video vertically.",
            default_callback=lambda: self._overlay_mirror_y.setChecked(False),
            default_label="off",
        )
        form.addRow("Mirror Y:", wrapped_mirror_y)

        self._layout.addWidget(content)
        self._rebuilding = False

    def update_values(self, overlay: VideoOverlayConfig) -> None:
        """Update overlay widgets in-place without rebuilding.

        Args:
            overlay: The current overlay configuration to reflect.
        """
        if not hasattr(self, "_overlay_enabled"):
            return
        self._rebuilding = True
        self._overlay_enabled.blockSignals(True)
        self._overlay_enabled.setChecked(overlay.enabled)
        self._overlay_enabled.blockSignals(False)
        self._overlay_video_label.setText(
            overlay.video_path or "No video selected"
        )
        self._overlay_blend_combo.blockSignals(True)
        idx = self._overlay_blend_combo.findData(overlay.blend_mode)
        if idx >= 0:
            self._overlay_blend_combo.setCurrentIndex(idx)
        self._overlay_blend_combo.blockSignals(False)
        self._overlay_opacity.blockSignals(True)
        self._overlay_opacity.setValue(overlay.opacity)
        self._overlay_opacity.blockSignals(False)
        self._overlay_rotation.blockSignals(True)
        self._overlay_rotation.setValue(overlay.rotation)
        self._overlay_rotation.blockSignals(False)
        self._overlay_mirror_x.blockSignals(True)
        self._overlay_mirror_x.setChecked(overlay.mirror_x)
        self._overlay_mirror_x.blockSignals(False)
        self._overlay_mirror_y.blockSignals(True)
        self._overlay_mirror_y.setChecked(overlay.mirror_y)
        self._overlay_mirror_y.blockSignals(False)
        self._rebuilding = False

    def _on_overlay_changed(self) -> None:
        if self._preset is None or self._rebuilding:
            return
        self._preset.video_overlay = VideoOverlayConfig(
            enabled=self._overlay_enabled.isChecked(),
            video_path=self._preset.video_overlay.video_path,
            blend_mode=self._overlay_blend_combo.currentData(),
            opacity=self._overlay_opacity.value(),
            rotation=self._overlay_rotation.value(),
            mirror_x=self._overlay_mirror_x.isChecked(),
            mirror_y=self._overlay_mirror_y.isChecked(),
        )
        self.overlay_changed.emit()

    def _on_overlay_video_pick(self) -> None:
        if self._preset is None:
            return
        default_dir = str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Overlay Video",
            default_dir,
            "Video Files (*.mp4 *.webm *.mkv *.avi *.mov)",
        )
        if path:
            self._preset.video_overlay.video_path = path
            self._overlay_video_label.setText(path)
            self._on_overlay_changed()

    def _on_preview_flags_changed(self) -> None:
        skip_overlay = (
            hasattr(self, "_overlay_disable_preview")
            and self._overlay_disable_preview.isChecked()
        )
        self.preview_flags_changed.emit(skip_overlay)

    def _wrap_with_buttons(
        self,
        widget: QWidget,
        description: str = "",
        default_callback: Callable[[], None] | None = None,
        default_label: str = "",
    ) -> QWidget:
        """Wrap a widget with optional reset button and help icon.

        Args:
            widget: The input widget to wrap.
            description: Tooltip text for the help button.
            default_callback: Called when the reset button is clicked.
            default_label: Short label shown in the reset tooltip.

        Returns:
            A container widget with the input, reset, and help controls.
        """
        if not description and default_callback is None:
            return widget
        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        row.addWidget(widget, stretch=1)
        if default_callback is not None:
            reset_btn = QPushButton("\u21BA")
            reset_btn.setObjectName("ResetButton")
            reset_btn.setFixedSize(20, 20)
            tip = (
                f"Reset to default ({default_label})"
                if default_label
                else "Reset to default"
            )
            reset_btn.setToolTip(tip)
            reset_btn.clicked.connect(default_callback)
            row.addWidget(reset_btn)
        if description:
            row.addWidget(make_help_button(description))
        return container


def _clear_layout(layout: QVBoxLayout | QHBoxLayout) -> None:
    """Recursively remove all items from a layout and delete their widgets."""
    while layout.count():
        item = layout.takeAt(0)
        assert item is not None
        w = item.widget()
        if w is not None:
            w.deleteLater()
        else:
            sub = item.layout()
            if sub is not None and isinstance(sub, (QVBoxLayout, QHBoxLayout)):
                _clear_layout(sub)
