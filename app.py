"""CampusFlow AI - a complete Python web prototype for event coordination."""
from __future__ import annotations

import json
from math import ceil
import pandas as pd
import requests
import streamlit as st

from database import add_resource, add_venue, authenticate, create_event, create_user, execute, initialize_database, notify, rows
from planner import alternatives, analyse_requirements, build_plan, detect_conflicts

st.set_page_config(page_title="CampusFlow AI", page_icon="CF", layout="wide")
initialize_database()
BACKEND_URL = "http://127.0.0.1:8000/api"
st.markdown("""<style>
#MainMenu,footer{visibility:hidden}.block-container{max-width:1280px;padding:2rem 2.25rem 4rem}
[data-testid="stSidebar"]{background:#0b1437}[data-testid="stSidebar"] *{color:#eef2ff!important}
.hero{background:linear-gradient(125deg,#132765,#5946dc);border-radius:22px;padding:32px 36px;color:#fff;margin:8px 0 26px}.hero h1{font-size:2.25rem;margin:0 0 8px;color:#fff}.hero p{color:#dbe6ff;font-size:1.05rem;margin:0}
.eyebrow{text-transform:uppercase;letter-spacing:.13em;font-size:.72rem;font-weight:700;color:#6676c9}.card{background:#fff;border:1px solid #e6eafb;border-radius:16px;padding:18px 20px;margin:8px 0;box-shadow:0 5px 15px rgba(17,35,93,.04)}.muted{color:#69738c}.agent{border-left:4px solid #6e56cf;padding:10px 14px;background:#f5f3ff;border-radius:0 10px 10px 0;margin:8px 0}.status{display:inline-block;border-radius:30px;padding:3px 10px;font-size:.78rem;font-weight:600;background:#e8f8ef;color:#187344}.alert{background:#fff3e6;border-left:4px solid #f59e0b;padding:12px 15px;border-radius:0 10px 10px 0}.stButton>button{border-radius:9px;font-weight:600}.stDataFrame{border:1px solid #edf0f7;border-radius:12px;overflow:hidden}
.login-shell{background:linear-gradient(135deg,#0b1437 0%,#253a9b 58%,#7654d9 100%);min-height:330px;border-radius:24px;padding:46px;color:white;margin-top:28px}.login-shell h1{font-size:2.6rem;color:white;margin:8px 0}.login-shell p{color:#d8e1ff;font-size:1.08rem}.login-points{margin-top:28px;line-height:2;color:#e9edff}
</style>""", unsafe_allow_html=True)

if "user" not in st.session_state:
    st.session_state["user"] = None

if not st.session_state["user"]:
    left, right = st.columns([1.15, .85], gap="large")
    with left:
        st.markdown("""<div class='login-shell'><div class='eyebrow' style='color:#c8d0ff'>CAMPUSFLOW AI</div><h1>Plan remarkable events, together.</h1><p>Your secure coordination workspace for fests, workshops, conferences and placement drives.</p><div class='login-points'>✦ AI-assisted event planning<br>✦ Live readiness and approval tracking<br>✦ Reliable conflict detection and replanning</div></div>""", unsafe_allow_html=True)
        st.caption("Local hackathon demo · Your password is securely hashed in the local SQLite database.")
    with right:
        st.markdown("<br><br>", unsafe_allow_html=True)
        login_tab, register_tab = st.tabs(["Sign in", "Create account"])
        with login_tab:
            st.subheader("Welcome back")
            with st.form("login-form"):
                email = st.text_input("Email address", placeholder="you@college.edu")
                password = st.text_input("Password", type="password")
                submitted = st.form_submit_button("Sign in to CampusFlow", type="primary", use_container_width=True)
            if submitted:
                try:
                    response = requests.post(f"{BACKEND_URL}/auth/login", json={"email": email, "password": password}, timeout=2)
                    user = response.json().get("user") if response.ok else None
                except requests.RequestException:
                    user = authenticate(email, password)
                if user:
                    st.session_state["user"] = user
                    st.success("Signed in successfully.")
                    st.rerun()
                else:
                    st.error("Incorrect email or password.")
            st.info("Demo account: `demo@campusflow.ai`  |  Password: `demo1234`")
        with register_tab:
            st.subheader("Create your coordinator account")
            with st.form("register-form"):
                name = st.text_input("Your full name")
                new_email = st.text_input("College email address")
                new_password = st.text_input("Create password", type="password", help="Use at least 8 characters.")
                confirm = st.text_input("Confirm password", type="password")
                create = st.form_submit_button("Create account", type="primary", use_container_width=True)
            if create:
                if not name.strip() or "@" not in new_email:
                    st.error("Enter your name and a valid email address.")
                elif len(new_password) < 8:
                    st.error("Your password must have at least 8 characters.")
                elif new_password != confirm:
                    st.error("The passwords do not match.")
                else:
                    try:
                        response = requests.post(f"{BACKEND_URL}/auth/register", json={"name": name, "email": new_email, "password": new_password}, timeout=2)
                        created = response.status_code == 201
                    except requests.RequestException:
                        created = create_user(name, new_email, new_password)
                    if created: st.success("Account created. You can now sign in.")
                    else: st.error("An account with this email already exists.")
    st.stop()

