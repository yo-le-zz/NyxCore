"""Login & Register dialog — NyxCore client."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.client.services.api import NyxCoreAPI
from src.client.services.workers import LoginWorker, RegisterWorker

STYLE = """
QDialog, QWidget { background: #0d1117; color: #e6edf3; font-family: 'JetBrains Mono', 'Consolas', monospace; }
QLineEdit {
    background: #161b22; border: 1px solid #30363d; border-radius: 6px;
    padding: 8px 12px; color: #e6edf3; font-size: 13px;
}
QLineEdit:focus { border-color: #58a6ff; }
QPushButton {
    background: #1f6feb; color: #fff; border: none; border-radius: 6px;
    padding: 9px 18px; font-weight: bold; font-size: 13px;
}
QPushButton:hover { background: #388bfd; }
QPushButton:disabled { background: #21262d; color: #8b949e; }
QPushButton#secondary {
    background: transparent; color: #58a6ff; border: 1px solid #30363d;
}
QPushButton#secondary:hover { border-color: #58a6ff; }
QLabel#title { font-size: 22px; font-weight: bold; color: #58a6ff; }
QLabel#sub { font-size: 12px; color: #8b949e; margin-bottom: 12px; }
QLabel#error { color: #f85149; font-size: 12px; }
"""


class AuthDialog(QDialog):
    def __init__(self, api: NyxCoreAPI, parent=None):
        super().__init__(parent)
        self.api = api
        self.setWindowTitle("NyxCore — Authentication")
        self.setFixedSize(420, 520)
        self.setStyleSheet(STYLE)
        self._worker = None

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_login_page())
        self._stack.addWidget(self._build_register_page())

        layout = QVBoxLayout(self)
        layout.addWidget(self._stack)
        layout.setContentsMargins(32, 32, 32, 32)

    # ── Pages ─────────────────────────────────────────────────────────────────

    def _build_login_page(self) -> QWidget:
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setSpacing(8)

        title = QLabel("🌑  NyxCore")
        title.setObjectName("title")
        vbox.addWidget(title)

        sub = QLabel("Secure ISO/OS Hub Platform")
        sub.setObjectName("sub")
        vbox.addWidget(sub)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setSpacing(10)

        self._login_user = QLineEdit()
        self._login_user.setPlaceholderText("username")
        self._login_pass = QLineEdit()
        self._login_pass.setPlaceholderText("password")
        self._login_pass.setEchoMode(QLineEdit.EchoMode.Password)

        form.addRow("Username", self._login_user)
        form.addRow("Password", self._login_pass)
        vbox.addLayout(form)

        self._login_error = QLabel("")
        self._login_error.setObjectName("error")
        vbox.addWidget(self._login_error)

        vbox.addSpacing(8)
        self._login_btn = QPushButton("Login")
        self._login_btn.clicked.connect(self._do_login)
        vbox.addWidget(self._login_btn)

        switch = QPushButton("No account? Register")
        switch.setObjectName("secondary")
        switch.clicked.connect(lambda: self._stack.setCurrentIndex(1))
        vbox.addWidget(switch)

        return page

    def _build_register_page(self) -> QWidget:
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setSpacing(8)

        title = QLabel("🌑  Create Account")
        title.setObjectName("title")
        vbox.addWidget(title)

        sub = QLabel("A valid license key is required")
        sub.setObjectName("sub")
        vbox.addWidget(sub)

        form = QFormLayout()
        form.setSpacing(10)

        self._reg_user = QLineEdit()
        self._reg_user.setPlaceholderText("3-32 chars, a-z 0-9 _-")
        self._reg_pass = QLineEdit()
        self._reg_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._reg_pass.setPlaceholderText("min 8 chars, 1 upper, 1 digit")
        self._reg_lic = QLineEdit()
        self._reg_lic.setPlaceholderText("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx")

        form.addRow("Username", self._reg_user)
        form.addRow("Password", self._reg_pass)
        form.addRow("License Key", self._reg_lic)
        vbox.addLayout(form)

        self._reg_error = QLabel("")
        self._reg_error.setObjectName("error")
        vbox.addWidget(self._reg_error)

        vbox.addSpacing(8)
        self._reg_btn = QPushButton("Register")
        self._reg_btn.clicked.connect(self._do_register)
        vbox.addWidget(self._reg_btn)

        switch = QPushButton("Already have an account? Login")
        switch.setObjectName("secondary")
        switch.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        vbox.addWidget(switch)

        return page

    # ── Actions ───────────────────────────────────────────────────────────────

    def _do_login(self):
        self._login_error.setText("")
        self._login_btn.setEnabled(False)
        self._login_btn.setText("Connecting…")

        self._worker = LoginWorker(self.api, self._login_user.text(), self._login_pass.text())
        self._worker.success.connect(self._on_login_ok)
        self._worker.error.connect(self._on_login_err)
        self._worker.start()

    def _on_login_ok(self, _data: dict):
        self.accept()

    def _on_login_err(self, msg: str):
        self._login_error.setText(f"⚠ {msg}")
        self._login_btn.setEnabled(True)
        self._login_btn.setText("Login")

    def _do_register(self):
        self._reg_error.setText("")
        self._reg_btn.setEnabled(False)
        self._reg_btn.setText("Registering…")

        self._worker = RegisterWorker(
            self.api,
            self._reg_user.text(),
            self._reg_pass.text(),
            self._reg_lic.text(),
        )
        self._worker.success.connect(self._on_reg_ok)
        self._worker.error.connect(self._on_reg_err)
        self._worker.start()

    def _on_reg_ok(self, _data: dict):
        QMessageBox.information(self, "Success", "Account created! Please log in.")
        self._stack.setCurrentIndex(0)
        self._reg_btn.setEnabled(True)
        self._reg_btn.setText("Register")

    def _on_reg_err(self, msg: str):
        self._reg_error.setText(f"⚠ {msg}")
        self._reg_btn.setEnabled(True)
        self._reg_btn.setText("Register")
