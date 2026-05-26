"""Application-wide QSS themes."""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import QApplication


DARK = {
    "bg":         "#2b2b2b",
    "bg1":        "#333333",
    "bg2":        "#3c3c3c",
    "bg3":        "#4a4a4a",
    "border":     "#555555",
    "green":      "#55ff55",
    "red":        "#ff4444",
    "amber":      "#ffaa00",
    "cyan":       "#66ccff",
    "blue":       "#5599dd",
    "text":       "#ffffff",
    "dim":        "#bbbbbb",
    "select_bg":  "#4477aa",
    "select_fg":  "#ffffff",
    "entry_bg":   "#333333",
    "alt_row":    "#343434",
}

LIGHT = {
    "bg":         "#f0f0f0",
    "bg1":        "#ffffff",
    "bg2":        "#fafafa",
    "bg3":        "#e8e8e8",
    "border":     "#cccccc",
    "green":      "#28a745",
    "red":        "#dc3545",
    "amber":      "#e67e00",
    "cyan":       "#0077b6",
    "blue":       "#0066cc",
    "text":       "#1a1a1a",
    "dim":        "#666666",
    "select_bg":  "#0066cc",
    "select_fg":  "#ffffff",
    "entry_bg":   "#ffffff",
    "alt_row":    "#f5f5f5",
}


_current = "dark"


def current_theme() -> str:
    return _current


def _palette(c: dict) -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(c["bg"]))
    p.setColor(QPalette.ColorRole.WindowText, QColor(c["text"]))
    p.setColor(QPalette.ColorRole.Base, QColor(c["bg1"]))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(c["alt_row"]))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(c["bg2"]))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(c["text"]))
    p.setColor(QPalette.ColorRole.Text, QColor(c["text"]))
    p.setColor(QPalette.ColorRole.Button, QColor(c["bg2"]))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(c["text"]))
    p.setColor(QPalette.ColorRole.BrightText, QColor(c["red"]))
    p.setColor(QPalette.ColorRole.Link, QColor(c["cyan"]))
    p.setColor(QPalette.ColorRole.Highlight, QColor(c["select_bg"]))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(c["select_fg"]))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(c["dim"]))
    return p


def _stylesheet(c: dict) -> str:
    return f"""
    QWidget {{
        background-color: {c['bg']};
        color: {c['text']};
        font-family: "Segoe UI";
        font-size: 9pt;
    }}
    QMainWindow, QDialog {{ background-color: {c['bg']}; }}

    QGroupBox {{
        background-color: {c['bg']};
        border: 1px solid {c['border']};
        border-radius: 4px;
        margin-top: 14px;
        padding-top: 6px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 6px;
        color: {c['blue']};
        font-weight: bold;
    }}

    QPushButton {{
        background-color: {c['bg2']};
        color: {c['text']};
        border: 1px solid {c['border']};
        border-radius: 3px;
        padding: 5px 12px;
        min-height: 18px;
    }}
    QPushButton:hover    {{ background-color: {c['bg3']}; }}
    QPushButton:pressed  {{ background-color: {c['border']}; }}
    QPushButton:disabled {{ color: {c['dim']}; background-color: {c['bg1']}; }}

    QLineEdit, QPlainTextEdit, QTextEdit {{
        background-color: {c['entry_bg']};
        color: {c['text']};
        border: 1px solid {c['border']};
        border-radius: 3px;
        padding: 3px 5px;
        selection-background-color: {c['select_bg']};
        selection-color: {c['select_fg']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
        border: 1px solid {c['blue']};
    }}

    QComboBox {{
        background-color: {c['entry_bg']};
        color: {c['text']};
        border: 1px solid {c['border']};
        border-radius: 3px;
        padding: 3px 18px 3px 6px;
        min-height: 18px;
    }}
    QComboBox:focus {{ border: 1px solid {c['blue']}; }}
    QComboBox::drop-down {{
        border: none;
        width: 16px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {c['entry_bg']};
        color: {c['text']};
        selection-background-color: {c['select_bg']};
        selection-color: {c['select_fg']};
        border: 1px solid {c['border']};
    }}

    QTreeWidget, QTableWidget, QListWidget {{
        background-color: {c['bg1']};
        alternate-background-color: {c['alt_row']};
        color: {c['text']};
        border: 1px solid {c['border']};
        gridline-color: {c['border']};
    }}
    QTreeWidget::item:selected,
    QTableWidget::item:selected,
    QListWidget::item:selected {{
        background-color: {c['select_bg']};
        color: {c['select_fg']};
    }}
    QHeaderView::section {{
        background-color: {c['bg2']};
        color: {c['dim']};
        border: 1px solid {c['border']};
        padding: 4px 6px;
    }}

    QTabWidget::pane {{
        border: 1px solid {c['border']};
        background-color: {c['bg']};
    }}
    QTabBar::tab {{
        background-color: {c['bg1']};
        color: {c['dim']};
        border: 1px solid {c['border']};
        padding: 6px 18px;
        margin-right: 1px;
    }}
    QTabBar::tab:selected {{
        background-color: {c['bg2']};
        color: {c['text']};
        border-bottom: 2px solid {c['blue']};
    }}

    QProgressBar {{
        background-color: {c['bg1']};
        border: 1px solid {c['border']};
        border-radius: 3px;
        text-align: center;
        color: {c['text']};
    }}
    QProgressBar::chunk {{ background-color: {c['blue']}; }}

    QScrollBar:vertical, QScrollBar:horizontal {{
        background: {c['bg']};
        border: none;
        width: 12px;
        height: 12px;
    }}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
        background: {c['bg3']};
        border-radius: 5px;
        min-width: 20px;
        min-height: 20px;
    }}
    QScrollBar::handle:hover {{ background: {c['border']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}

    QStatusBar {{
        background-color: {c['bg1']};
        color: {c['dim']};
        border-top: 1px solid {c['border']};
    }}

    QMenuBar {{
        background-color: {c['bg1']};
        color: {c['text']};
        border-bottom: 1px solid {c['border']};
    }}
    QMenuBar::item:selected {{
        background-color: {c['select_bg']};
        color: {c['select_fg']};
    }}
    QMenu {{
        background-color: {c['bg1']};
        color: {c['text']};
        border: 1px solid {c['border']};
    }}
    QMenu::item:selected {{
        background-color: {c['select_bg']};
        color: {c['select_fg']};
    }}

    QSplitter::handle {{ background-color: {c['border']}; }}
    QSplitter::handle:horizontal {{ width: 4px; }}
    QSplitter::handle:vertical {{ height: 4px; }}

    QCheckBox::indicator, QRadioButton::indicator {{
        width: 14px;
        height: 14px;
    }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
        background-color: {c['blue']};
        border: 1px solid {c['blue']};
    }}
    QCheckBox::indicator:unchecked, QRadioButton::indicator:unchecked {{
        background-color: {c['entry_bg']};
        border: 1px solid {c['border']};
    }}
    """


def apply_theme(app: QApplication, name: str) -> None:
    global _current
    _current = name
    c = DARK if name == "dark" else LIGHT
    app.setStyle("Fusion")
    app.setPalette(_palette(c))
    app.setStyleSheet(_stylesheet(c))
