"""Report dialog — file a report against an ISO, with a mandatory description."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from src.client.services.api import NyxCoreAPI
from src.client.services.workers import ReportWorker

STYLE = """
QDialog, QWidget { background: #0d1117; color: #e6edf3; font-family: 'Consolas', monospace; }
QTextEdit {
    background: #161b22; border: 1px solid #30363d; border-radius: 6px;
    padding: 8px; color: #e6edf3; font-size: 13px;
}
QTextEdit:focus { border-color: #58a6ff; }
QPushButton {
    background: #21262d; color: #e6edf3; border: 1px solid #30363d;
    border-radius: 6px; padding: 8px 16px; font-size: 12px;
}
QPushButton:hover { background: #1f6feb; border-color: #1f6feb; }
QPushButton#submit { background: #f85149; border-color: #f85149; color: #fff; font-weight: bold; }
QPushButton#submit:hover { background: #ff7b72; }
QLabel#title { font-size: 16px; font-weight: bold; color: #f85149; }
QLabel#sub { font-size: 11px; color: #8b949e; }
"""


class ReportDialog(QDialog):
    def __init__(self, api: NyxCoreAPI, filename: str, parent=None):
        super().__init__(parent)
        self.api = api
        self.filename = filename
        self._worker = None

        self.setWindowTitle("Report ISO")
        self.setFixedSize(420, 320)
        self.setStyleSheet(STYLE)

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(24, 22, 24, 22)
        vbox.setSpacing(10)

        title = QLabel("🚩 Report this ISO")
        title.setObjectName("title")
        vbox.addWidget(title)

        sub = QLabel(f"{filename}")
        sub.setObjectName("sub")
        sub.setWordWrap(True)
        vbox.addWidget(sub)

        vbox.addSpacing(6)
        vbox.addWidget(QLabel("Description (required) — explain why you are reporting this ISO:"))

        self._description = QTextEdit()
        self._description.setPlaceholderText(
            "e.g. corrupted file, malware suspected, mislabeled content, copyright issue…"
        )
        vbox.addWidget(self._description)

        self._error = QLabel("")
        self._error.setStyleSheet("color:#f85149;font-size:11px")
        vbox.addWidget(self._error)

        self._submit_btn = QPushButton("Submit report")
        self._submit_btn.setObjectName("submit")
        self._submit_btn.clicked.connect(self._submit)
        vbox.addWidget(self._submit_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        vbox.addWidget(cancel_btn)

    def _submit(self):
        description = self._description.toPlainText().strip()
        if not description:
            self._error.setText("⚠ A description is required to file a report.")
            return

        self._error.setText("")
        self._submit_btn.setEnabled(False)
        self._submit_btn.setText("Submitting…")

        self._worker = ReportWorker(self.api, self.filename, description)
        self._worker.success.connect(self._on_ok)
        self._worker.error.connect(self._on_err)
        self._worker.start()

    def _on_ok(self, _filename: str):
        QMessageBox.information(self, "Report submitted", "Thank you, the report has been sent to the admins.")
        self.accept()

    def _on_err(self, msg: str):
        self._error.setText(f"⚠ {msg}")
        self._submit_btn.setEnabled(True)
        self._submit_btn.setText("Submit report")
