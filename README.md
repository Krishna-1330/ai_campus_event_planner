# CampusFlow AI

CampusFlow AI is a constraint-first, multi-agent campus event operations platform. It converts an event request written in natural language into a resource-aware plan, checks every constraint, and waits for a human before it locks resources.

Core flow: natural-language brief -> Gemini extraction -> specialist agents -> deterministic validation -> human approval -> time-slot locks -> live replanning.

## What is included

- Premium responsive command center built with plain HTML, CSS and JavaScript.
- Seven focused agents: Event Understanding, Schedule, Venue, People, Resource, Conflict and Coordinator.
- Gemini structured JSON extraction when `GEMINI_API_KEY` is set, with safe deterministic parsing if it is not.
- MongoDB persistence with Atlas preferred in production and a local MongoDB fallback for development.
- Role-based sign-in with a separate Administrator tab and a Faculty/Volunteer tab (with an ID-type toggle) on the same login screen.
- A dedicated **My CampusFlow** member workspace for faculty and volunteers: their profile, live availability status, running and upcoming campus events, their own event assignments with **Accept / Decline**, and a **monthly attendance** summary credited after completed events.
- An **admin-only** command center: AI-prompt event creation, the full resources graph with live available/assigned status for every resource type, the Data Manager (CRUD + image upload) for every campus record type, schedule, conflicts, agent network and audit trail.
- Time-slot locking for faculty, volunteers, guests, venues, labs, equipment and vehicles.
- Quantity-aware equipment, explainable matching scores, human approval, in-app notifications, optional SMTP assignment emails and audit trail.
- Dynamic replanning: simulate Lab C1 becoming unavailable, review a replacement plan, then approve or reject it.

No React, Tailwind, Node.js, maps, SMS, calendars, or external notification services are required.

## Stack and architecture

- Frontend: HTML, CSS and JavaScript
- Backend: Python and Flask
- Database: MongoDB Atlas or local MongoDB via PyMongo
- AI: Gemini API, optional
- Email: SMTP, optional. Assignment emails are sent only after a valid plan is approved and locked.

The Event Orchestrator invokes specialist agents. The constraint engine is always the final authority for date permissions, capacity, software, time overlaps, workloads and equipment quantities. Gemini never decides resource availability.

## Run locally

1. Install Python 3.10 or newer and open a terminal in this project folder.
2. Create and activate a virtual environment.

   Windows PowerShell: `py -m venv .venv` then `.\.venv\Scripts\Activate.ps1`

   macOS/Linux: `python3 -m venv .venv` then `source .venv/bin/activate`

3. Install the packages: `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and add your values.
5. Start the project: `flask --app app run --debug`
6. Open `http://127.0.0.1:5000`.

CampusFlow tries MongoDB Atlas first when `MONGO_URI` is configured. If Atlas is absent or unavailable, it connects to `LOCAL_MONGO_URI` (default: `mongodb://127.0.0.1:27017`) and creates/uses the `campusflow_ai` database. New databases start empty. If neither database is reachable, CampusFlow uses temporary in-memory storage, which is cleared when the app restarts.

## Sign-in roles

The sign-in screen has two tabs: **Faculty / Volunteer** (with a Volunteer/Faculty ID-type toggle) and **Administrator**. Change the development credentials in `.env` before deploying.

- **Admin:** open the *Administrator* tab and sign in with `ADMIN_USERNAME` and `ADMIN_PASSWORD`. Admins can create events from an AI prompt, approve or reject plans, and add, edit, upload images, or import CSV records through Data Manager. Admins are the only accounts that can add events or campus resources.
- **Faculty:** open the *Faculty / Volunteer* tab, choose **Faculty**, and sign in with the faculty ID added through Data Manager and `DEFAULT_MEMBER_PASSWORD`.
- **Volunteer:** open the *Faculty / Volunteer* tab, choose **Volunteer**, and sign in with the volunteer ID added through Data Manager and `DEFAULT_MEMBER_PASSWORD`.

Faculty and volunteers land on **My CampusFlow**, a member-only workspace showing:

- Their **profile** (name, department, photo if uploaded) and current **status** — Available, Response needed, or Assigned.
- **Running events** happening right now and **upcoming events**, campus-wide.
- Their own **event assignments**, each with **Accept** / **Decline** buttons while a response is pending. Accepting confirms they are assigned; declining leaves the assignment open for the admin to review.
- **Monthly attendance**: every *accepted* assignment earns a fixed 25 points only after its event is marked completed, totalled per calendar month and overall. This applies identically to faculty and volunteers.

