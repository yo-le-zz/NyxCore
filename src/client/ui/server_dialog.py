"""Server URL selection dialog."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

STYLE = """
QDialog { background: #0d1117; color: #e6edf3; font-family: 'Consolas', monospace; }
QLineEdit {
    background: #161b22; border: 1px solid #30363d; border-radius: 6px;
    padding: 8px; color: #e6edf3;
}
QLabel { color: #8b949e; }
"""


class ServerDialog(QDialog):
    def __init__(self, default_url: str = "http://127.0.0.1:8000", parent=None):
        super().__init__(parent)
        self.setWindowTitle("NyxCore — Server")
        self.setFixedSize(380, 160)
        self.setStyleSheet(STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)

        lbl = QLabel("Enter NyxCore server URL:")
        layout.addWidget(lbl)

        form = QFormLayout()
        self._url = QLineEdit(default_url)
        form.addRow("Server URL", self._url)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def server_url(self) -> str:
        return self._url.text().strip().rstrip("/")
