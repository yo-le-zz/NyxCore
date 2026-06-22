#!/usr/bin/env bash
# build_msi.sh — requires WiX Toolset v4.0.5 installed on the Windows runner
set -euo pipefail

# 1. Extraction et nettoyage de la version (Format strict X.Y.Z)
RAW_VERSION=$(grep '^version' pyproject.toml | head -1 | sed 's/.*= *"\(.*\)"/\1/')
VERSION=$(echo "${RAW_VERSION}" | sed -E 's/^([0-9]+\.[0-9]+\.[0-9]+).*/\1/')

echo "[msi] Building NyxCore ${VERSION} MSIs …"

for COMPONENT in client; do
    PKG_NAME="nyxcore-${COMPONENT}"
    SRC_DIR="dist/${COMPONENT}/main.dist"

    # Vérification que le dossier Nuitka existe
    if [ ! -d "${SRC_DIR}" ]; then
        echo "[ERROR] Le dossier de build Nuitka n'existe pas : ${SRC_DIR}" >&2
        exit 1
    fi

    # Définition de l'UpgradeCode
    UPGRADE_CODE="4a5c6e7d-8f9a-0b1c-2d3e-4f5a6b7c8d9e"

    # 2. Génération dynamique de la liste des fichiers (Alternative pure Bash à <Files>)
    # On crée les composants WiX un par un pour chaque fichier du dossier Nuitka
    echo "[msi] Récolte des fichiers du dossier Nuitka..."
    FILES_XML=""
    REFS_XML=""
    COUNTER=1

    # On liste récursivement tous les fichiers du dossier de build
    while IFS= read -r FILE_PATH; do
        # Passer si c'est un dossier
        [ -d "${FILE_PATH}" ] && continue

        # Obtenir le chemin relatif par rapport à la racine du projet pour le 'Source'
        # Remplacer les slashs par des antislashs pour Windows/WiX
        WIN_SOURCE=$(echo "${FILE_PATH}" | sed 's/\//\\/g')
        
        # Extraire le nom du fichier pour l'ID (en nettoyant les caractères interdits)
        FILE_NAME=$(basename "${FILE_PATH}")
        CLEAN_ID="File_${COUNTER}"
        COMP_ID="Comp_${COUNTER}"

        # Générer le XML du composant (WiX v4 n'exige plus de GUID pour les composants simples avec KeyPath)
        FILES_XML="${FILES_XML}
      <Component Id=\"${COMP_ID}\">
        <File Id=\"${CLEAN_ID}\" Source=\"${WIN_SOURCE}\" KeyPath=\"yes\" />
      </Component>"

        # Générer la référence pour la Feature principale
        REFS_XML="${REFS_XML}
      <ComponentRef Id=\"${COMP_ID}\" />"

        COUNTER=$((COUNTER + 1))
    done < <(find "${SRC_DIR}" -type f)

    # 3. Génération du fichier WiX principal avec l'arborescence injectée
    cat > "dist/${COMPONENT}.wxs" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">
  
  <Package Name="NyxCore ${COMPONENT^}" Version="${VERSION}" Manufacturer="yolezz"
           UpgradeCode="${UPGRADE_CODE}" Language="1033" Codepage="1252">
    
    <MajorUpgrade DowngradeErrorMessage="A newer version is installed." />
    <MediaTemplate EmbedCab="yes" />

    <Feature Id="Main" Level="1">
      <ComponentRef Id=\"ShortcutComponent\" />
      ${REFS_XML}
    </Feature>

    <StandardDirectory Id="ProgramFiles6432Folder">
      <Directory Id="INSTALLDIR" Name="NyxCore ${COMPONENT^}">
        ${FILES_XML}
      </Directory>
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

  </Package>
</Wix>
EOF

    # 4. Compilation avec WiX v4
    if command -v wix &>/dev/null; then
        echo "[msi] Compilation du pack avec WiX v4..."
        wix build "dist/${COMPONENT}.wxs" -o "dist/${PKG_NAME}-${VERSION}.msi"
    else
        echo "[ERROR] WiX Toolset v4 non trouvé." >&2
        exit 1
    fi

    echo "[msi] ${PKG_NAME}-${VERSION}.msi terminé avec succès !"
done