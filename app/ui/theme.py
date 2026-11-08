"""Shared look: flat, minimal, five-colour palette (warm ivory, coral red, mint green, soft yellow, charcoal)."""
IVORY = "#F7EFE8"       # page background
CORAL = "#FC6454"       # primary actions, selected items
CORAL_DARK = "#E9503F"  # hover / pressed
MINT = "#BAF5D9"        # success, profit
YELLOW = "#F3E16B"      # warnings, pending, highlights
CHARCOAL = "#282828"    # sidebar, headings, text
CARD = "#FFFFFF"
LINE = "#E8DDD2"        # thin borders
LINE_DARK = "#D9CABC"
MUTED = "#7B7068"
ROW_ALT = "#FBF7F3"
CORAL_TINT = "#FFE3DF"  # selected row / soft coral background

# names other modules already import
BG = IVORY
BG_DARK = "#EFE4DA"
ACCENT = CORAL
ACCENT_DARK = CORAL_DARK
TEXT = CHARCOAL
ERROR = "#D92D20"
BORDER = LINE
WINE = CHARCOAL
HOME_BTN_BG, HOME_BTN_BORDER, HOME_BTN_HOVER, HOME_BTN_TEXT = CARD, LINE, "#FFF3F1", CHARCOAL

STYLESHEET = f"""
QWidget {{ background: {IVORY}; color: {CHARCOAL}; font-family: 'Segoe UI', 'Noto Nastaliq Urdu', Arial; font-size: 14px; }}
QDialog, QMainWindow {{ background: {IVORY}; }}
QLabel {{ background: transparent; }}
QCheckBox, QRadioButton {{ background: transparent; }}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit {{
    background: {CARD}; border: 1px solid {LINE_DARK}; border-radius: 10px; padding: 6px 11px;
    selection-background-color: {CORAL_TINT}; selection-color: {CHARCOAL}; }}
QLineEdit:hover, QComboBox:hover, QDoubleSpinBox:hover, QSpinBox:hover, QDateEdit:hover {{ border: 1px solid {MUTED}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus,
QDateEdit:focus {{ border: 2px solid {CORAL}; padding: 5px 10px; }}
QComboBox QAbstractItemView {{ background: {CARD}; border: 1px solid {LINE}; selection-background-color: {CORAL_TINT};
    selection-color: {CHARCOAL}; outline: none; }}
QTableWidget, QTableView, QListWidget {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 12px;
    gridline-color: {LINE}; alternate-background-color: {ROW_ALT}; selection-background-color: {CORAL_TINT};
    selection-color: {CHARCOAL}; }}
QTableWidget::item, QTableView::item {{ padding: 4px 6px; }}
QHeaderView::section {{ background: {BG_DARK}; color: {CHARCOAL}; font-weight: 700; padding: 8px 8px; border: none;
    border-right: 1px solid {LINE}; border-bottom: 1px solid {LINE_DARK}; }}
QListWidget::item {{ padding: 5px 8px; border-radius: 6px; }}
QListWidget::item:selected {{ background: {CORAL_TINT}; color: {CHARCOAL}; }}
QPushButton {{ background: {CORAL}; color: #ffffff; border: none; border-radius: 10px; padding: 8px 20px; font-weight: 600; }}
QPushButton:hover {{ background: {CORAL_DARK}; }}
QPushButton:pressed {{ background: #D2432F; }}
QPushButton:disabled {{ background: #F4B9B1; color: #ffffff; }}
QPushButton:focus {{ border: 2px solid {CHARCOAL}; padding: 6px 18px; }}
QPushButton#secondary {{ background: {CARD}; color: {CHARCOAL}; border: 1px solid {LINE_DARK}; }}
QPushButton#secondary:hover {{ background: {BG_DARK}; }}
QPushButton#secondary:pressed {{ background: {LINE}; }}
QLabel#title {{ font-size: 24px; font-weight: 700; letter-spacing: 1px; color: {CHARCOAL}; }}
QLabel#subtitle {{ color: {MUTED}; }}
QLabel#error {{ color: {ERROR}; font-weight: 600; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {LINE_DARK}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {MUTED}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {LINE_DARK}; border-radius: 5px; min-width: 30px; }}
QScrollBar::handle:horizontal:hover {{ background: {MUTED}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QTabBar::tab {{ background: {BG_DARK}; color: {CHARCOAL}; padding: 7px 16px; border-top-left-radius: 10px;
    border-top-right-radius: 10px; margin-right: 2px; }}
QTabBar::tab:selected {{ background: {CORAL}; color: #ffffff; font-weight: 700; }}
QMenuBar {{ background: {BG_DARK}; }}
QMenuBar::item {{ background: transparent; padding: 6px 12px; }}
QMenuBar::item:selected {{ background: {CORAL_TINT}; }}
QMenu {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 8px; }}
QMenu::item {{ background: transparent; padding: 6px 28px; }}
QMenu::item:selected {{ background: {CORAL_TINT}; color: {CHARCOAL}; }}
QToolTip {{ background: {CHARCOAL}; color: #ffffff; border: none; padding: 4px 8px; }}
"""
