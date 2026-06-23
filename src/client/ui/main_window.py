"""Main window — NyxCore ISO hub."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from src.client.services.api import NyxCoreAPI
from src.client.services.workers import DownloadWorker, ListISOsWorker, UploadWorker
from src.client.ui.report_dialog import ReportDialog

STYLE = """
QMainWindow, QWidget { background: #0d1117; color: #e6edf3; font-family: 'Consolas', monospace; }
QLabel#header { font-size: 18px; font-weight: bold; color: #58a6ff; }
QLabel#user  { font-size: 12px; color: #8b949e; }
QListWidget {
    background: #161b22; border: 1px solid #30363d; border-radius: 6px;
    color: #e6edf3; font-size: 13px; padding: 4px;
}
QListWidget::item { padding: 8px 12px; border-bottom: 1px solid #21262d; }
QListWidget::item:selected { background: #1f6feb; border-radius: 4px; }
QProgressBar {
    background: #21262d; border: none; border-radius: 4px;
    text-align: center; color: #e6edf3; min-height: 20px;
}
QProgressBar::chunk { background: #1f6feb; border-radius: 4px; }
QPushButton {
    background: #21262d; color: #e6edf3; border: 1px solid #30363d;
    border-radius: 6px; padding: 7px 16px; font-size: 12px;
}
QPushButton:hover { background: #1f6feb; border-color: #1f6feb; }
QPushButton:disabled { color: #484f58; }
QPushButton#danger { border-color: #f85149; color: #f85149; }
QPushButton#danger:hover { background: #f85149; color: #fff; }
QPushButton#warn { border-color: #d29922; color: #d29922; }
QPushButton#warn:hover { background: #d29922; color: #0d1117; }
QStatusBar { background: #161b22; color: #8b949e; font-size: 11px; }
QWidget#transferRow { background: #161b22; border: 1px solid #30363d; border-radius: 6px; }
QLabel#transferLabel { color: #8b949e; font-size: 11px; }
"""


class MainWindow(QMainWindow):
    def __init__(self, api: NyxCoreAPI, username: str):
        super().__init__()
        self.api = api
        self.username = username
        self._active_worker = None
        self._upload_worker: UploadWorker | None = None

        self.setWindowTitle("NyxCore ISO Hub")
        self.setMinimumSize(820, 600)
        self.setStyleSheet(STYLE)

        self._build_ui()
        self._load_isos()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title = QLabel("🌑  NyxCore ISO Hub")
        title.setObjectName("header")
        hdr.addWidget(title)
        hdr.addStretch()
        user_lbl = QLabel(f"👤 {self.username}")
        user_lbl.setObjectName("user")
        hdr.addWidget(user_lbl)
        logout_btn = QPushButton("Logout")
        logout_btn.setObjectName("danger")
        logout_btn.clicked.connect(self._logout)
        hdr.addWidget(logout_btn)
        root.addLayout(hdr)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        self._refresh_btn = QPushButton("⟳  Refresh")
        self._refresh_btn.clicked.connect(self._load_isos)
        self._upload_btn = QPushButton("⬆  Upload ISO")
        self._upload_btn.clicked.connect(self._upload_iso)
        self._download_btn = QPushButton("⬇  Download")
        self._download_btn.setEnabled(False)
        self._download_btn.clicked.connect(self._download_iso)
        self._report_btn = QPushButton("🚩  Report")
        self._report_btn.setObjectName("warn")
        self._report_btn.setEnabled(False)
        self._report_btn.clicked.connect(self._report_iso)
        toolbar.addWidget(self._refresh_btn)
        toolbar.addWidget(self._upload_btn)
        toolbar.addWidget(self._download_btn)
        toolbar.addWidget(self._report_btn)
        toolbar.addStretch()
        root.addLayout(toolbar)

        # ── ISO list ──────────────────────────────────────────────────────────
        self._list = QListWidget()
        self._list.itemSelectionChanged.connect(self._on_selection)
        root.addWidget(self._list)

        # ── Active transfer panel (feature 3 — cancellable upload) ───────────
        self._transfer_row = QWidget()
        self._transfer_row.setObjectName("transferRow")
        self._transfer_row.setVisible(False)
        trow = QHBoxLayout(self._transfer_row)
        trow.setContentsMargins(10, 8, 10, 8)

        self._transfer_label = QLabel("")
        self._transfer_label.setObjectName("transferLabel")
        trow.addWidget(self._transfer_label, stretch=0)

        self._progress = QProgressBar()
        self._progress.setValue(0)
        trow.addWidget(self._progress, stretch=1)

        self._cancel_upload_btn = QPushButton("✕ Cancel")
        self._cancel_upload_btn.setObjectName("danger")
        self._cancel_upload_btn.clicked.connect(self._cancel_upload)
        trow.addWidget(self._cancel_upload_btn, stretch=0)

        root.addWidget(self._transfer_row)

        # ── Status bar ────────────────────────────────────────────────────────
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready")

    # ── ISO operations ────────────────────────────────────────────────────────

    def _load_isos(self):
        self._status.showMessage("Loading ISOs…")
        self._refresh_btn.setEnabled(False)
        worker = ListISOsWorker(self.api)
        worker.success.connect(self._on_isos_loaded)
        worker.error.connect(lambda e: self._status.showMessage(f"Error: {e}"))
        worker.finished.connect(lambda: self._refresh_btn.setEnabled(True))
        self._keep(worker)
        worker.start()

    def _on_isos_loaded(self, isos: list[dict]):
        self._list.clear()
        for iso in isos:
            size_mb = iso["file_size"] / (1024 * 1024)
            item = QListWidgetItem(f"  {iso['file_name']}   ({size_mb:.1f} MB)")
            item.setData(Qt.ItemDataRole.UserRole, iso["file_name"])
            self._list.addItem(item)
        self._status.showMessage(f"{len(isos)} ISO(s) available")

    def _on_selection(self):
        has_selection = bool(self._list.selectedItems())
        self._download_btn.setEnabled(has_selection)
        self._report_btn.setEnabled(has_selection)

    def _selected_filename(self) -> str | None:
        items = self._list.selectedItems()
        if not items:
            return None
        return items[0].data(Qt.ItemDataRole.UserRole)

    # ── Upload (cancellable — feature 3) ──────────────────────────────────────

    def _upload_iso(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select ISO File", str(Path.home()), "ISO Files (*.iso *.img);;All Files (*)"
        )
        if not path:
            return

        self._set_busy(True)
        self._show_transfer_row(Path(path).name)

        worker = UploadWorker(self.api, path)
        worker.progress.connect(self._progress.setValue)
        worker.success.connect(self._on_upload_ok)
        worker.error.connect(self._on_op_error)
        worker.cancelled.connect(self._on_upload_cancelled)
        worker.finished.connect(self._on_upload_finished)
        self._upload_worker = worker
        self._keep(worker)
        worker.start()

    def _cancel_upload(self):
        if self._upload_worker is not None:
            self._cancel_upload_btn.setEnabled(False)
            self._cancel_upload_btn.setText("Cancelling…")
            self._upload_worker.cancel()

    def _show_transfer_row(self, label: str):
        self._transfer_label.setText(label)
        self._cancel_upload_btn.setEnabled(True)
        self._cancel_upload_btn.setText("✕ Cancel")
        self._transfer_row.setVisible(True)
        self._progress.setValue(0)

    def _on_upload_ok(self, path: str):
        name = Path(path).name
        self._status.showMessage(f"✔ {name} uploaded")
        self._load_isos()

    def _on_upload_cancelled(self, msg: str):
        self._status.showMessage(f"⏹ {msg}")

    def _on_upload_finished(self):
        self._upload_worker = None
        self._transfer_row.setVisible(False)
        self._set_busy(False)

    # ── Download ──────────────────────────────────────────────────────────────

    def _download_iso(self):
        filename = self._selected_filename()
        if not filename:
            return

        dest_dir = QFileDialog.getExistingDirectory(
            self, "Select Download Folder", str(Path.home())
        )
        if not dest_dir:
            return

        dest = str(Path(dest_dir) / filename)
        self._set_busy(True)
        worker = DownloadWorker(self.api, filename, dest)
        worker.progress.connect(self._progress.setValue)
        worker.success.connect(self._on_download_ok)
        worker.error.connect(self._on_op_error)
        worker.finished.connect(lambda: self._set_busy(False))
        self._keep(worker)
        worker.start()

    def _on_download_ok(self, saved: str):
        self._status.showMessage(f"✔ Saved to {saved}")
        QMessageBox.information(self, "Download complete", f"File saved to:\n{saved}")

    # ── Report (feature 5) ─────────────────────────────────────────────────────

    def _report_iso(self):
        filename = self._selected_filename()
        if not filename:
            return
        dlg = ReportDialog(self.api, filename, parent=self)
        dlg.exec()

    # ── Shared error handling ─────────────────────────────────────────────────

    def _on_op_error(self, msg: str):
        self._status.showMessage(f"Error: {msg}")
        QMessageBox.critical(self, "Error", msg)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_busy(self, busy: bool):
        self._upload_btn.setEnabled(not busy)
        self._download_btn.setEnabled(not busy and bool(self._list.selectedItems()))
        self._refresh_btn.setEnabled(not busy)
        if not busy:
            self._progress.setValue(0)

    def _keep(self, worker):
        """Prevent garbage collection of running workers."""
        self._active_worker = worker

    def _logout(self):
        from src.client.utils.session import clear_session

        self.api.logout()
        clear_session()
        self.close()
