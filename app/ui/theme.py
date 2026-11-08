"""Shared look: flat, minimal, five-colour palette (warm ivory, coral red, mint green, soft yellow, charcoal)."""
PRIMARY = "#2563EB"        # buttons, selected items
PRIMARY_DARK = "#1D4ED8"   # hover
PRIMARY_PRESSED = "#1E40AF"
PRIMARY_TINT = "#DBEAFE"   # selected row, soft highlights
NAVY = "#1E293B"           # toolbar and footer
BG = "#F3F5F9"             # page background
SURFACE = "#FFFFFF"        # cards, inputs, tables
LINE = "#DDE3EC"           # thin borders
LINE_DARK = "#C5CFDD"
TEXT = "#1F2937"
MUTED = "#64748B"
ROW_ALT = "#F8FAFC"
HEAD_BG = "#E8EDF4"        # table headers
SUCCESS = "#16A34A"
SUCCESS_BG = "#DCFCE7"     # profit, completed
SUCCESS_TEXT = "#166534"
WARN_BG = "#FEF3C7"        # pending, warnings
WARN_TEXT = "#92400E"
ERROR = "#DC2626"

# names other modules already import
BG_DARK = HEAD_BG
ACCENT, ACCENT_DARK = PRIMARY, PRIMARY_DARK
BORDER, WINE = LINE, TEXT
HOME_BTN_BG, HOME_BTN_BORDER, HOME_BTN_HOVER, HOME_BTN_TEXT = SURFACE, LINE, "#EFF6FF", TEXT

STYLESHEET = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-family: 'Segoe UI', 'Noto Nastaliq Urdu', Arial; font-size: 14px; }}
QDialog, QMainWindow {{ background: {BG}; }}
QLabel {{ background: transparent; }}
QCheckBox, QRadioButton {{ background: transparent; }}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit {{
    background: {SURFACE}; border: 1px solid {LINE_DARK}; border-radius: 8px; padding: 6px 10px;
    selection-background-color: {PRIMARY_TINT}; selection-color: {TEXT}; }}
QLineEdit:hover, QComboBox:hover, QDoubleSpinBox:hover, QSpinBox:hover, QDateEdit:hover {{ border: 1px solid {MUTED}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus,
QDateEdit:focus {{ border: 2px solid {PRIMARY}; padding: 5px 9px; }}
QComboBox QAbstractItemView {{ background: {SURFACE}; border: 1px solid {LINE}; selection-background-color: {PRIMARY_TINT};
    selection-color: {TEXT}; outline: none; }}
QTableWidget, QTableView, QListWidget {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 8px;
    gridline-color: {LINE}; alternate-background-color: {ROW_ALT}; selection-background-color: {PRIMARY_TINT};
    selection-color: {TEXT}; }}
QTableWidget::item, QTableView::item {{ padding: 4px 6px; }}
QHeaderView::section {{ background: {HEAD_BG}; color: {TEXT}; font-weight: 700; padding: 8px 8px; border: none;
    border-right: 1px solid {LINE}; border-bottom: 1px solid {LINE_DARK}; }}
QListWidget::item {{ padding: 5px 8px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {PRIMARY_TINT}; color: {TEXT}; }}
QPushButton {{ background: {PRIMARY}; color: #ffffff; border: none; border-radius: 8px; padding: 8px 20px; font-weight: 600; }}
QPushButton:hover {{ background: {PRIMARY_DARK}; }}
QPushButton:pressed {{ background: {PRIMARY_PRESSED}; }}
QPushButton:disabled {{ background: #A9BFEF; color: #ffffff; }}
QPushButton:focus {{ border: 2px solid {NAVY}; padding: 6px 18px; }}
QPushButton#secondary {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {LINE_DARK}; }}
QPushButton#secondary:hover {{ background: {HEAD_BG}; }}
QPushButton#secondary:pressed {{ background: {LINE}; }}
QLabel#title {{ font-size: 24px; font-weight: 700; color: {TEXT}; }}
QLabel#subtitle {{ color: {MUTED}; }}
QLabel#error {{ color: {ERROR}; font-weight: 600; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {LINE_DARK}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {MUTED}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {LINE_DARK}; border-radius: 5px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {MUTED}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QTabBar::tab {{ background: {HEAD_BG}; color: {TEXT}; padding: 7px 16px; border-top-left-radius: 8px;
    border-top-right-radius: 8px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: {PRIMARY}; color: #ffffff; font-weight: 700; }}
QMenuBar {{ background: {NAVY}; color: #ffffff; }}
QMenuBar::item {{ background: transparent; color: #ffffff; padding: 8px 14px; }}
QMenuBar::item:selected {{ background: {PRIMARY}; }}
QMenu {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 8px; }}
QMenu::item {{ background: transparent; padding: 6px 28px; }}
QMenu::item:selected {{ background: {PRIMARY_TINT}; color: {TEXT}; }}
QToolTip {{ background: {NAVY}; color: #ffffff; border: none; padding: 4px 8px; }}
"""
