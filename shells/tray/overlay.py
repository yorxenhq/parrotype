"""Status overlay pill: bottom-center, never steals focus, click-through.

States (per spec):
  LISTENING     rec dot + live waveform + mono timer + hint
  TRANSCRIBING  spinner + "распознаю…"
  STATUS        spinner + arbitrary text (model download progress etc.)
  INSERTED      check + text preview, flash 800ms then fade out
  ERROR         warning + message, stays until clicked (click = action or log)

Polish: soft drop shadow, fade+slide enter/exit (150-200ms ease-out),
attack/decay smoothed waveform, word-boundary preview trimming.
"""

from __future__ import annotations

import math
from collections import deque
from enum import Enum, auto
from typing import Callable

from PySide6.QtCore import QEasingCurve, QPoint, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from shells.tray import theme
from shells.tray.i18n import tr


class OverlayState(Enum):
    HIDDEN = auto()
    LISTENING = auto()
    TRANSCRIBING = auto()
    STATUS = auto()
    INSERTED = auto()
    ERROR = auto()


N_WAVE_BARS = 14
PREVIEW_MAX_CHARS = 36
MARGIN = 24                 # room for the drop shadow around the pill
SLIDE_PX = 14               # enter/exit vertical travel
ATTACK = 0.55               # waveform smoothing: rise speed (0..1 per tick)
DECAY = 0.86                # waveform smoothing: fall multiplier per tick


