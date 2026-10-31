"""Shared look: white, clean, modern."""
ACCENT = "#1b6ef3"
ACCENT_DARK = "#1555c0"
TEXT = "#1f2937"
MUTED = "#6b7280"
ERROR = "#d92d20"

STYLESHEET = f"""
QWidget {{ background: #ffffff; color: {TEXT}; font-family: 'Segoe UI', 'Noto Nastaliq Urdu', Arial; font-size: 14px; }}
QLineEdit {{ border: 1px solid #d0d5dd; border-radius: 8px; padding: 9px 12px; background: #fff; }}
QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
QPushButton {{ background: {ACCENT}; color: #fff; border: none; border-radius: 8px; padding: 10px 22px; font-weight: 600; }}
QPushButton:hover {{ background: {ACCENT_DARK}; }}
QPushButton:disabled {{ background: #9bbcf5; }}
QPushButton#secondary {{ background: #eef2f7; color: {TEXT}; }}
QPushButton#secondary:hover {{ background: #dde4ee; }}
QLabel#title {{ font-size: 24px; font-weight: 700; letter-spacing: 1px; }}
QLabel#subtitle {{ color: {MUTED}; }}
QLabel#error {{ color: {ERROR}; font-weight: 600; }}
"""
