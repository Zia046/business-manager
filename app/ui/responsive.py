"""Pieces that make pages fit the window: no horizontal scrolling, content re-flows when the size changes."""
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QSizePolicy


class FitWidthScrollArea(QScrollArea):
    """Scrolls up/down only. Tells the page its usable width whenever the window is maximised, restored or resized."""
    widthChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.widthChanged.emit(self.viewport().width())


def reflow(grid, widgets, cols, max_cols=8):
    """Put the widgets into the grid again with `cols` equal columns."""
    while grid.count():
        grid.takeAt(0)
    for c in range(max_cols):
        grid.setColumnStretch(c, 0)
    for i, w in enumerate(widgets):
        grid.addWidget(w, i // cols, i % cols)
    for c in range(cols):
        grid.setColumnStretch(c, 1)


class ChartLabel(QLabel):
    """A chart picture that is drawn again at the width it really has, so it never forces the page wider."""

    def __init__(self, ratio=0.62, parent=None):
        super().__init__(parent)
        self.ratio = ratio
        self._render_fn = None
        self._last = None
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.draw)

    def set_source(self, render_fn):
        """render_fn((width, height)) -> PNG bytes."""
        self._render_fn = render_fn
        self._last = None
        self.draw()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._timer.start(80)                          # wait until the user stops dragging

    def draw(self):
        if self._render_fn is None:
            return
        w = max(220, self.width())
        h = int(w * self.ratio)
        if (w, h) == self._last:
            return
        self._last = (w, h)
        pix = QPixmap()
        pix.loadFromData(self._render_fn((w, h)), "PNG")
        self.setFixedHeight(h)
        self.setPixmap(pix)
