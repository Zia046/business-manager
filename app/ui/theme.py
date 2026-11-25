"""Shared look: flat and clean. Dark navy navigation, white / light-grey pages, and one accent colour per kind of
information on the Home screen and the Dashboard (red, green, cyan, orange, purple, gold, teal)."""
PRIMARY = "#2563EB"        # buttons, selected items
PRIMARY_DARK = "#1D4ED8"   # hover
PRIMARY_PRESSED = "#1E40AF"
PRIMARY_TINT = "#DBEAFE"   # selected row, soft highlights
NAVY = "#14213D"           # toolbar, footer and other navigation areas (dark navy)
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

# Home screen + Dashboard accents (one meaning each)
C_NAVY = "#1B2A4A"         # main / neutral
C_RED = "#D32F3A"          # primary actions, important highlights, money owed
REMOVE, REMOVE_HOVER, REMOVE_PRESSED = "#CF3F49", "#B5333C", "#992A32"   # softer red for Remove buttons
C_GREEN = "#1E8E4E"        # positive money: sales, profit, completed
C_GOLD = "#D99A06"         # selected financial highlights: cash, net profit
C_CYAN = "#0E9FC0"         # information
C_PURPLE = "#5A3EC8"       # secondary information
C_ORANGE = "#E2620E"       # warnings, low stock
C_TEAL = "#149A80"         # stock, backup
ACCENTS = {"navy": C_NAVY, "red": C_RED, "green": C_GREEN, "gold": C_GOLD, "cyan": C_CYAN, "purple": C_PURPLE,
           "orange": C_ORANGE, "teal": C_TEAL}


def rgb(hex_color: str):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def blend(hex_color: str, other: str = "#FFFFFF", amount: float = 0.5) -> str:
    """Mix a colour with another one (white by default): amount 0 = the colour itself, 1 = the other."""
    a, b = rgb(hex_color), rgb(other)
    return "#%02X%02X%02X" % tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


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
/* Cell editors (Quantity, Price, Discount ... typed inside a table): a table row is only about 30 px high, so the
   editor must not carry the big padding of normal input boxes - that is what cut off the bottom of the digits. */
QAbstractItemView QLineEdit, QAbstractItemView QDoubleSpinBox, QAbstractItemView QSpinBox, QAbstractItemView QDateEdit,
QAbstractItemView QComboBox, QAbstractItemView QLineEdit:hover, QAbstractItemView QDoubleSpinBox:hover,
QAbstractItemView QSpinBox:hover, QAbstractItemView QLineEdit:focus, QAbstractItemView QDoubleSpinBox:focus,
QAbstractItemView QSpinBox:focus, QAbstractItemView QDateEdit:focus, QAbstractItemView QComboBox:focus {{
    padding: 0px 4px; margin: 0px; min-height: 0px; border: 1px solid {PRIMARY}; border-radius: 0px; }}
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
/* Remove buttons: one soft red everywhere, set apart from normal action buttons */
QPushButton#remove {{ background: {REMOVE}; color: #ffffff; border: 1px solid {REMOVE}; border-radius: 7px;
    padding: 6px 14px; font-weight: 600; }}
QPushButton#remove:hover {{ background: {REMOVE_HOVER}; border-color: {REMOVE_HOVER}; }}
QPushButton#remove:pressed {{ background: {REMOVE_PRESSED}; border-color: {REMOVE_PRESSED}; }}
QPushButton#remove:focus {{ border: 2px solid {NAVY}; padding: 5px 13px; }}
QPushButton#remove:disabled {{ background: #E9B4B8; border-color: #E9B4B8; }}
/* inside a table row (about 30 px high) the same button is compact, so the whole word fits */
QAbstractItemView QPushButton#remove {{ padding: 2px 8px; margin: 2px 4px; border-radius: 6px; font-size: 12px; }}
QAbstractItemView QPushButton#remove:focus {{ padding: 1px 7px; }}
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
QMenuBar::item:selected {{ background: {C_RED}; }}
QMenu {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 8px; }}
QMenu::item {{ background: transparent; padding: 6px 28px; }}
QMenu::item:selected {{ background: {PRIMARY_TINT}; color: {TEXT}; }}
QToolTip {{ background: {NAVY}; color: #ffffff; border: none; padding: 4px 8px; }}
"""
