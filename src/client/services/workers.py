"""Qt worker threads for non-blocking API operations."""

from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal

from src.client.services.api import UploadCancelled


class LoginWorker(QThread):
    success = Signal(dict)
    error = Signal(str)

    def __init__(self, api, username: str, password: str):
        super().__init__()
        self._api = api
        self._username = username
        self._password = password

    def run(self):
        try:
            data = self._api.login(self._username, self._password)
            self.success.emit(data)
        except Exception as e:
            self.error.emit(str(e))


class RegisterWorker(QThread):
    success = Signal(dict)
    error = Signal(str)

    def __init__(self, api, username: str, password: str, license_key: str):
        super().__init__()
        self._api = api
        self._username = username
        self._password = password
        self._license_key = license_key

    def run(self):
        try:
            data = self._api.register(self._username, self._password, self._license_key)
            self.success.emit(data)
        except Exception as e:
            self.error.emit(str(e))


class UploadWorker(QThread):
    """
    Upload worker — cancellable (feature 3).

    Call .cancel() from the UI thread to request cancellation; the worker
    checks a threading.Event between chunks (and during the SHA-256 pass) and
    stops cleanly, telling the server to discard the partial upload.
    """

    progress = Signal(int)  # percentage 0-100
    success = Signal(str)
    error = Signal(str)
    cancelled = Signal(str)

    def __init__(self, api, file_path: str):
        super().__init__()
        self._api = api
        self._file_path = file_path
        self._cancel_event = threading.Event()

    def cancel(self):
        """Request cancellation. Safe to call multiple times / from the UI thread."""
        self._cancel_event.set()

    def run(self):
        try:

            def _cb(sent, total):
                if total:
                    self.progress.emit(int(sent * 100 / total))

            self._api.upload_iso(
                self._file_path, progress_callback=_cb, cancel_event=self._cancel_event
            )
            self.success.emit(self._file_path)
        except UploadCancelled as e:
            self.cancelled.emit(str(e))
        except Exception as e:
            self.error.emit(str(e))


class DownloadWorker(QThread):
    progress = Signal(int)  # percentage 0-100
    success = Signal(str)
    error = Signal(str)

    def __init__(self, api, filename: str, dest_path: str):
        super().__init__()
        self._api = api
        self._filename = filename
        self._dest_path = dest_path

    def run(self):
        try:

            def _cb(recv, total):
                if total:
                    self.progress.emit(int(recv * 100 / total))

            saved = self._api.download_iso(self._filename, self._dest_path, progress_callback=_cb)
            self.success.emit(saved)
        except Exception as e:
            self.error.emit(str(e))


class ListISOsWorker(QThread):
    success = Signal(list)
    error = Signal(str)

    def __init__(self, api):
        super().__init__()
        self._api = api

    def run(self):
        try:
            self.success.emit(self._api.list_isos())
        except Exception as e:
            self.error.emit(str(e))


class ReportWorker(QThread):
    """Feature 5 — submits a report for an ISO."""

    success = Signal(str)
    error = Signal(str)

    def __init__(self, api, filename: str, description: str):
        super().__init__()
        self._api = api
        self._filename = filename
        self._description = description

    def run(self):
        try:
            self._api.report_iso(self._filename, self._description)
            self.success.emit(self._filename)
        except Exception as e:
            self.error.emit(str(e))
