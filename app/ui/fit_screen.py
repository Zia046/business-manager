"""Every window opens inside the screen: a normal-sized window, never taller or wider than the monitor."""
from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDialog, QMainWindow


class FitToScreen(QObject):
    SHARE = 0.92          # a window uses at most this part of the free screen area

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Show and isinstance(obj, QDialog) and obj.isWindow():
            self.fit(obj)
        return False

    @classmethod
    def fit(cls, win):
        if isinstance(win, QMainWindow):
            return
        screen = win.screen() or QGuiApplication.primaryScreen()
        if not screen:
            return
        area = screen.availableGeometry()
        w = min(win.width(), int(area.width() * cls.SHARE))
        h = min(win.height(), int(area.height() * cls.SHARE))
        if (w, h) != (win.width(), win.height()):
            win.resize(w, h)
        g = win.frameGeometry()
        x = min(max(g.x(), area.x()), max(area.x(), area.right() - g.width()))
        y = min(max(g.y(), area.y()), max(area.y(), area.bottom() - g.height()))
        if (x, y) != (g.x(), g.y()):
            win.move(x, y)
