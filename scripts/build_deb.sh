#!/usr/bin/env bash
# build_deb.sh <server|client>
set -euo pipefail

COMPONENT="${1:-server}"
VERSION=$(grep '^version' pyproject.toml | head -1 | sed 's/.*= *"\(.*\)"/\1/')
ARCH="amd64"
PKG_NAME="nyxcore-${COMPONENT}"
PKG_DIR="dist/pkg_${COMPONENT}"

echo "[deb] Building ${PKG_NAME}_${VERSION}.deb …"

# ── Directory structure ───────────────────────────────────────────────────────
rm -rf "${PKG_DIR}"
mkdir -p "${PKG_DIR}/DEBIAN"
mkdir -p "${PKG_DIR}/usr/bin"
mkdir -p "${PKG_DIR}/usr/lib/nyxcore/${COMPONENT}"
mkdir -p "${PKG_DIR}/lib/systemd/system"

# ── Copy compiled binary ──────────────────────────────────────────────────────
BINARY_DIR="dist/${COMPONENT}/nyxcore-${COMPONENT}.dist"
if [ -d "${BINARY_DIR}" ]; then
    cp -r "${BINARY_DIR}/." "${PKG_DIR}/usr/lib/nyxcore/${COMPONENT}/"
fi

# ── Wrapper script ────────────────────────────────────────────────────────────
cat > "${PKG_DIR}/usr/bin/nyxcore-${COMPONENT}" << EOF
#!/bin/sh
exec /usr/lib/nyxcore/${COMPONENT}/nyxcore-${COMPONENT} "\$@"
EOF
chmod +x "${PKG_DIR}/usr/bin/nyxcore-${COMPONENT}"

# ── Control file ──────────────────────────────────────────────────────────────
cat > "${PKG_DIR}/DEBIAN/control" << EOF
Package: ${PKG_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Maintainer: yolezz <yolezz@nyxcore.io>
Description: NyxCore ISO/OS Hub — ${COMPONENT}
 Secure platform for ISO management, license control, and machine tracking.
EOF

# ── Systemd unit (server only) ────────────────────────────────────────────────
if [ "${COMPONENT}" = "server" ]; then
    cat > "${PKG_DIR}/lib/systemd/system/nyxcore-server.service" << EOF
[Unit]
Description=NyxCore Server
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/nyxcore-server --port 8000
Restart=on-failure
RestartSec=5
User=nyxcore
EnvironmentFile=-/etc/nyxcore/server.env

[Install]
WantedBy=multi-user.target
EOF

    # Post-install script
    cat > "${PKG_DIR}/DEBIAN/postinst" << 'EOF'
#!/bin/sh
set -e
useradd --system --no-create-home --shell /usr/sbin/nologin nyxcore 2>/dev/null || true
mkdir -p /etc/nyxcore /var/lib/nyxcore/isos
chown nyxcore:nyxcore /var/lib/nyxcore /var/lib/nyxcore/isos
systemctl daemon-reload
systemctl enable nyxcore-server 2>/dev/null || true
echo "NyxCore server installed. Edit /etc/nyxcore/server.env then: systemctl start nyxcore-server"
EOF
    chmod +x "${PKG_DIR}/DEBIAN/postinst"
fi

# ── Build package ─────────────────────────────────────────────────────────────
fakeroot dpkg-deb --build "${PKG_DIR}" "dist/${PKG_NAME}_${VERSION}.deb"
echo "[deb] Done: dist/${PKG_NAME}_${VERSION}.deb"
