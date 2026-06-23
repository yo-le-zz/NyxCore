# NyxCore v1.1.0 — Implémentation complète des 6 fonctionnalités

Tous les fichiers ci-dessous sont à copier **en remplacement** des fichiers du même nom dans
ton repo (ou en ajout, pour les nouveaux fichiers). L'arborescence du zip reproduit exactement
`src/server/...` et `src/client/...`.

## ⚠️ Étape obligatoire après déploiement : passer sur PostgreSQL

Le serveur utilise maintenant **PostgreSQL par défaut** (`DB_BACKEND=postgresql` dans
`config.py`) — bien plus maintenable en production que SQLite : vraies migrations,
écritures concurrentes propres, pas de surprise "no such column" après une mise à jour.

### Étapes :

1. **Installer PostgreSQL** sur le serveur :
   ```bash
   sudo apt update && sudo apt install -y postgresql postgresql-contrib
   sudo systemctl enable --now postgresql
   ```

2. **Créer la base et l'utilisateur** :
   ```bash
   sudo -u postgres psql << 'EOF'
   CREATE USER nyxcore WITH PASSWORD 'CHANGE_MOI';
   CREATE DATABASE nyxcore OWNER nyxcore;
   GRANT ALL PRIVILEGES ON DATABASE nyxcore TO nyxcore;
   EOF
   ```

3. **Installer les drivers Python** :
   ```bash
   cd ~/NyxCore && source venv/bin/activate
   pip install -r requirements-postgresql.txt
   ```

4. **Configurer `.env`** — copie `.env.postgresql.example` vers `.env` (ou fusionne
   avec ton `.env` existant) et renseigne `PG_PASSWORD`.

5. **Migrer les données existantes** (si tu as déjà des users/ISOs en SQLite) :
   ```bash
   sudo apt install -y pgloader
   pgloader migrate_sqlite_to_postgres.load   # adapte le chemin du .db et le mdp dans le fichier
   sudo -u postgres psql -d nyxcore -f migration_v1.1_postgres.sql
   ```
   Si tu repars d'une base vide, ignore cette étape : `init_db()` créera tout
   automatiquement au premier démarrage, avec toutes les colonnes correctes.

6. **Redémarrer** :
   ```bash
   sudo systemctl restart nyxcore
   journalctl -u nyxcore -f
   ```
   Tu dois voir `Database backend: postgresql — ...` dans les logs.

Si tu veux exceptionnellement rester sur SQLite pour un test local, mets `DB_BACKEND=sqlite`
dans `.env` — tout le code reste compatible avec les deux backends.

---

## Fonctionnalité 1 — Compteurs upload/download séparés

**Modifié :**
- `src/server/models/user.py` → ajout `total_uploads`, `total_downloads`, `total_upload_bytes`, `total_download_bytes`
- `src/server/routers/isos.py` → incrémentés dans `complete_upload()` et `download_iso()`
  (le compteur download n'est incrémenté qu'à la **première** requête d'un téléchargement,
  pas à chaque requête `Range` de reprise, pour ne pas fausser les stats)
- `src/server/routers/admin.py` → `_get_stats()` agrège les nouveaux compteurs
- `src/server/templates/admin/dashboard.html` → 2 cartes séparées (⬆ Uploads / ⬇ Downloads)
- `src/server/templates/admin/users.html` → 2 colonnes par utilisateur

## Fonctionnalité 2 — Site public `/hub/`

**Nouveaux fichiers :**
- `src/server/models/hub.py` → `HubVisit` (1 ligne par IP unique/jour), `HubDownload`
- `src/server/routers/hub.py` → `/hub/` (liste + recherche + tri), `/hub/stats`, `/hub/download/{filename}`
- `src/server/templates/hub/index.html`, `src/server/templates/hub/stats.html`

**Modifié :**
- `src/server/main.py` → `app.include_router(hub.router, prefix="/hub")`
- `src/server/routers/__init__.py`

