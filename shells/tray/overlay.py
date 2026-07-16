"""Status overlay pill: bottom-center, never steals focus, click-through.

States (per spec):
  LISTENING     rec dot + live waveform + mono timer + hint
  TRANSCRIBING  spinner + "распознаю…"
  INSERTED      check + text preview, flash 800ms then fade out
  ERROR         warning + message, stays until clicked (click opens log)
"""

from __future__ import annotations

import math
from collections import deque
from enum import Enum, auto

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from shells.tray import theme


class OverlayState(Enum):
    HIDDEN = auto()
    LISTENING = auto()
    TRANSCRIBING = auto()
    INSERTED = auto()
    ERROR = auto()


N_WAVE_BARS = 14
PREVIEW_MAX_CHARS = 32


class OverlayPill(QWidget):
    clicked_error = Signal()   # user clicked the pill in ERROR state -> open log

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self.state = OverlayState.HIDDEN
        self.toggle_mode = False           # pulsing rec dot in toggle mode
        self.language_label = "AUTO"
        self.hint_text = "отпусти — вставлю"
        self.preview_text = ""
        self.error_text = ""
        self._elapsed_ms = 0
        self._levels: deque[float] = deque([0.0] * N_WAVE_BARS, maxlen=N_WAVE_BARS)
        self._phase = 0.0                  # spinner / pulse animation phase
        self._opacity = 1.0

        self._font_ui = QFont(theme.FONT_UI, 10)
        if self._font_ui.family() != theme.FONT_UI:
            self._font_ui = QFont(theme.FONT_UI_FALLBACK, 10)
        self._font_mono = QFont(theme.FONT_MONO, 10)

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(50)
        self._tick_timer.timeout.connect(self._on_tick)

        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._start_fade)

        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(40)
        self._fade_timer.timeout.connect(self._on_fade)

        self.setFixedHeight(theme.PILL_HEIGHT)

    # -- public API ------------------------------------------------------

    def show_listening(self, language_label: str, toggle_mode: bool) -> None:
        self._reset_timers()
        self.state = OverlayState.LISTENING
        self.language_label = language_label
        self.toggle_mode = toggle_mode
        self.hint_text = "хоткей — стоп" if toggle_mode else "отпусти — вставлю"
        self._elapsed_ms = 0
        self._levels.extend([0.0] * N_WAVE_BARS)
        self._opacity = 1.0
        self._set_click_through(True)
        self._tick_timer.start()
        self._relayout()
        self.show()

    def show_transcribing(self) -> None:
        self._reset_timers()
        self.state = OverlayState.TRANSCRIBING
        self._opacity = 1.0
        self._set_click_through(True)
        self._tick_timer.start()
        self._relayout()
        self.show()

    def show_inserted(self, text: str) -> None:
        self._reset_timers()
        self.state = OverlayState.INSERTED
        preview = text.strip().replace("\n", " ")
        if len(preview) > PREVIEW_MAX_CHARS:
            preview = preview[: PREVIEW_MAX_CHARS - 1] + "…"
        self.preview_text = preview
        self._opacity = 1.0
        self._set_click_through(True)
        self._relayout()
        self.show()
        self._flash_timer.start(theme.INSERTED_FLASH_MS)

    def show_error(self, message: str) -> None:
        self._reset_timers()
        self.state = OverlayState.ERROR
        self.error_text = message
        self._opacity = 1.0
        self._set_click_through(False)     # error pill is clickable (opens log)
        self._relayout()
        self.show()

    def hide_pill(self) -> None:
        self._reset_timers()
        self.state = OverlayState.HIDDEN
        self.hide()

    def push_level(self, rms: float) -> None:
        """Feed microphone RMS (0..~0.5) for the live waveform."""
        self._levels.append(min(1.0, rms * 6.0))
        if self.state == OverlayState.LISTENING:
            self.update()

    # -- internals ---------------------------------------------------------

    def _reset_timers(self) -> None:
        self._tick_timer.stop()
        self._flash_timer.stop()
        self._fade_timer.stop()

    def _set_click_through(self, enabled: bool) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, enabled)
        flags = self.windowFlags()
        if enabled:
            flags |= Qt.WindowType.WindowTransparentForInput
        else:
            flags &= ~Qt.WindowType.WindowTransparentForInput
        visible = self.isVisible()
        self.setWindowFlags(flags)
        if visible:
            self.show()

    def _on_tick(self) -> None:
        self._phase = (self._phase + 0.08) % (2 * math.pi)
        if self.state == OverlayState.LISTENING:
            self._elapsed_ms += self._tick_timer.interval()
        self.update()

    def _start_fade(self) -> None:
        self._fade_timer.start()

    def _on_fade(self) -> None:
        self._opacity -= 40 / theme.INSERTED_FADE_MS
        if self._opacity <= 0:
            self.hide_pill()
        else:
            self.setWindowOpacity(self._opacity)
            self.update()

    def elapsed_seconds(self) -> int:
        return self._elapsed_ms // 1000

    def _timer_text(self) -> str:
        s = self.elapsed_seconds()
        return f"{s // 60}:{s % 60:02d}"

    def _content_width(self) -> int:
        fm_ui = QFontMetrics(self._font_ui)
        fm_mono = QFontMetrics(self._font_mono)
        if self.state == OverlayState.LISTENING:
            hint = f"{self.language_label} · {self.hint_text}"
            return (
                16 + 10 + 10                       # pad + rec dot
                + N_WAVE_BARS * 5 + 10             # waveform
                + fm_mono.horizontalAdvance("00:00") + 12
                + fm_ui.horizontalAdvance(hint) + 16
            )
        if self.state == OverlayState.TRANSCRIBING:
            return 16 + 14 + 10 + QFontMetrics(self._font_ui).horizontalAdvance("распознаю…") + 16
        if self.state == OverlayState.INSERTED:
            return 16 + 14 + 10 + fm_ui.horizontalAdvance(f"«{self.preview_text}»") + 16
        if self.state == OverlayState.ERROR:
            return 16 + 14 + 10 + fm_ui.horizontalAdvance(self.error_text) + 16
        return 120

    def _relayout(self) -> None:
        width = max(140, self._content_width())
        self.setFixedWidth(width)
        self.setWindowOpacity(1.0)
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = geo.center().x() - width // 2
        y = geo.bottom() - theme.PILL_HEIGHT - 24    # above taskbar
        self.move(QPoint(x, y))

    # -- painting ---------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802, ANN001
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg = QColor(theme.BG_OVERLAY)
        bg.setAlpha(theme.BG_OVERLAY_ALPHA)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        radius = self.height() / 2
        painter.drawRoundedRect(self.rect(), radius, radius)

        x = 16.0
        cy = self.height() / 2
        if self.state == OverlayState.LISTENING:
            x = self._paint_rec_dot(painter, x, cy)
            x = self._paint_waveform(painter, x, cy)
            x = self._paint_timer(painter, x, cy)
            self._paint_text(
                painter, x, cy,
                f"{self.language_label} · {self.hint_text}", theme.MUTED,
            )
        elif self.state == OverlayState.TRANSCRIBING:
            x = self._paint_spinner(painter, x, cy)
            self._paint_text(painter, x, cy, "распознаю…", theme.TEXT)
        elif self.state == OverlayState.INSERTED:
            x = self._paint_check(painter, x, cy)
            self._paint_text(painter, x, cy, f"«{self.preview_text}»", theme.TEXT)
        elif self.state == OverlayState.ERROR:
            x = self._paint_warning(painter, x, cy)
            self._paint_text(painter, x, cy, self.error_text, theme.TEXT)
        painter.end()

    def _paint_rec_dot(self, painter: QPainter, x: float, cy: float) -> float:
        color = QColor(theme.REC)
        if self.toggle_mode:  # pulsing in toggle mode
            color.setAlphaF(0.5 + 0.5 * (0.5 + math.sin(self._phase * 2) / 2))
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPoint(int(x + 5), int(cy)), 5, 5)
        return x + 10 + 10

    def _paint_waveform(self, painter: QPainter, x: float, cy: float) -> float:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.ACCENT))
        for i, level in enumerate(self._levels):
            h = max(3.0, level * 22.0)
            painter.drawRoundedRect(
                int(x + i * 5), int(cy - h / 2), 3, int(h), 1.5, 1.5
            )
        return x + N_WAVE_BARS * 5 + 10

    def _paint_timer(self, painter: QPainter, x: float, cy: float) -> float:
        long_rec = self.elapsed_seconds() >= theme.LONG_RECORDING_S
        painter.setFont(self._font_mono)
        painter.setPen(QColor(theme.ACCENT if long_rec else theme.TEXT))
        text = self._timer_text()
        fm = QFontMetrics(self._font_mono)
        painter.drawText(
            int(x), int(cy + fm.ascent() / 2 - 1), text
        )
        return x + fm.horizontalAdvance("00:00") + 12

    def _paint_spinner(self, painter: QPainter, x: float, cy: float) -> float:
        pen = QPen(QColor(theme.ACCENT), 2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        start_angle = int(-self._phase * 916)      # rotate
        painter.drawArc(int(x), int(cy - 7), 14, 14, start_angle, 120 * 16)
        return x + 14 + 10

    def _paint_check(self, painter: QPainter, x: float, cy: float) -> float:
        pen = QPen(QColor(theme.ACCENT), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawLine(int(x), int(cy + 1), int(x + 4), int(cy + 5))
        painter.drawLine(int(x + 4), int(cy + 5), int(x + 12), int(cy - 5))
        return x + 14 + 10

    def _paint_warning(self, painter: QPainter, x: float, cy: float) -> float:
        painter.setFont(self._font_ui)
        painter.setPen(QColor("#FFB020"))
        painter.drawText(int(x), int(cy + 5), "⚠")
        return x + 14 + 10

    def _paint_text(
        self, painter: QPainter, x: float, cy: float, text: str, color: str
    ) -> None:
        painter.setFont(self._font_ui)
        painter.setPen(QColor(color))
        fm = QFontMetrics(self._font_ui)
        painter.drawText(int(x), int(cy + fm.ascent() / 2 - 1), text)

    def mousePressEvent(self, event) -> None:  # noqa: N802, ANN001
        if self.state == OverlayState.ERROR:
            self.clicked_error.emit()
            self.hide_pill()
