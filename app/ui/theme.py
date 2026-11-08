"""Shared look: glossy glass style in soft peach / blush / warm white / coral (colours only, nothing else changes)."""
BG = "#fff5f0"          # warm white page background
BG_DARK = "#fbe1d8"     # menu bar / table headers
ACCENT = "#e07a67"      # coral
ACCENT_DARK = "#cf5f4c"
TEXT = "#3b2a28"
MUTED = "#8a6f68"
ERROR = "#d92d20"
BORDER = "#efd2c7"
WINE = "#5a2d2d"        # headings

# the 8 big home-screen buttons (the real colours are in main_window.CARD_COLORS)
HOME_BTN_BG = "#fff1ec"
HOME_BTN_BORDER = "#f3b9a8"
HOME_BTN_HOVER = "#fddccf"
HOME_BTN_TEXT = "#6d2f27"

STYLESHEET = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-family: 'Segoe UI', 'Noto Nastaliq Urdu', Arial; font-size: 14px; }}
QDialog, QMainWindow {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #fffaf7,stop:0.6 #fff1ea,stop:1 #fde6dd); }}
QLabel {{ background: transparent; }}
QCheckBox, QRadioButton {{ background: transparent; }}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit {{
    background: rgba(255,255,255,0.92); border: 1px solid {BORDER}; border-radius: 10px; padding: 6px 11px;
    selection-background-color: #f9c9bb; selection-color: {TEXT}; }}
QLineEdit:hover, QComboBox:hover, QDoubleSpinBox:hover, QSpinBox:hover, QDateEdit:hover {{ border: 1px solid #e6b3a4; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus,
QDateEdit:focus {{ border: 2px solid {ACCENT}; padding: 5px 10px; }}
QComboBox QAbstractItemView {{ background: #ffffff; border: 1px solid {BORDER}; selection-background-color: #fbd9cf;
    selection-color: {TEXT}; outline: none; }}
QTableWidget, QTableView, QListWidget {{ background: rgba(255,255,255,0.92); border: 1px solid {BORDER}; border-radius: 12px;
    gridline-color: #f6e6df; alternate-background-color: #fffaf7; selection-background-color: #fbd5c9;
    selection-color: {TEXT}; }}
QTableWidget::item, QTableView::item {{ padding: 4px 6px; }}
QHeaderView::section {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #fdeee8,stop:1 #f9d9ce); color: {WINE};
    font-weight: 700; padding: 7px 8px; border: none; border-right: 1px solid #f3d3c8; border-bottom: 1px solid {BORDER}; }}
QListWidget::item {{ padding: 5px 8px; border-radius: 6px; }}
QListWidget::item:selected {{ background: #fbd5c9; color: {TEXT}; }}
QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #f4977f,stop:0.5 #e57b66,stop:1 #d96450); color: #fff;
    border: 1px solid #cf5f4c; border-top: 1px solid #f9bdad; border-radius: 11px; padding: 8px 20px; font-weight: 600; }}
QPushButton:hover {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #f7a690,stop:0.5 #ea8873,stop:1 #de6d59); }}
QPushButton:pressed {{ background: #cf5f4c; border-top: 1px solid #cf5f4c; }}
QPushButton:disabled {{ background: #f1c9bf; border: 1px solid #ebbcaf; color: #fff7f4; }}
QPushButton:focus {{ border: 2px solid #f6a899; }}
QPushButton#secondary {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffffff,stop:1 #fbe3da); color: {WINE};
    border: 1px solid #efc4b6; border-top: 1px solid #ffffff; }}
QPushButton#secondary:hover {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #ffffff,stop:1 #f9d6ca); }}
QPushButton#secondary:pressed {{ background: #f6cbbd; }}
QLabel#title {{ font-size: 24px; font-weight: 700; letter-spacing: 1px; color: {WINE}; }}
QLabel#subtitle {{ color: {MUTED}; }}
QLabel#error {{ color: {ERROR}; font-weight: 600; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #f0c4b6; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #e6a999; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #f0c4b6; border-radius: 5px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: #e6a999; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QTabBar::tab {{ background: #fbe1d8; color: {WINE}; padding: 7px 16px; border-top-left-radius: 10px;
    border-top-right-radius: 10px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: #ffffff; font-weight: 700; }}
QMenuBar {{ background: {BG_DARK}; }}
QMenuBar::item {{ background: transparent; padding: 6px 12px; }}
QMenuBar::item:selected {{ background: #f6c9bc; }}
QMenu {{ background: #ffffff; border: 1px solid {BORDER}; border-radius: 8px; }}
QMenu::item {{ background: transparent; padding: 6px 28px; }}
QMenu::item:selected {{ background: #fbd9cf; color: {TEXT}; }}
QToolTip {{ background: #ffffff; color: {TEXT}; border: 1px solid {BORDER}; }}
"""
