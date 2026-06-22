"""NyxCore Client — main entry point."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from src.client.services.api import NyxCoreAPI, APIError
from src.client.utils.hardware import get_hardware_id, get_hostname, get_os_info
from src.client.utils.session import clear_session, load_session, save_session


def run():
    app = QApplication(sys.argv)
    app.setApplicationName("NyxCore")
    app.setOrganizationName("yolezz")

    # ── Try to restore session ─────────────────────────────────────────────────
    stored = load_session()
    server_url = stored["server_url"] if stored else None
    api: NyxCoreAPI | None = None

    if stored:
        api = NyxCoreAPI(stored["server_url"])
        api._access_token = stored["access_token"]
        api._refresh_token = stored["refresh_token"]
        try:
            me = api.me()
            username = me["username"]
            _open_main(app, api, username)
            return sys.exit(app.exec())
        except Exception:
            clear_session()

    # ── Server URL dialog ─────────────────────────────────────────────────────
    from src.client.ui.server_dialog import ServerDialog

    srv_dlg = ServerDialog(server_url or "http://127.0.0.1:8000")
    if srv_dlg.exec() != srv_dlg.DialogCode.Accepted:
        sys.exit(0)

    server_url = srv_dlg.server_url
    api = NyxCoreAPI(server_url)

    # Verify server reachable
    try:
        api.health()
    except Exception as e:
        QMessageBox.critical(None, "Connection Error", f"Cannot reach server:\n{e}")
        sys.exit(1)

    # ── Auth dialog ───────────────────────────────────────────────────────────
    from src.client.ui.auth_dialog import AuthDialog

    auth_dlg = AuthDialog(api)
    if auth_dlg.exec() != auth_dlg.DialogCode.Accepted:
        sys.exit(0)

    me = api.me()
    username = me["username"]

    # Persist session
    save_session(server_url, api._access_token, api._refresh_token, username)

    # Register machine silently
    try:
        api.register_machine(get_hardware_id(), get_hostname(), get_os_info())
    except APIError as e:
        if e.status_code == 403:
            QMessageBox.critical(None, "Machine Banned", str(e))
            sys.exit(1)

    _open_main(app, api, username)
    sys.exit(app.exec())


def _open_main(app: QApplication, api: NyxCoreAPI, username: str):
    from src.client.ui.main_window import MainWindow

    win = MainWindow(api, username)
    win.show()


if __name__ == "__main__":
    run()