The server enforces this: faculty and volunteer sessions can only reach their own availability, their own event feed, and responding to their own assignments — every other API endpoint (resources, data manager, schedule, conflicts, agents, audit) returns `403` for non-admin accounts. Default local development values are `admin` / `admin123` and member password `campus123`.

## MongoDB setup

### Local MongoDB

1. Install and start MongoDB Community Edition (the default Windows service is supported).
2. In `.env`, use `LOCAL_MONGO_URI=mongodb://127.0.0.1:27017` and optionally set `MONGO_DB_NAME=campusflow_ai`.
3. Start CampusFlow. The database starts empty; records you add through Data Manager persist across restarts.
4. Open `http://127.0.0.1:5000/health` to confirm `"mode": "local"`.

### MongoDB Atlas

1. Create a MongoDB Atlas cluster, database user and Network Access entry for your IP.
2. Copy the Atlas Python SRV string from Connect -> Drivers.
3. Put it in `.env` as `MONGO_URI=mongodb+srv://YOUR_USER:YOUR_PASSWORD@YOUR_CLUSTER.mongodb.net/campusflow_ai?retryWrites=true&w=majority`.
4. Add long random values for `SECRET_KEY`, `ADMIN_PASSWORD` and `DEFAULT_MEMBER_PASSWORD`.
5. Start CampusFlow, sign in as an administrator, and add your campus records in Data Manager. Each record type has a CSV template you can download and import.

If an older database still contains sample records, run `flask --app app clear-data` and confirm the prompt. This permanently clears all CampusFlow records and recreates only the configured administrator account.

## Gemini setup

Create an API key in Google AI Studio and set `GEMINI_API_KEY=your-key` in `.env`. It is server-only and never sent to the browser. If Gemini fails, times out or returns invalid JSON, CampusFlow still creates a plan using deterministic requirement extraction.

## Email setup

To deliver assignment emails, add `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` and `SMTP_USE_TLS` to `.env`. Add an **Email** address to faculty, volunteer and guest records. If SMTP or an email address is missing, the app keeps the in-app mailbox notification and skips external delivery. Emails are never sent for draft, invalid or unapproved plans.

## Admin workflow

1. Sign in as an administrator (Administrator tab), then open **Create event** and describe the event in a prompt. This AI prompt is the only way an event is created — there is no manual event form.
2. Review the live agent workflow and constraint checks, then open the event's **command center**.
3. Choose **Approve and lock**. Assignment records are created for every selected lab, venue, faculty member, volunteer, guest, equipment item and vehicle. Only after this successful approval are in-app assignment notices and optional SMTP emails sent. Faculty and volunteer assignments start as *pending* until that person accepts or declines them from their own **My CampusFlow** screen.
4. Open **Resources** to see every campus resource type with a live **Available now** / **Assigned** badge, calculated from active time-slot assignments — never a manual toggle.
5. Open **Data manager** to add or edit faculty, volunteers, guests, blocks, labs, venues, equipment, vehicles and academic-calendar records. Download the matching CSV template to import records in bulk; required fields are checked before any CSV rows are saved. The Academic calendar tab can also read a clearly dated timetable image with Gemini Vision, show the recognized working and holiday days for review, and then save them. IDs can be generated automatically, and each record supports an optional image upload.
6. Click **Simulate resource unavailable** on an approved event. This writes a time-bounded outage assignment for Lab C1; it never flips a global availability field.
7. CampusFlow proposes alternatives, rechecks capacity, software, people and equipment, and explains what changed. Approve the new plan — old locks are released, new locks are created, and the audit log records the change.

## Resource locking

There is no global `available=true/false` flag. Each approved plan writes assignment documents with `resource_id`, `event_id`, `resource_type`, `start_datetime`, `end_datetime`, `assignment_type`, `quantity` and `status`. Faculty and volunteer assignments additionally carry `acceptance` (`pending` / `accepted` / `declined`).

Availability uses the exact rule: `existing_start < requested_end AND existing_end > requested_start`.

For equipment, all overlapping locked quantities are subtracted from `total_quantity`. For people, the same overlap rule and daily workload limits are checked. The app validates again immediately before approval, so a changed plan cannot be locked.

## REST endpoints