Accès : `http://<ip>:<port>/hub/` — aucune authentification, aucune route d'upload/suppression
exposée dans ce module (lecture seule par construction, pas juste par contrôle d'accès).

## Fonctionnalité 3 — Annuler un upload en cours

**Côté serveur :**
- `src/server/routers/isos.py` → nouvelle route `DELETE /api/v1/isos/upload/{upload_id}`
  (nettoie les chunks stagés via `iso_storage.cleanup_staging()`, passe le statut DB à `cancelled`)

**Côté client :**
- `src/client/services/api.py` → `upload_iso()` accepte un `cancel_event: threading.Event`,
  vérifié entre chaque chunk (et pendant le calcul du SHA-256) ; `cancel_upload()` ajouté
- `src/client/services/workers.py` → `UploadWorker.cancel()` + signal `cancelled`
- `src/client/ui/main_window.py` → panneau "transfert actif" avec bouton ✕ Cancel, visible
  pendant l'upload

## Fonctionnalité 4 — Gestion ISO par utilisateur (admin)

**Modifié :**
- `src/server/models/user.py` → `is_banned`, `ban_reason`, `banned_at` (ban au niveau **utilisateur**,
  distinct du ban par machine déjà existant — un compte banni ne peut plus se reconnecter,
  vérifié dans `get_current_user()` et au login)
- `src/server/core/security.py`, `src/server/routers/auth.py` → rejettent les comptes `is_banned`
- `src/server/routers/admin.py` → `/admin/isos` enrichi : jointure `Upload(action="upload") + User`
  pour afficher pseudo + ID, recherche (`?q=`), boutons "Delete" et "Ban uploader" (+ option
  "Supprimer et bannir" via une checkbox dans le formulaire)
- `src/server/templates/admin/isos.html`, `src/server/templates/admin/users.html`

## Fonctionnalité 5 — Signalement d'ISO

**Nouveaux fichiers :**
- `src/server/models/report.py` → `Report` (file_name, reporter_id, description, status, dates)
- `src/server/templates/admin/reports.html`
- `src/client/ui/report_dialog.py` → formulaire avec description obligatoire

**Modifié :**
- `src/server/routers/isos.py` → `POST /api/v1/isos/{filename}/report`
- `src/server/routers/admin.py` → `/admin/reports` + 3 actions indépendantes :
  `POST /admin/reports/{id}/ignore`, `/accept` (supprime l'ISO), `/ban-reporter` (bannit le
  signaleur sans toucher à l'ISO)
- `src/client/services/api.py`, `workers.py` → `report_iso()`, `ReportWorker`
- `src/client/ui/main_window.py` → bouton 🚩 Report

## Fonctionnalité 6 — Suppression ISO (vue générale admin)

Déjà couvert par la fonctionnalité 4 : bouton "Delete" sur chaque ligne de `/admin/isos`,
avec confirmation JS avant soumission du formulaire `POST /admin/isos/delete`.
Réutilise `iso_storage.delete_iso()` (existant, inchangé).

---

## Contraintes transversales

- **Traçabilité** : `src/server/models/admin_log.py` (`AdminActionLog` + helper
  `log_admin_action()`), appelé à chaque ban/unban/suppression/traitement de signalement.
- **Pas de nouveau système d'auth** : tout passe par `_require_session` (panel web) ou
  `require_admin` (REST Bearer), déjà existants.
- **Aucune régression** : l'ancien comportement (`Upload.action` log, ban par machine,
  téléchargement par Range) est conservé intégralement ; les nouveaux compteurs s'ajoutent
  en plus, sans rien retirer.

## Fichiers livrés

```
src/server/models/{user.py*, report.py, hub.py, admin_log.py, __init__.py*}
src/server/core/{config.py*, database.py*, security.py*}
src/server/routers/{auth.py*, isos.py*, admin.py*, hub.py, __init__.py*}
src/server/main.py*
src/server/services/schemas.py*
src/server/templates/admin/{base.html*, dashboard.html*, users.html*, isos.html*, reports.html}
src/server/templates/hub/{index.html, stats.html}
src/client/services/{api.py*, workers.py*}
src/client/ui/{main_window.py*, report_dialog.py}
.env.postgresql.example
migrate_sqlite_to_postgres.load
migration_v1.1_postgres.sql
requirements-postgresql.txt
```
(`*` = fichier existant modifié, le reste est nouveau)

## Vérification rapide après déploiement

```bash
# Démarrer le serveur
python -m src.server.main --reload

# Vérifier les nouvelles routes
curl http://127.0.0.1:8000/hub/
curl http://127.0.0.1:8000/hub/stats
curl -H "Authorization: Bearer <master_password>" http://127.0.0.1:8000/admin/api/stats
```

Pense aussi à vérifier dans `/admin/users` que les boutons Ban/Unban apparaissent, et dans
`/admin/isos` que la recherche et les boutons Delete/Ban uploader fonctionnent après avoir
uploadé au moins une ISO de test.