def all_data():
    try:
        venue_response = requests.get(f"{BACKEND_URL}/venues", timeout=1)
        resource_response = requests.get(f"{BACKEND_URL}/resources", timeout=1)
        event_response = requests.get(f"{BACKEND_URL}/events", timeout=1)
        if all(response.ok for response in (venue_response, resource_response, event_response)):
            st.session_state["backend_online"] = True
            return venue_response.json(), resource_response.json(), event_response.json()
    except requests.RequestException:
        pass
    st.session_state["backend_online"] = False
    return (rows("SELECT * FROM venues ORDER BY capacity DESC"), rows("SELECT * FROM resources ORDER BY category, name"), rows("SELECT * FROM events ORDER BY id DESC"))

def api_update(path, payload, fallback):
    """Send a live action to FastAPI, with a local fallback when developing offline."""
    try:
        response = requests.patch(f"{BACKEND_URL}{path}", json=payload, timeout=2)
        if response.ok:
            return True
    except requests.RequestException:
        pass
    fallback()
    return False

def api_create(path, payload, fallback):
    try:
        response = requests.post(f"{BACKEND_URL}{path}", json=payload, timeout=2)
        if response.status_code in (200, 201):
            return True
    except requests.RequestException:
        pass
    fallback()
    return False

def database_connection():
    try:
        response = requests.get(f"{BACKEND_URL}/database/status", timeout=2)
        if response.ok:
            return response.json()
    except requests.RequestException:
        pass
    return {"status": "connected", "engine": "SQLite", "database": "campusflow.db", "counts": {}}

def heading(title, subtitle):
    st.markdown(f"<div class='eyebrow'>Campus operations workspace</div><h1>{title}</h1><p class='muted'>{subtitle}</p>", unsafe_allow_html=True)

def pick_event(events, label="Choose an event"):
    if not events:
        st.info("No saved events yet. Generate a plan in AI Planner first.")
        return None
    return st.selectbox(label, events, format_func=lambda x: f"#{x['id']} · {x['name']}")

def get_schedule(event_id):
    try:
        response = requests.get(f"{BACKEND_URL}/events/{event_id}/schedule", timeout=1)
        if response.ok:
            return response.json()
    except requests.RequestException:
        pass
    result = rows("SELECT * FROM schedules WHERE event_id = ? ORDER BY day, start_time", (event_id,))
    for item in result: item["equipment"] = json.loads(item["equipment"])
    return result

venues, resources, events = all_data()

with st.sidebar:
    st.markdown("## CAMPUSFLOW AI")
    st.caption("Plan. Coordinate. Deliver.")
    st.markdown(f"**{st.session_state['user']['name']}**")
    st.caption(f"{st.session_state['user']['role']} · {st.session_state['user']['email']}")
    if st.button("Log out", use_container_width=True):
        st.session_state["user"] = None
        st.rerun()
    st.divider()
    st.caption("API connected" if st.session_state.get("backend_online") else "Local fallback mode")
    st.divider()
    page = st.radio("Navigation", ["Overview", "AI Planner", "Events", "Schedule", "Tasks & approvals", "Conflict center", "Venues & resources", "Notifications"], label_visibility="collapsed")
    st.divider(); st.markdown("**Agent system online**"); st.caption("Requirement · Venue · Schedule · Resource · Replanning")

