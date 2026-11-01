"""Shared look: soft blue background (easy on the eyes), white input boxes."""
BG = "#e8f0fa"          # soft blue page background
BG_DARK = "#d3e3f6"     # menu bar / table headers
ACCENT = "#1b6ef3"
ACCENT_DARK = "#1555c0"
TEXT = "#1f2937"
MUTED = "#5b6b80"
ERROR = "#d92d20"
BORDER = "#bcd0e6"

# the 7 big home-screen buttons: a light red tint
HOME_BTN_BG = "#fdeceb"
HOME_BTN_BORDER = "#f0b3b0"
HOME_BTN_HOVER = "#fbd6d3"
HOME_BTN_TEXT = "#7a1f1a"

STYLESHEET = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-family: 'Segoe UI', 'Noto Nastaliq Urdu', Arial; font-size: 14px; }}
QLabel {{ background: transparent; }}
QCheckBox {{ background: transparent; }}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QDoubleSpinBox, QSpinBox, QDateEdit {{
    background: #ffffff; border: 1px solid {BORDER}; border-radius: 7px; padding: 6px 10px; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QDateEdit:focus {{ border: 1px solid {ACCENT}; }}
QComboBox QAbstractItemView {{ background: #ffffff; selection-background-color: #cfe1fb; selection-color: {TEXT}; }}
QTableWidget, QListWidget {{ background: #ffffff; border: 1px solid {BORDER}; }}
QPushButton {{ background: {ACCENT}; color: #fff; border: none; border-radius: 8px; padding: 8px 20px; font-weight: 600; }}
QPushButton:hover {{ background: {ACCENT_DARK}; }}
QPushButton:disabled {{ background: #9bbcf5; }}
QPushButton#secondary {{ background: #d3e3f6; color: {TEXT}; }}
QPushButton#secondary:hover {{ background: #bfd6f1; }}
QLabel#title {{ font-size: 24px; font-weight: 700; letter-spacing: 1px; }}
QLabel#subtitle {{ color: {MUTED}; }}
QLabel#error {{ color: {ERROR}; font-weight: 600; }}
QMenuBar {{ background: {BG_DARK}; }}
QMenuBar::item {{ background: transparent; padding: 6px 12px; }}
QMenuBar::item:selected {{ background: #b9d3ef; }}
QMenu {{ background: #ffffff; border: 1px solid {BORDER}; }}
QMenu::item {{ background: transparent; padding: 6px 28px; }}
QMenu::item:selected {{ background: #cfe1fb; color: {TEXT}; }}
QToolTip {{ background: #ffffff; color: {TEXT}; border: 1px solid {BORDER}; }}
"""
