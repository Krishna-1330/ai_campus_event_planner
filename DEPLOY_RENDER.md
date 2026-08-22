# CampusFlow AI: Render Deployment

This guide deploys the existing local data to MongoDB Atlas once and then runs the app on Render. You do not need to enter the data again.

## 1. Back up the local database

Make sure the local MongoDB service is running. From PowerShell, run:

```powershell
mongodump --uri="mongodb://127.0.0.1:27017/campusflow_ai" --out=".\mongo-backup"
```

If `mongodump` is not recognized, run it from the MongoDB Database Tools installation folder or install MongoDB Database Tools first.

Keep `.\mongo-backup` somewhere safe. Do not commit it to GitHub.

## 2. Create MongoDB Atlas

1. Create an Atlas project and cluster.
2. Create a database user and save its username and password.
3. In **Network Access**, add `0.0.0.0/0` for a quick Render test, or use the current Render outbound IP policy for a restricted production setup.
4. In **Connect > Drivers**, copy the Python SRV connection string.
5. Replace the placeholders and keep the database name as `campusflow_ai`:

```text
mongodb+srv://ATLAS_USER:ATLAS_PASSWORD@ATLAS_CLUSTER.mongodb.net/campusflow_ai?retryWrites=true&w=majority
```

URL-encode special characters in the database username or password. For example, `@` becomes `%40`.

## 3. Copy the local data into Atlas

Run this from the project folder. Replace the URI with the real Atlas URI:

```powershell
mongorestore --uri="mongodb+srv://ATLAS_USER:ATLAS_PASSWORD@ATLAS_CLUSTER.mongodb.net/campusflow_ai?retryWrites=true&w=majority" --nsFrom="campusflow_ai.*" --nsTo="campusflow_ai.*" ".\mongo-backup\campusflow_ai"
```

For a clean Atlas database, the command copies all CampusFlow collections, including faculty, volunteers, labs, venues, events, assignments, users, notifications, and audit logs.

If Atlas already contains a previous copy and you intentionally want to replace it, add `--drop`:

```powershell
mongorestore --drop --uri="mongodb+srv://ATLAS_USER:ATLAS_PASSWORD@ATLAS_CLUSTER.mongodb.net/campusflow_ai?retryWrites=true&w=majority" --nsFrom="campusflow_ai.*" --nsTo="campusflow_ai.*" ".\mongo-backup\campusflow_ai"
```

Do not use `--drop` unless you have a fresh backup and want to erase the Atlas copy.

## 4. Test Atlas locally before deploying

Temporarily set these values in your local `.env`:

```dotenv
MONGO_URI=mongodb+srv://ATLAS_USER:ATLAS_PASSWORD@ATLAS_CLUSTER.mongodb.net/campusflow_ai?retryWrites=true&w=majority
MONGO_DB_NAME=campusflow_ai
LOCAL_MONGO_URI=
SECRET_KEY=use-a-long-random-value
ADMIN_USERNAME=admin
ADMIN_PASSWORD=use-a-new-admin-password
DEFAULT_MEMBER_PASSWORD=use-a-new-member-password
```

Start the app:

```powershell
flask --app app run --debug
```

Open `http://127.0.0.1:5000/health`. It must report MongoDB Atlas rather than temporary memory. Sign in and confirm that the existing records are visible. Stop the local Flask process after checking.

## 5. Push the project to GitHub

Do not commit `.env`, database backups, passwords, or API keys. Confirm that `.gitignore` includes them before pushing:

```powershell
git status
```

The existing `.gitignore` already excludes `.env`, Python cache files, and virtual environments. Keep `mongo-backup` outside the repository or add it to `.gitignore` before committing.

## 6. Create the Render Web Service

1. Open Render and choose **New + > Web Service**.
2. Connect the GitHub repository.
3. Select **Python 3**.
4. Set **Build Command** to:

```text
pip install -r requirements.txt
```

5. Set **Start Command** to:

```text
gunicorn app:app
```

6. Add these Render environment variables:

| Variable | Value |
| --- | --- |
| `MONGO_URI` | Your Atlas SRV URI |
| `MONGO_DB_NAME` | `campusflow_ai` |
| `LOCAL_MONGO_URI` | Leave empty |
| `SECRET_KEY` | A long random production secret |
| `ADMIN_USERNAME` | Your production admin username |
| `ADMIN_PASSWORD` | A strong production admin password |
| `DEFAULT_MEMBER_PASSWORD` | A strong initial member password |
| `GEMINI_API_KEY` | Optional Gemini API key |
| `SMTP_HOST` | Optional SMTP host |
| `SMTP_PORT` | Optional, usually `587` |
| `SMTP_USERNAME` | Optional SMTP username |
| `SMTP_PASSWORD` | Optional SMTP password |
| `SMTP_FROM` | Optional sender address |
| `SMTP_USE_TLS` | `true` unless your SMTP provider requires otherwise |

The `gunicorn app:app` command is intended for Render's Linux runtime. A local Gunicorn check on Windows can fail with `ModuleNotFoundError: fcntl`; that is a Windows platform limitation, not an application error.

7. Deploy the service.
8. Open the Render URL and check `/health`. It must show Atlas storage, not temporary memory.

## 7. Verify the deployment

Run this checklist after deployment:

- Open `/health` and confirm Atlas storage.
- Sign in as the administrator.
- Confirm faculty, volunteers, labs, venues, events, and assignments are present.
- Open one event and verify its resources and timeline.
- Check that a faculty or volunteer can sign in with the migrated account.
- Create a test notification and verify **Delete all** works.
- Confirm event completion updates accepted participant attendance.
- Check Render logs for database connection errors.

Do not run `flask --app app clear-data` after migration. That command permanently deletes the database records selected by the running app.

## Uploaded images

The database stores image URLs, while image files are stored in `static/uploads/`. Render instances have an ephemeral filesystem, so newly uploaded images can disappear after a redeploy or restart.

For a quick deployment, commit the existing required image files under `static/uploads/` before deploying. For production, change image storage to durable object storage such as Cloudinary, Amazon S3, or Cloudflare R2 and store those permanent URLs in MongoDB.

## Current deployment status

The application already has:

- `gunicorn` in `requirements.txt`.
- Flask application entry point `app:app`.
- Atlas-first database selection through `MONGO_URI`.
- `/health` storage verification.
- Role-based access controls and server-side validation.
- Tests for assignment, availability, venue/lab matching, notifications, timeline replanning, and event email behavior.

Before production, use strong credentials, restrict Atlas network access where practical, configure `SECRET_KEY`, and decide how uploaded images should be persisted.