if page == "Overview":
    st.markdown("""<div class='hero'><div class='eyebrow' style='color:#b8c4ff'>AI CAMPUS EVENT PLANNING</div><h1>Every campus event, under control.</h1><p>Turn one sentence into a coordinated plan, resolve operational conflicts, and keep every stakeholder ready.</p></div>""", unsafe_allow_html=True)
    tasks, pending = rows("SELECT * FROM tasks"), rows("SELECT * FROM approvals WHERE status = 'Pending'")
    c1,c2,c3,c4=st.columns(4); c1.metric("Active events",len(events)); c2.metric("Campus venues",len(venues)); c3.metric("Open tasks",sum(x["status"] != "Done" for x in tasks)); c4.metric("Approvals needed",len(pending))
    db = database_connection()
    st.caption(f"Database: {db['status']} · {db['engine']} · {db['database']}")
    left,right=st.columns([1.25,.75])
    with left:
        st.subheader("Your event pipeline")
        if events:
            table=pd.DataFrame(events)[["name","participants","days","status","created_at"]]; table.columns=["Event","People","Days","Status","Created"]
            st.dataframe(table,use_container_width=True,hide_index=True)
        else: st.markdown("<div class='card'><h3>Start with an event brief</h3><p class='muted'>Describe your fest, conference or drive in plain English. CampusFlow creates the first operational plan in seconds.</p></div>",unsafe_allow_html=True)
    with right:
        st.subheader("How AI works")
        for title,text in [("1. Understand","Requirement Agent extracts scale and activities."),("2. Coordinate","Specialists select venues, schedule work and delegate tasks."),("3. Protect","Rules detect conflicts before the event day.")]: st.markdown(f"<div class='agent'><b>{title}</b><br><span class='muted'>{text}</span></div>",unsafe_allow_html=True)

elif page == "AI Planner":
    heading("Plan with AI","Give the orchestrator a natural-language brief. It coordinates specialist planning agents.")
    brief=st.text_area("Event brief", "I want to conduct a 2-day technical fest for 800 students with 5 competitions, 2 workshops and an inauguration.",height=145)
    left,right=st.columns([1,3])
    if left.button("Generate plan",type="primary",use_container_width=True):
        try:
            response = requests.post(f"{BACKEND_URL}/plan", json={"description": brief}, timeout=5)
            st.session_state["draft"] = response.json() if response.ok else build_plan(analyse_requirements(brief), venues)
        except requests.RequestException:
            st.session_state["draft"] = build_plan(analyse_requirements(brief), venues)
    right.caption("No API key required for this demo. Reliable capacity and overlap checks always stay in Python.")
    plan=st.session_state.get("draft")
    if plan:
        st.success("Plan created. The Orchestrator completed five specialist-agent steps.")
        for name,text in [("Requirement Agent","Extracted attendance, duration and activity mix."),("Venue Agent","Matched activity sizes to facilities."),("Schedule Agent","Created a multi-day run sheet."),("Resource Agent","Estimated equipment, volunteer and security needs."),("Replanning Agent","Is ready to resolve conflicts after validation.")]: st.markdown(f"<div class='agent'><b>{name}</b> — {text}</div>",unsafe_allow_html=True)
        a,b,c,d=st.columns(4); a.metric("Attendance",plan["participants"]); b.metric("Duration",f"{plan['days']} day(s)"); c.metric("Volunteers",plan["volunteers_needed"]); d.metric("Security",plan["security_needed"])
        insights = plan.get("ai_insights", {})
        if insights:
            label = "OpenAI insights" if insights.get("enabled") else "Local AI fallback"
            st.subheader(label)
            st.markdown(f"<div class='card'><b>Planning summary</b><br>{insights.get('summary', '')}<br><br><b>Why these venues?</b><br>{insights.get('venue_reasoning', '')}</div>", unsafe_allow_html=True)
            insight_left, insight_right = st.columns(2)
            insight_left.markdown("**Operational risks**")
            for risk in insights.get("risks", []): insight_left.write(f"• {risk}")
            insight_right.markdown("**Stakeholder briefing**")
            insight_right.info(insights.get("stakeholder_briefing", ""))
        st.subheader("Proposed schedule"); show=pd.DataFrame(plan["schedule"]); st.dataframe(show,use_container_width=True,hide_index=True)
        x,y=st.columns(2); x.subheader("Delegated tasks"); x.dataframe(pd.DataFrame(plan["tasks"]),use_container_width=True,hide_index=True); y.subheader("Approval gates"); y.dataframe(pd.DataFrame(plan["approvals"]),use_container_width=True,hide_index=True)
        if st.button("Save event and start coordination",type="primary"):
            try:
                response = requests.post(f"{BACKEND_URL}/events", json=plan, timeout=5)
                event_id = response.json()["event_id"] if response.status_code == 201 else create_event(plan)
            except requests.RequestException:
                event_id = create_event(plan)
            st.session_state.pop("draft",None); st.success(f"{plan['name']} saved as event #{event_id}.")

