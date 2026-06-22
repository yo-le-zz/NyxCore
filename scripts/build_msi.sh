#!/usr/bin/env bash
# build_msi.sh — requires WiX Toolset v4 installed on the Windows runner
set -euo pipefail

VERSION=$(grep '^version' pyproject.toml | head -1 | sed 's/.*= *"\(.*\)"/\1/')
echo "[msi] Building NyxCore ${VERSION} MSIs …"

for COMPONENT in client; do
    PKG_NAME="nyxcore-${COMPONENT}"
    # Dossier généré par Nuitka contenant l'exécutable et toutes les DLLs/dépendances
    SRC_DIR="dist/${COMPONENT}/nyxcore-${COMPONENT}.dist"

    # On s'assure que le chemin est au format Windows pour WiX (remplacement des / par des \)
    SRC_DIR_WIN=$(echo "${SRC_DIR}" | sed 's/\//\\/g')

    # Generate WiX source
    cat > "dist/${COMPONENT}.wxs" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">
  <Package Name="NyxCore ${COMPONENT^}" Version="${VERSION}" Manufacturer="yolezz"
           UpgradeCode="4a5c6e7d-8f9a-0b1c-2d3e-4f5a6b7c8d9e"
           Language="1033" Codepage="1252">
    <MajorUpgrade DowngradeErrorMessage="A newer version is installed." />
    <MediaTemplate EmbedCab="yes" />

    <Feature Id="Main" Level="1">
      <ComponentGroupRef Id="Files" />
      <ComponentRef Id="ShortcutComponent" />
    </Feature>

    <StandardDirectory Id="ProgramFiles6432Folder">
      <Directory Id="INSTALLDIR" Name="NyxCore ${COMPONENT^}" />
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

    <ComponentGroup Id="Files" Directory="INSTALLDIR">
      <Files Include="${SRC_DIR_WIN}\\**" />
    </ComponentGroup>

  </Package>
</Wix>
EOF

    # Build MSI avec WiX v4
    if command -v wix &>/dev/null; then
        echo "[msi] Compilation du pack avec WiX v4..."
        wix build "dist/${COMPONENT}.wxs" -o "dist/${PKG_NAME}-${VERSION}.msi"
    else
        echo "[ERROR] WiX Toolset v4 non trouvé." >&2
        exit 1
    fi

    echo "[msi] ${PKG_NAME}-${VERSION}.msi terminé avec succès."
done