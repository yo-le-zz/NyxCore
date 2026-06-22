#!/bin/env bash
# build_deb.sh <server|client>
set -euo pipefail

COMPONENT="${1:-server}"
VERSION="1.0.0"
ARCH="amd64"
PKG_NAME="nyxcore-${COMPONENT}"
PKG_DIR="dist/pkg_${COMPONENT}"
ICON_PATH="/home/ilan/Bureau/NyxCore/NyxCore.png"

echo "[deb] Building ${PKG_NAME}_${VERSION}.deb …"

# ── Structure des dossiers ───────────────────────────────────────────────────
rm -rf "${PKG_DIR}"
mkdir -p "${PKG_DIR}/DEBIAN"
mkdir -p "${PKG_DIR}/usr/bin"
mkdir -p "${PKG_DIR}/usr/lib/nyxcore/${COMPONENT}"
mkdir -p "${PKG_DIR}/lib/systemd/system"
mkdir -p "${PKG_DIR}/usr/share/pixmaps"

# ── Copie de l'icône (si elle existe) ─────────────────────────────────────────
if [ -f "${ICON_PATH}" ]; then
    cp "${ICON_PATH}" "${PKG_DIR}/usr/share/pixmaps/nyxcore.png"
else
    echo "[warning] Icône introuvable à l'emplacement : ${ICON_PATH}"
fi

# ── Copie du binaire compilé ──────────────────────────────────────────────────
BINARY_DIR="dist/${COMPONENT}/nyxcore-${COMPONENT}.dist"
if [ -d "${BINARY_DIR}" ]; then
    cp -r "${BINARY_DIR}/." "${PKG_DIR}/usr/lib/nyxcore/${COMPONENT}/"
fi

# ── Script Wrapper (Exécutable principal) ─────────────────────────────────────
cat > "${PKG_DIR}/usr/bin/nyxcore-${COMPONENT}" << EOF
#!/bin/sh
exec /usr/lib/nyxcore/${COMPONENT}/nyxcore-${COMPONENT} "\$@"
EOF
chmod +x "${PKG_DIR}/usr/bin/nyxcore-${COMPONENT}"

# ── Fichier Control (Métadonnées) ─────────────────────────────────────────────
# Note: python3 (>= 3.13) force l'utilisation de Python 3.13 au minimum
cat > "${PKG_DIR}/DEBIAN/control" << EOF
Package: ${PKG_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Maintainer: yolezz <yolezz@nyxcore.io>
Depends: python3 (>= 3.13)
Description: NyxCore — ${COMPONENT}
 NyxCore is a software that allows for a huge HUB of different ISO operating systems.
 Secure platform for ISO management, license control, and machine tracking.
EOF

# ── Unité Systemd (Serveur uniquement) ────────────────────────────────────────
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

    # Script Post-installation
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

# ── Construction du paquet ────────────────────────────────────────────────────
fakeroot dpkg-deb --build "${PKG_DIR}" "dist/${PKG_NAME}_${VERSION}.deb"
echo "[deb] Done: dist/${PKG_NAME}_${VERSION}.deb"