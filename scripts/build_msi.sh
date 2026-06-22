#!/usr/bin/env bash
# build_msi.sh — requires WiX Toolset v4 installed on the Windows runner
set -euo pipefail

VERSION=$(grep '^version' pyproject.toml | head -1 | sed 's/.*= *"\(.*\)"/\1/')
echo "[msi] Building NyxCore ${VERSION} MSIs …"

for COMPONENT in client; do
    PKG_NAME="nyxcore-${COMPONENT}"
    SRC_DIR="dist\\${COMPONENT}\\nyxcore-${COMPONENT}.dist"

    # Generate WiX source
    cat > "dist/${COMPONENT}.wxs" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">
  <Package Name="NyxCore ${COMPONENT^}" Version="${VERSION}" Manufacturer="yolezz"
           UpgradeCode="$(python -c "import uuid; print(uuid.uuid4())")"
           Language="1033" Codepage="1252">
    <MajorUpgrade DowngradeErrorMessage="A newer version is installed." />
    <MediaTemplate EmbedCab="yes" />
    <Feature Id="Main" Level="1">
      <ComponentGroupRef Id="Files" />
      <ComponentRef Id="ShortcutComponent" />
    </Feature>
    <StandardDirectory Id="ProgramFiles6432Folder">
      <Directory Id="INSTALLDIR" Name="NyxCore ${COMPONENT^}">
        <ComponentGroup Id="Files" Directory="INSTALLDIR">
          <!-- Files harvested via heat.exe or manually listed -->
        </ComponentGroup>
      </Directory>
    </StandardDirectory>
    <StandardDirectory Id="DesktopFolder">
      <Component Id="ShortcutComponent" Guid="*">
        <Shortcut Id="AppShortcut" Name="NyxCore ${COMPONENT^}"
                  Target="[INSTALLDIR]nyxcore-${COMPONENT}.exe"
                  WorkingDirectory="INSTALLDIR" />
        <RemoveFolder Id="RemoveDesktop" On="uninstall" />
        <RegistryValue Root="HKCU" Key="Software\\NyxCore\\${COMPONENT}"
                       Name="installed" Type="integer" Value="1" KeyPath="yes" />
      </Component>
    </StandardDirectory>
  </Package>
</Wix>
EOF

    # Harvest files
    if command -v heat &>/dev/null; then
        heat dir "${SRC_DIR}" -cg Files -dr INSTALLDIR -scom -sfrag -srd \
            -sreg -gg -o "dist/${COMPONENT}_files.wxs" 2>/dev/null || true
    fi

    # Build MSI
    if command -v wix &>/dev/null; then
        wix build "dist/${COMPONENT}.wxs" -o "dist/${PKG_NAME}-${VERSION}.msi" || true
    elif command -v candle &>/dev/null; then
        candle "dist/${COMPONENT}.wxs" -o "dist/${COMPONENT}.wixobj"
        light "dist/${COMPONENT}.wixobj" -o "dist/${PKG_NAME}-${VERSION}.msi"
    fi

    echo "[msi] ${PKG_NAME}-${VERSION}.msi done (or skipped if WiX not found)"
done
