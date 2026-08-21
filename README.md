# CampusFlow AI

A beginner-friendly, all-Python Streamlit prototype for the **AI Campus Event Planning & Coordination Agent** hackathon problem.

## What it demonstrates

- Natural-language requirement extraction (rule-based Requirement Agent)
- An orchestrator coordinating venue, schedule, resource, task, and replanning agents
- Persistent SQLite storage for events, venues, resources, schedules, tasks, approvals, and notifications
- Reliable Python checks for venue capacity, overlapping double bookings, and resource over-allocation
- Human approval queue, readiness score, task tracker, and attendance what-if simulation

## Run locally

Open PowerShell in this project folder and run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks activation, run this once for the current PowerShell window, then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Open **two PowerShell terminals** in this project folder after activating `.venv` in each.

Terminal 1 - start the Python backend API:

```powershell
uvicorn backend:app --reload --port 8000
```

Terminal 2 - start the website frontend:

```powershell
streamlit run app.py
```

The website opens at `http://localhost:8501`. The backend interactive API documentation is at `http://127.0.0.1:8000/docs`.

## Demo for judges

1. Open **AI Planner** and generate/save the pre-filled technical-fest plan.
2. Open **Conflict Center**, add an intentional double booking, then check conflicts.
3. Use **Dashboard** to approve items and mark tasks done; the readiness score changes.
4. Use **Events** to run an attendance what-if simulation.

## Adding a real LLM later

CampusFlow is already prepared for the OpenAI API. Create a secret `.env` file beside `backend.py` by copying `.env.example`, then replace the placeholder:

```text
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-5.6
```

Create an API key in the OpenAI Platform dashboard, then restart the backend. The backend calls OpenAI only from Python; the browser never receives the key. OpenAI adds explanatory planning insights, venue reasoning, risks, and a stakeholder briefing. The app's deterministic validation remains in Python because capacity and overlap checks must be reliable.
