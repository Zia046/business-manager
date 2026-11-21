"""Two-column data-entry window with a scrolling body and a fixed footer (Save / Cancel always visible).

Why: a form built as one long column makes the window as tall as all its rows together. Qt never makes a
window smaller than its layout needs, so on a normal laptop screen the Save button ended up below the
screen, and showing more rows (e.g. RAM / Storage when a phone category is chosen) made it grow further.

Here the rows live inside a scroll area, which needs almost no height of its own; the window therefore
always fits the screen, keeps its size and place while fields appear or hide, and only the middle part
scrolls. The footer with the buttons is outside the scroll area, so it can never be scrolled away.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QFormLayout, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy,
                               QVBoxLayout, QWidget)

from .theme import C_RED, LINE, NAVY, SURFACE

SCREEN_SHARE_W, SCREEN_SHARE_H = 0.92, 0.88


def section(text):
    """A small heading inside a column (spans the whole row of a QFormLayout)."""
    lab = QLabel(text)
    lab.setStyleSheet(f"font-size: 15px; font-weight: 800; color: {NAVY}; padding: 6px 0 2px 8px; "
                      f"border-left: 4px solid {C_RED};")
    return lab


def _form():
    f = QFormLayout()
    f.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    f.setHorizontalSpacing(12)
    f.setVerticalSpacing(10)
    return f


class TwoColumnForm:
    """Builds the layout of `dialog`:  [ scroll area: left form | right form, then full-width notes ]
                                          [ footer: message ......... extra buttons | Cancel | Save ]"""

    def __init__(self, dialog, width=940):
        self.dialog, self.width = dialog, width
        outer = QVBoxLayout(dialog)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        # normally never needed (labels wrap and fields shrink); on a very small screen a side scroll bar is
        # better than fields cut off at the edge
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setMinimumHeight(120)
        body = QWidget()
        body.setObjectName("formBody")
        self.scroll.setWidget(body)
        outer.addWidget(self.scroll, 1)

        page = QVBoxLayout(body)
        page.setContentsMargins(26, 18, 26, 12)
        page.setSpacing(12)
        cols = QHBoxLayout()
        cols.setSpacing(34)
        self.left, self.right = _form(), _form()
        for f in (self.left, self.right):
            box = QVBoxLayout()
            box.addLayout(f)
            box.addStretch(1)                       # both columns start at the top
            cols.addLayout(box, 1)
        page.addLayout(cols)
        self.notes = QVBoxLayout()                  # full-width hints under the two columns
        page.addLayout(self.notes)
        page.addStretch(1)

        footer = QFrame()
        footer.setObjectName("formFooter")
        footer.setStyleSheet(f"QFrame#formFooter {{ background: {SURFACE}; border-top: 1px solid {LINE}; }}")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(26, 12, 26, 14)
        fl.setSpacing(10)
        self.error = QLabel("")
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        self.error.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.left_buttons = QHBoxLayout()
        fl.addLayout(self.left_buttons)
        fl.addWidget(self.error, 1)
        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(10)
        fl.addLayout(self.buttons)
        outer.addWidget(footer)

    def note(self, widget):
        self.notes.addWidget(widget)
        return widget

    def button(self, text, slot, primary=False, left=False):
        b = QPushButton(text)
        b.setAutoDefault(False)
        if not primary:
            b.setObjectName("secondary")
        b.setMinimumWidth(110)
        b.clicked.connect(slot)
        (self.left_buttons if left else self.buttons).addWidget(b)
        return b

    def _wrap_labels(self):
        """Long labels may use two lines, so a narrow window keeps every field fully visible."""
        for form in (self.left, self.right):
            for i in range(form.rowCount()):
                item = form.itemAt(i, QFormLayout.LabelRole)
                lab = item.widget() if item else None
                if isinstance(lab, QLabel) and lab.text():
                    lab.setWordWrap(True)
                    lab.setMaximumWidth(210)
                    lab.setMinimumWidth(min(lab.sizeHint().width(), 120))
                field = form.itemAt(i, QFormLayout.FieldRole)
                w = field.widget() if field else None
                if w is not None and not isinstance(w, (QLabel, QPushButton)):
                    w.setMinimumWidth(150)
                    w.setSizePolicy(QSizePolicy.Expanding, w.sizePolicy().verticalPolicy())

    def fit(self):
        """A comfortable size that is never bigger than the screen, centred on it."""
        self._wrap_labels()
        d = self.dialog
        screen = d.screen() if d.screen() else QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen else None
        body = self.scroll.widget().sizeHint()
        want_w = max(self.width, body.width() + 30)
        want_h = body.height() + 90                 # + footer
        if area is not None:
            want_w = min(want_w, int(area.width() * SCREEN_SHARE_W))
            want_h = min(want_h, int(area.height() * SCREEN_SHARE_H))
        d.setMinimumSize(min(640, want_w), min(360, want_h))
        d.resize(want_w, want_h)
        if area is not None:
            d.move(area.x() + (area.width() - want_w) // 2, area.y() + max(0, (area.height() - want_h) // 2 - 20))