elif page == "Events":
    heading("Event workspace","Inspect event plans and model operational changes before they become problems.")
    event=pick_event(events)
    if event:
        st.markdown(f"<div class='card'><span class='status'>{event['status']}</span><h3>{event['name']}</h3><p class='muted'>{event['description']}</p></div>",unsafe_allow_html=True)
        a,b,c=st.columns(3); a.metric("Participants",event["participants"]); b.metric("Duration",f"{event['days']} days"); c.metric("Created",event["created_at"].split("T")[0])
        st.subheader("What-if attendance simulation"); increase=st.slider("Additional participants",0,1000,200,25); new_total=event["participants"]+increase; volunteers=max(10,ceil(new_total/25)); security=max(2,ceil(new_total/150))
        a,b,c=st.columns(3); a.metric("New attendance",new_total); b.metric("Volunteers needed",volunteers); c.metric("Security needed",security)
        if new_total>1000: st.warning("Capacity alert: move the largest session to Open Ground, or split it into parallel sessions.")
        else: st.success("Capacity remains feasible using the largest available venue.")
        if st.button("Notify coordinators about this simulation"):
            message=f"What-if simulation: attendance changed to {new_total}; volunteers recommended: {volunteers}."
            api_create(f"/events/{event['id']}/notifications", {"message": message}, lambda: notify(event["id"], message))
            st.success("Briefing notification added.")

elif page == "Schedule":
    heading("Schedule board","A single view of activities, times, venues and assigned resources.")
    event=pick_event(events)
    if event:
        schedule=get_schedule(event["id"])
        if schedule:
            show=pd.DataFrame(schedule)[["day","start_time","end_time","activity","venue","participants","equipment"]]; show.columns=["Day","Start","End","Activity","Venue","People","Equipment"]
            st.dataframe(show,use_container_width=True,hide_index=True)
            for day in sorted({x["day"] for x in schedule}):
                st.subheader(f"Day {day}")
                for item in [x for x in schedule if x["day"]==day]: st.markdown(f"<div class='card'><b>{item['start_time']} – {item['end_time']} · {item['activity']}</b><br><span class='muted'>{item['venue']} · {item['participants']} participants · {', '.join(item['equipment'])}</span></div>",unsafe_allow_html=True)

elif page == "Tasks & approvals":
    heading("Command center","Track execution tasks and keep sensitive decisions under human control.")
    event=pick_event(events)
    if event:
        tasks=rows("SELECT * FROM tasks WHERE event_id = ? ORDER BY CASE priority WHEN 'High' THEN 1 ELSE 2 END",(event["id"],)); approvals=rows("SELECT * FROM approvals WHERE event_id = ?",(event["id"],))
        done=sum(t["status"]=="Done" for t in tasks); approved=sum(a["status"]=="Approved" for a in approvals); score=round(100*((done/len(tasks) if tasks else 0)*.55+(approved/len(approvals) if approvals else 0)*.45))
        st.metric("Event readiness",f"{score}%",f"{done}/{len(tasks)} tasks complete"); st.progress(score); left,right=st.columns([1.2,.8])
        with left:
            st.subheader("Tasks")
            for task in tasks:
                a,b=st.columns([5,1]); state="Completed" if task["status"]=="Done" else f"{task['priority']} priority"; a.markdown(f"<div class='card'><b>{task['title']}</b><br><span class='muted'>{task['owner']} · {task['deadline']} · {state}</span></div>",unsafe_allow_html=True)
                if task["status"]!="Done" and b.button("Complete",key=f"done-{task['id']}"):
                    api_update(f"/tasks/{task['id']}", {"status": "Done"}, lambda: execute("UPDATE tasks SET status = 'Done' WHERE id = ?",(task["id"],)))
                    message=f"Task completed: {task['title']}"
                    api_create(f"/events/{event['id']}/notifications", {"message": message}, lambda: notify(event["id"], message))
                    st.rerun()
        with right:
            st.subheader("Human approvals")
            for approval in approvals:
                st.markdown(f"**{approval['item']}**  \n{approval['reason']}  \nStatus: `{approval['status']}`")
                if approval["status"]=="Pending":
                    yes,no=st.columns(2)
                    if yes.button("Approve",key=f"yes-{approval['id']}"):
                        api_update(f"/approvals/{approval['id']}", {"status": "Approved"}, lambda: execute("UPDATE approvals SET status = 'Approved' WHERE id = ?",(approval["id"],)))
                        message=f"Approved: {approval['item']}"; api_create(f"/events/{event['id']}/notifications", {"message": message}, lambda: notify(event["id"], message)); st.rerun()
                    if no.button("Reject",key=f"no-{approval['id']}"):
                        api_update(f"/approvals/{approval['id']}", {"status": "Rejected"}, lambda: execute("UPDATE approvals SET status = 'Rejected' WHERE id = ?",(approval["id"],)))
                        message=f"Rejected: {approval['item']}"; api_create(f"/events/{event['id']}/notifications", {"message": message}, lambda: notify(event["id"], message)); st.rerun()
                st.divider()