- `POST /api/events` creates an event brief.
- `GET /api/events` and `GET /api/events/<id>` return events.
- `POST /api/events/<id>/plan` generates a validated proposal.
- `POST /api/events/<id>/approve` revalidates and locks a plan.
- `POST /api/events/<id>/complete` marks an ended approved event complete and credits attendance/event counts for accepted participants.
- `POST /api/events/<id>/recheck-resources/labs` or `/venues` separately recalculates the best available lab or venue fit for the event slot.
- `POST /api/events/<id>/replan-timeline` regenerates the event timeline only when it is at least as complete as the current timeline.
- `POST /api/events/<id>/simulate-conflict` creates an outage and proposes a replan.
- `POST /api/events/<id>/replan`, `/approve-replan` and `/reject-replan` handle replanning decisions.
- `GET /api/resources`, `/api/faculty`, `/api/volunteers`, `/api/guests`, `/api/venues`, `/api/labs`, `/api/equipment`, `/api/vehicles` return resource data.
- `GET /api/availability?name=<name>&start_datetime=<iso>&end_datetime=<iso>` checks matching resource availability for a requested time.
- `GET`, `POST` and `PUT /api/data/<type>` list, manually create and edit data-manager records. `POST /api/data/<type>/csv` imports a validated CSV file. `POST /api/data/academic_calendar/scan-image` reads a timetable image with Gemini Vision, and `/image-import` saves the reviewed result. Supported types are `faculty`, `volunteers`, `guests`, `blocks`, `labs`, `venues`, `equipment`, `vehicles` and `academic_calendar`; write operations require an admin session.
- `POST /api/uploads` uploads a JPG, PNG, GIF or WebP image (5 MB maximum) for an admin-managed record.
- `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` provide session access for every role.
- `GET /api/auth/my-availability` returns the signed-in faculty/volunteer's profile, assignments (with acceptance status) and attendance summary.
- `GET /api/auth/my-events` returns a member-safe feed of currently running and upcoming approved events.
- `POST /api/auth/assignments/<assignment_id>/respond` lets a faculty/volunteer accept or decline their own assignment (`{"decision": "accept"}` or `{"decision": "decline"}`).
- `GET /api/campus/blocks`, `/api/campus/blocks/<id>/labs`, `/api/dashboard`, `/api/schedule`, `/api/conflicts`, `/api/audit`, `/api/notifications` and `/api/agents` supply the admin-only operations views. `DELETE /api/notifications` clears all app notifications.

## Deploy to Render (easy English)

For the complete one-time local MongoDB to Atlas migration and Render checklist, see [DEPLOY_RENDER.md](DEPLOY_RENDER.md).

1. Put this project in GitHub. Do not upload `.env`.
2. In MongoDB Atlas Network Access, allow Render to connect. For a temporary test, `0.0.0.0/0` works; restrict it for a real production project.
3. At render.com, click **New +**, then **Web Service**. Connect GitHub and choose the repository.
4. Select **Python 3**. Use `pip install -r requirements.txt` as the Build Command and `gunicorn app:app` as the Start Command.
5. In Render Environment, add `MONGO_URI`, `GEMINI_API_KEY`, `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD` and `DEFAULT_MEMBER_PASSWORD`.
6. `gunicorn==23.0.0` is already listed in `requirements.txt`.
7. Create the Web Service and open its Render URL when the build finishes.
8. Open Data Manager after deployment and import your campus CSV files, or add records individually.

## Campus images

The app intentionally uses no generic stock photography. Put supplied real campus photos in `static/images/` using the names described in [static/images/README.md](static/images/README.md). The visual placeholders preserve the exact card and lab-detail structure until those assets are added.

## Project layout

- `agents/` has specialist planning agents and the orchestrator.
- `services/` has availability, matching, constraints, Gemini and audit logic.
- `database/` has the MongoDB adapter and empty collection definitions.
- `routes/` has the clean JSON API blueprints, including the member-facing endpoints in `routes/auth.py`.
- `templates/index.html` is the single-page app shell: the role-based login screen, the admin command center views, and the **My CampusFlow** member view.
- `static/css/style.css` and `static/css/data-manager.css` are the responsive visual system, including the login tabs and member dashboard styling.
- `static/js/app.js` is framework-free client behavior.

## Security and error handling

Secrets stay in environment variables, prompts are validated server-side, and the API returns meaningful JSON errors for missing events, invalid plans and changed constraints. Atlas and Gemini failures fall back safely for local development. Audit records never include API keys or secrets. Every non-authentication API route enforces the signed-in role server-side, independent of what the browser UI shows.