def _trim_preview(text: str, limit: int = PREVIEW_MAX_CHARS) -> str:
    """Cut at a word boundary and add an ellipsis — no mid-word chops."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[: limit + 1]
    space = cut.rfind(" ")
    if space > limit // 2:
        cut = cut[:space]
    else:
        cut = text[:limit]
    return cut.rstrip(" ,.;:—-") + "…"


class OverlayPill(QWidget):
    clicked_error = Signal()   # click in ERROR state with no custom action

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
        self.toggle_mode = False
        self.language_label = "AUTO"
        self.hint_text = ""
        self.preview_text = ""
        self.status_text = ""
        self.error_text = ""
        self.error_action: Callable[[], None] | None = None
        self._elapsed_ms = 0
        self._levels: deque[float] = deque([0.0] * N_WAVE_BARS, maxlen=N_WAVE_BARS)
        self._heights = [0.0] * N_WAVE_BARS      # smoothed display heights
        self._phase = 0.0

        self._font_ui = QFont(theme.FONT_UI, 10)
        if self._font_ui.family() != theme.FONT_UI:
            self._font_ui = QFont(theme.FONT_UI_FALLBACK, 10)
        self._font_mono = QFont(theme.FONT_MONO, 10)

        self._tick_timer = QTimer(self)
        self._tick_timer.setInterval(33)
        self._tick_timer.timeout.connect(self._on_tick)

        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(lambda: self._animate_out(theme.INSERTED_FADE_MS))

        # enter/exit animation: 0 = hidden, 1 = fully shown
        self._anim = QVariantAnimation(self)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self._anim.finished.connect(self._on_anim_finished)
        self._anim_t = 0.0
        self._exiting = False

        self.setFixedHeight(theme.PILL_HEIGHT + 2 * MARGIN)

    # -- public API ------------------------------------------------------

    def show_listening(self, language_label: str, toggle_mode: bool) -> None:
        self.language_label = language_label
        self.toggle_mode = toggle_mode
        self.hint_text = tr("pill.hotkey_to_stop") if toggle_mode else tr("pill.release_to_insert")
        self._elapsed_ms = 0
        self._levels.extend([0.0] * N_WAVE_BARS)
        self._heights = [0.0] * N_WAVE_BARS
        self._enter_state(OverlayState.LISTENING, click_through=True)

    def show_transcribing(self) -> None:
        self._enter_state(OverlayState.TRANSCRIBING, click_through=True)

    def show_status(self, text: str) -> None:
        """Spinner + arbitrary text (e.g. model download progress)."""
        self.status_text = text
        if self.state == OverlayState.STATUS:
            self._relayout()
            self.update()
        else:
            self._enter_state(OverlayState.STATUS, click_through=True)

    def show_inserted(self, text: str) -> None:
        self.preview_text = _trim_preview(text)
        self._enter_state(OverlayState.INSERTED, click_through=True)
        self._flash_timer.start(theme.INSERTED_FLASH_MS)

    def show_error(self, message: str, action: Callable[[], None] | None = None) -> None:
        self.error_text = message
        self.error_action = action
        self._enter_state(OverlayState.ERROR, click_through=False)

    def hide_pill(self, instant: bool = False) -> None:
        self._flash_timer.stop()
        if instant or self.state == OverlayState.HIDDEN or not self.isVisible():
            self._finish_hide()
        else:
            self._animate_out(150)

    def push_level(self, rms: float) -> None:
        """Feed microphone RMS (0..~0.5) for the live waveform."""
        self._levels.append(min(1.0, rms * 6.0))

    def elapsed_seconds(self) -> int:
        return self._elapsed_ms // 1000

    # -- state entry / animations -----------------------------------------

    def _enter_state(self, state: OverlayState, click_through: bool) -> None:
        self._flash_timer.stop()
        was_hidden = self.state == OverlayState.HIDDEN or not self.isVisible()
        self.state = state
        self._exiting = False
        self._set_click_through(click_through)
        self._relayout()
        if not self._tick_timer.isActive():
            self._tick_timer.start()
        if was_hidden:
            self._anim.stop()
            self._anim_t = 0.0
            self.setWindowOpacity(0.0)
            self.show()
            self._animate(0.0, 1.0, theme.ANIM_MS)
        else:
            self._anim.stop()
            self._anim_t = 1.0
            self.setWindowOpacity(1.0)
            self.update()

    def _animate(self, start: float, end: float, ms: int) -> None:
        self._anim.stop()
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.setDuration(ms)
        self._anim.start()

    def _animate_out(self, ms: int) -> None:
        if self._exiting:
            return
        self._exiting = True
        self._animate(self._anim_t, 0.0, ms)

    def _on_anim(self, value) -> None:  # noqa: ANN001
        self._anim_t = float(value)
        self.setWindowOpacity(self._anim_t)
        self.update()

    def _on_anim_finished(self) -> None:
        if self._exiting and self._anim_t <= 0.01:
            self._finish_hide()

    def _finish_hide(self) -> None:
        self._tick_timer.stop()
        self._anim.stop()
        self._exiting = False
        self.state = OverlayState.HIDDEN
        self.hide()

    # -- internals ---------------------------------------------------------

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
        self._phase = (self._phase + 0.055) % (2 * math.pi)
        if self.state == OverlayState.LISTENING:
            self._elapsed_ms += self._tick_timer.interval()
            targets = list(self._levels)
            for i in range(N_WAVE_BARS):
                target = targets[i]
                current = self._heights[i]
                if target > current:
                    current += (target - current) * ATTACK
                else:
                    current *= DECAY
                self._heights[i] = current
        self.update()

    def _timer_text(self) -> str:
        s = self.elapsed_seconds()
        return f"{s // 60}:{s % 60:02d}"

    def _content_width(self) -> int:
        fm_ui = QFontMetrics(self._font_ui)
        fm_mono = QFontMetrics(self._font_mono)
        if self.state == OverlayState.LISTENING:
            hint = f"{self.language_label} · {self.hint_text}"
            return (
                18 + 10 + 12
                + N_WAVE_BARS * 5 + 12
                + fm_mono.horizontalAdvance("00:00") + 14
                + fm_ui.horizontalAdvance(hint) + 18
            )
        if self.state == OverlayState.TRANSCRIBING:
            return 18 + 14 + 11 + fm_ui.horizontalAdvance(tr("pill.transcribing")) + 18
        if self.state == OverlayState.STATUS:
            return 18 + 14 + 11 + fm_ui.horizontalAdvance(self.status_text) + 18
        if self.state == OverlayState.INSERTED:
            return 18 + 14 + 11 + fm_ui.horizontalAdvance(f"«{self.preview_text}»") + 18
        if self.state == OverlayState.ERROR:
            return 18 + 14 + 11 + fm_ui.horizontalAdvance(self.error_text) + 18
        return 120

    def _relayout(self) -> None:
        width = max(140, self._content_width()) + 2 * MARGIN
        self.setFixedWidth(width)
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = geo.center().x() - width // 2
        y = geo.bottom() - theme.PILL_HEIGHT - 24 - MARGIN
        self.move(QPoint(x, y))

    # -- painting ---------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802, ANN001
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        slide = (1.0 - self._anim_t) * SLIDE_PX
        pill_x = MARGIN
        pill_y = MARGIN + slide
        pill_w = self.width() - 2 * MARGIN
        pill_h = theme.PILL_HEIGHT
        radius = pill_h / 2

        # soft drop shadow (layered rounded rects below the pill)
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(10, 0, -1):
            shadow = QColor(0, 0, 0)
            shadow.setAlphaF(0.028 * (11 - i) / 10 * self._anim_t)
            painter.setBrush(shadow)
            painter.drawRoundedRect(
                int(pill_x - i * 0.8), int(pill_y + 3 - i * 0.3),
                int(pill_w + i * 1.6), int(pill_h + i * 1.4),
                radius + i * 0.5, radius + i * 0.5,
            )

        bg = QColor(theme.BG_OVERLAY)
        bg.setAlpha(theme.BG_OVERLAY_ALPHA)
        painter.setBrush(bg)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(
            int(pill_x), int(pill_y), int(pill_w), int(pill_h), radius, radius
        )
        # hairline edge for definition on light desktops
        edge = QColor("#FFFFFF")
        edge.setAlphaF(0.06)
        painter.setPen(QPen(edge, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            int(pill_x), int(pill_y), int(pill_w), int(pill_h), radius, radius
        )

        x = pill_x + 18.0
        cy = pill_y + pill_h / 2
        if self.state == OverlayState.LISTENING:
            x = self._paint_rec_dot(painter, x, cy)
            x = self._paint_waveform(painter, x, cy)
            x = self._paint_timer(painter, x, cy)
            self._paint_text(
                painter, x, cy, f"{self.language_label} · {self.hint_text}", theme.MUTED
            )
        elif self.state == OverlayState.TRANSCRIBING:
            x = self._paint_spinner(painter, x, cy)
            self._paint_text(painter, x, cy, tr("pill.transcribing"), theme.TEXT)
        elif self.state == OverlayState.STATUS:
            x = self._paint_spinner(painter, x, cy)
            self._paint_text(painter, x, cy, self.status_text, theme.TEXT)
        elif self.state == OverlayState.INSERTED:
            x = self._paint_check(painter, x, cy)
            self._paint_text(painter, x, cy, f"«{self.preview_text}»", theme.TEXT)
        elif self.state == OverlayState.ERROR:
            x = self._paint_warning(painter, x, cy)
            self._paint_text(painter, x, cy, self.error_text, theme.TEXT)
        painter.end()

    def _paint_rec_dot(self, painter: QPainter, x: float, cy: float) -> float:
        color = QColor(theme.REC)
        if self.toggle_mode:
            color.setAlphaF(0.55 + 0.45 * (0.5 + math.sin(self._phase * 2.2) / 2))
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPoint(int(x + 5), int(cy)), 5, 5)
        return x + 10 + 12

    def _paint_waveform(self, painter: QPainter, x: float, cy: float) -> float:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.ACCENT))
        for i, level in enumerate(self._heights):
            h = max(3.0, level * 22.0)
            painter.drawRoundedRect(
                int(x + i * 5), int(cy - h / 2), 3, int(h), 1.5, 1.5
            )
        return x + N_WAVE_BARS * 5 + 12

    def _paint_timer(self, painter: QPainter, x: float, cy: float) -> float:
        long_rec = self.elapsed_seconds() >= theme.LONG_RECORDING_S
        painter.setFont(self._font_mono)
        painter.setPen(QColor(theme.ACCENT if long_rec else theme.TEXT))
        fm = QFontMetrics(self._font_mono)
        painter.drawText(int(x), int(cy + fm.ascent() / 2 - 1), self._timer_text())
        return x + fm.horizontalAdvance("00:00") + 14

    def _paint_spinner(self, painter: QPainter, x: float, cy: float) -> float:
        pen = QPen(QColor(theme.ACCENT), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        start_angle = int(-self._phase * 1200)
        painter.drawArc(int(x), int(cy - 7), 14, 14, start_angle, 110 * 16)
        return x + 14 + 11

    def _paint_check(self, painter: QPainter, x: float, cy: float) -> float:
        pen = QPen(QColor(theme.ACCENT), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(int(x), int(cy + 1), int(x + 4), int(cy + 5))
        painter.drawLine(int(x + 4), int(cy + 5), int(x + 12), int(cy - 5))
        return x + 14 + 11

    def _paint_warning(self, painter: QPainter, x: float, cy: float) -> float:
        painter.setFont(self._font_ui)
        painter.setPen(QColor("#FFB020"))
        painter.drawText(int(x), int(cy + 5), "⚠")
        return x + 14 + 11

    def _paint_text(
        self, painter: QPainter, x: float, cy: float, text: str, color: str
    ) -> None:
        painter.setFont(self._font_ui)
        painter.setPen(QColor(color))
        fm = QFontMetrics(self._font_ui)
        painter.drawText(int(x), int(cy + fm.ascent() / 2 - 1), text)

    def mousePressEvent(self, event) -> None:  # noqa: N802, ANN001
        if self.state == OverlayState.ERROR:
            action = self.error_action
            self.hide_pill()
            if action is not None:
                action()
            else:
                self.clicked_error.emit()