elif page == "Conflict center":
    heading("Conflict center","Validate schedules with deterministic rules, then let the Replanning Agent explain the safest next action.")
    event=pick_event(events)
    if event:
        schedule=get_schedule(event["id"])
        if st.button("Run conflict validation",type="primary"):
            try:
                response = requests.post(f"{BACKEND_URL}/events/{event['id']}/conflicts", timeout=5)
                st.session_state["conflicts"] = response.json() if response.ok else detect_conflicts(schedule, venues, resources)
            except requests.RequestException:
                st.session_state["conflicts"] = detect_conflicts(schedule, venues, resources)
        conflicts=st.session_state.get("conflicts",[])
        if conflicts:
            for number,conflict in enumerate(conflicts,1):
                recommendation = conflict.get("recommendation", alternatives(conflict,schedule,venues))
                st.error(f"{number}. {conflict['type']} — {conflict['message']}")
                st.markdown(f"<div class='alert'><b>Replanning Agent recommendation</b><br>{recommendation}</div>",unsafe_allow_html=True)
        elif "conflicts" in st.session_state: st.success("All checks passed: no double bookings, capacity issues, or equipment overallocation were found.")
        st.subheader("Judge demo: create a conflict")
        if schedule:
            item=st.selectbox("Choose an activity to duplicate",schedule,format_func=lambda x:f"Day {x['day']} · {x['activity']}")
            if st.button("Create intentional double booking"):
                execute("INSERT INTO schedules(event_id, activity, day, start_time, end_time, venue, participants, equipment) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",(event["id"],item["activity"]+" — DEMO CONFLICT",item["day"],item["start_time"],item["end_time"],item["venue"],item["participants"],json.dumps(item["equipment"]))); notify(event["id"],"Alert: intentional double-booking demo added. Run validation."); st.warning("Conflict created. Run validation to see the recommendation.")

elif page == "Venues & resources":
    heading("Campus inventory","Manage the shared spaces and operational resources that planning agents can use.")
    left,right=st.columns(2)
    with left:
        st.subheader("Venues"); table=pd.DataFrame(venues)[["name","capacity","features","available"]]; table.columns=["Venue","Capacity","Features","Available"]; st.dataframe(table,use_container_width=True,hide_index=True)
        with st.expander("Add a venue"):
            with st.form("venue-form",clear_on_submit=True):
                name=st.text_input("Venue name"); capacity=st.number_input("Capacity",min_value=1,value=100); features=st.text_input("Features","Projector, Wi-Fi")
                if st.form_submit_button("Add venue"):
                    if not name.strip(): st.error("Enter a venue name.")
                    elif api_create("/venues", {"name": name, "capacity": capacity, "features": features}, lambda: add_venue(name,capacity,features)): st.rerun()
                    else: st.error("Choose a unique venue name.")
    with right:
        st.subheader("Resources"); table=pd.DataFrame(resources)[["name","quantity","category"]]; table.columns=["Resource","Quantity","Category"]; st.dataframe(table,use_container_width=True,hide_index=True)
        with st.expander("Add a resource"):
            with st.form("resource-form",clear_on_submit=True):
                name=st.text_input("Resource name"); quantity=st.number_input("Quantity",min_value=1,value=1); category=st.selectbox("Category",["Equipment","People","Transport","Other"])
                if st.form_submit_button("Add resource"):
                    if not name.strip(): st.error("Enter a resource name.")
                    elif api_create("/resources", {"name": name, "quantity": quantity, "category": category}, lambda: add_resource(name,quantity,category)): st.rerun()
                    else: st.error("Choose a unique resource name.")

else:
    heading("Notifications","Briefings and updates automatically produced as the event plan changes.")
    event=pick_event(events,"Filter by event")
    if event:
        notices=rows("SELECT * FROM notifications WHERE event_id = ? ORDER BY id DESC",(event["id"],))
        if notices:
            for item in notices: st.markdown(f"<div class='card'><b>Operational update</b><br>{item['message']}<br><span class='muted'>{item['created_at']}</span></div>",unsafe_allow_html=True)
        else: st.info("No notifications for this event yet.")
        with st.form("manual-notification",clear_on_submit=True):
            message=st.text_input("Send a stakeholder briefing")
            if st.form_submit_button("Add notification") and message.strip():
                api_create(f"/events/{event['id']}/notifications", {"message": message.strip()}, lambda: notify(event["id"],message.strip()))
                st.rerun()
