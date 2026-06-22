"""Main window — NyxCore ISO hub."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QSize
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
QStatusBar { background: #161b22; color: #8b949e; font-size: 11px; }
"""


class MainWindow(QMainWindow):
    def __init__(self, api: NyxCoreAPI, username: str):
        super().__init__()
        self.api = api
        self.username = username
        self._active_worker = None

        self.setWindowTitle("NyxCore ISO Hub")
        self.setMinimumSize(800, 560)
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
        toolbar.addWidget(self._refresh_btn)
        toolbar.addWidget(self._upload_btn)
        toolbar.addWidget(self._download_btn)
        toolbar.addStretch()
        root.addLayout(toolbar)

        # ── ISO list ──────────────────────────────────────────────────────────
        self._list = QListWidget()
        self._list.itemSelectionChanged.connect(self._on_selection)
        root.addWidget(self._list)

        # ── Progress ──────────────────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setValue(0)
        self._progress.setVisible(False)
        root.addWidget(self._progress)

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
        self._download_btn.setEnabled(bool(self._list.selectedItems()))

    def _upload_iso(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select ISO File", str(Path.home()),
            "ISO Files (*.iso *.img);;All Files (*)"
        )
        if not path:
            return

        self._set_busy(True)
        worker = UploadWorker(self.api, path)
        worker.progress.connect(self._progress.setValue)
        worker.success.connect(self._on_upload_ok)
        worker.error.connect(self._on_op_error)
        worker.finished.connect(lambda: self._set_busy(False))
        self._keep(worker)
        worker.start()

    def _on_upload_ok(self, path: str):
        name = Path(path).name
        self._status.showMessage(f"✔ {name} uploaded")
        self._load_isos()

    def _download_iso(self):
        items = self._list.selectedItems()
        if not items:
            return
        filename = items[0].data(Qt.ItemDataRole.UserRole)

        dest_dir = QFileDialog.getExistingDirectory(self, "Select Download Folder", str(Path.home()))
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

    def _on_op_error(self, msg: str):
        self._status.showMessage(f"Error: {msg}")
        QMessageBox.critical(self, "Error", msg)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_busy(self, busy: bool):
        self._upload_btn.setEnabled(not busy)
        self._download_btn.setEnabled(not busy)
        self._refresh_btn.setEnabled(not busy)
        self._progress.setVisible(busy)
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
