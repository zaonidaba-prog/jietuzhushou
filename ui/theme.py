APP_STYLE = """
* {
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI";
    font-size: 10pt;
    color: #1E293B;
}
QMainWindow, QDialog, QWidget#page {
    background: #F3F6FB;
}
QLabel[class="title"] {
    font-size: 19pt;
    font-weight: 700;
    color: #0F172A;
}
QLabel[class="subtitle"] {
    color: #64748B;
    font-size: 9.5pt;
}
QLabel[class="section"] {
    font-weight: 700;
    color: #334155;
    font-size: 10.5pt;
}
QLabel[class="hint"] {
    color: #94A3B8;
    font-size: 9pt;
}
QLineEdit, QComboBox, QKeySequenceEdit {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 8px 12px;
    min-height: 20px;
    selection-background-color: #BFDBFE;
}
QLineEdit:focus, QComboBox:focus, QKeySequenceEdit:focus {
    border: 1px solid #2563EB;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    selection-background-color: #EFF6FF;
    selection-color: #1E293B;
    outline: none;
}
QPushButton {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 9px;
    padding: 8px 16px;
    min-height: 20px;
}
QPushButton:hover {
    background: #F8FAFC;
}
QPushButton:pressed {
    background: #F1F5F9;
}
QPushButton[class="primary"] {
    background: #2563EB;
    color: #FFFFFF;
    border: 1px solid #2563EB;
    font-weight: 600;
}
QPushButton[class="primary"]:hover {
    background: #1D4ED8;
}
QPushButton[class="danger"] {
    color: #DC2626;
    border: 1px solid #FECACA;
    background: #FEF2F2;
}
QPushButton[class="danger"]:hover {
    background: #FEE2E2;
}
QPushButton[class="ghost"] {
    border: none;
    background: transparent;
    color: #475569;
    padding: 6px 10px;
}
QPushButton[class="ghost"]:hover {
    background: #E2E8F0;
}
QPlainTextEdit {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 12px;
    font-size: 11pt;
    selection-background-color: #BFDBFE;
}
QListWidget {
    background: transparent;
    border: none;
    outline: none;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #CBD5E1;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #94A3B8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}
QCheckBox {
    spacing: 8px;
    color: #334155;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1px solid #CBD5E1;
    background: #FFFFFF;
}
QCheckBox::indicator:checked {
    background: #2563EB;
    border: 1px solid #2563EB;
}
QMenu {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    padding: 6px;
}
QMenu::item {
    padding: 7px 26px 7px 14px;
    border-radius: 6px;
}
QMenu::item:selected {
    background: #EFF6FF;
}
QToolTip {
    background: #0F172A;
    color: #FFFFFF;
    border: none;
    padding: 6px 9px;
    border-radius: 6px;
}
QFrame[class="card"] {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 14px;
}
QFrame[class="banner"] {
    background: #FFF7ED;
    border: 1px solid #FED7AA;
    border-radius: 10px;
}
"""
