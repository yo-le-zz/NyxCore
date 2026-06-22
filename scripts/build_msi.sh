#!/usr/bin/env bash
set -euo pipefail

# Nettoyage propre et simple de la version (votre version initiale validée)
RAW_VERSION=$(grep '^version' pyproject.toml | head -1 | sed 's/.*= *"\(.*\)"/\1/')
VERSION=$(echo "${RAW_VERSION}" | sed -E 's/^([0-9]+\.[0-9]+\.[0-9]+).*/\1/')

echo "=== DIAGNOSTIC WIX v4 ==="
echo "Version brute : ${RAW_VERSION}"
echo "Version MSI   : ${VERSION}"
if command -v wix &>/dev/null; then
    echo "Version de l'exécutable WiX :"
    wix --version || true
else
    echo "wix n'est pas dans le PATH global du shell"
fi
echo "========================="

COMPONENT="client"
PKG_NAME="nyxcore-${COMPONENT}"

# Génération d'un schéma XML 100% valide (statique, juste pour valider la compilation)
cat > "dist/${COMPONENT}.wxs" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">
  <Package Name="NyxCore ${COMPONENT^}" Version="${VERSION}" Manufacturer="yolezz"
           UpgradeCode="4a5c6e7d-8f9a-0b1c-2d3e-4f5a6b7c8d9e"
           Language="1033" Codepage="1252">
    
    <MajorUpgrade DowngradeErrorMessage="A newer version is installed." />
    <MediaTemplate EmbedCab="yes" />

    <Feature Id="Main" Level="1">
      <ComponentRef Id="MainExecutableComponent" />
      <ComponentRef Id="ShortcutComponent" />
    </Feature>

    <StandardDirectory Id="ProgramFiles6432Folder">
      <Directory Id="INSTALLDIR" Name="NyxCore ${COMPONENT^}" />
    </StandardDirectory>

    <StandardDirectory Id="DesktopFolder">
      <Component Id="ShortcutComponent" Guid="3b2a1c0d-ef4a-5b6c-7d8e-9f0a1b2c3d4e">
        <Shortcut Id="AppShortcut" Name="NyxCore ${COMPONENT^}"
                  Target="[INSTALLDIR]nyxcore-${COMPONENT}.exe"
                  WorkingDirectory="INSTALLDIR" />
        <RemoveFolder Id="RemoveDesktop" On="uninstall" />
        <RegistryValue Root="HKCU" Key="Software\\NyxCore\\${COMPONENT}"
                       Name="installed" Type="integer" Value="1" KeyPath="yes" />
      </Component>
    </StandardDirectory>

    <Component Id="MainExecutableComponent" Guid="1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d" Directory="INSTALLDIR">
      <File Id="MainExe" Source="dist/${COMPONENT}/main.dist/nyxcore-client.exe" KeyPath="yes" />
    </Component>

  </Package>
</Wix>
EOF

echo "[wix] Lancement du build de test..."
wix build "dist/${COMPONENT}.wxs" -o "dist/${PKG_NAME}-${VERSION}.msi"