#!/usr/bin/env bash
# build_msi.sh — requires WiX Toolset v4 installed on the Windows runner
set -euo pipefail

VERSION=$(grep '^version' pyproject.toml | head -1 | sed 's/.*= *"\(.*\)"/\1/')
echo "[msi] Building NyxCore ${VERSION} MSIs …"

for COMPONENT in client; do
    PKG_NAME="nyxcore-${COMPONENT}"
    # Dossier généré par Nuitka contenant l'exécutable et ses dépendances
    SRC_DIR="dist/${COMPONENT}/main.dist"

    # Conversion des slashs pour le format de chemin Windows exigé par WiX
    SRC_DIR_WIN=$(echo "${SRC_DIR}" | sed 's/\//\\/g')

    # Génération du fichier source WiX v4 (Utilise le namespace 'util' requis pour <Files>)
    cat > "dist/${COMPONENT}.wxs" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs"
     xmlns:util="http://wixtoolset.org/schemas/v4/wxs/util">
     
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
      <Component Id="ShortcutComponent" Guid="3b2a1c0d-ef4a-5b6c-7d8e-9f0a1b2c3d4e">
        <Shortcut Id="AppShortcut" Name="NyxCore ${COMPONENT^}"
                  Target="[INSTALLDIR]nyxcore-client.exe"
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

    # Build du MSI avec WiX v4 en incluant l'extension UTIL indispensable pour <Files>
    if command -v wix &>/dev/null; then
        echo "[msi] Compilation du pack avec WiX v4..."
        wix build "dist/${COMPONENT}.wxs" -ext WixToolset.Util.Extension -o "dist/${PKG_NAME}-${VERSION}.msi"
    else
        echo "[ERROR] WiX Toolset v4 non trouvé." >&2
        exit 1
    fi

    echo "[msi] ${PKG_NAME}-${VERSION}.msi terminé avec succès !"
done