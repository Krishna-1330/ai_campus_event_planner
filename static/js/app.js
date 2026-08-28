/* CampusFlow AI client: no framework, no external integrations. */
const state = { currentView: 'login', eventId: null, resourcesType: 'faculty', venuesType: 'venues', dataType: 'faculty', notifications: [], currentEvent: null, user: null, dataRecords: [], dataEdit: null, calendarImageRecords: [], loginTab: 'staff', staffRole: 'volunteer', dashboardEvent: null, dataContext: 'resources' };
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const esc = (value = '') => String(value).replace(/[&<>'"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
const nice = value => String(value || '').replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
const compactDate = value => value ? new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : 'Unscheduled';
const compactTime = value => value ? new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—';

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  const data = await response.json().catch(() => ({ ok: false, error: 'Unexpected server response.' }));
  if (response.status === 401 && !path.startsWith('/api/auth/')) showLogin(true);
  if (!response.ok) throw new Error(data.error || 'Something went wrong.');
  return data;
}
function toast(message, kind = '') {
  const item = document.createElement('div'); item.className = `toast ${kind}`; item.textContent = message;
  $('#toast-area').append(item); setTimeout(() => item.remove(), 4200);
}
function delay(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

function navigate(view) {
  if (!state.user && view !== 'login') { showLogin(); return; }
  const memberViews = new Set(['member-dashboard', 'profile', 'attendance']);
  const organizerViews = new Set(['dashboard', 'create', 'planning', 'event', 'profile']);
  const adminViews = new Set(['dashboard', 'create', 'planning', 'event', 'resources', 'venues', 'data', 'schedule', 'campus', 'conflicts', 'agents', 'audit']);
  if (state.user?.role === 'admin' && memberViews.has(view)) view = 'dashboard';
  if (state.user?.role === 'organizer' && !organizerViews.has(view)) view = 'dashboard';
  if (state.user && !['admin', 'organizer'].includes(state.user.role) && !memberViews.has(view)) view = 'member-dashboard';
  if (state.user?.role === 'admin' && !adminViews.has(view)) view = 'dashboard';
  state.currentView = view;
  $$('.view').forEach(el => el.classList.toggle('active', el.id === `view-${view}`));
  $$('nav a').forEach(el => el.classList.toggle('active', el.dataset.view === view));
  window.location.hash = view;
  const loaders = { dashboard: loadDashboard, schedule: loadSchedule, resources: loadResources, venues: loadVenues, data: loadDataManager, campus: loadCampus, conflicts: loadConflicts, agents: loadAgents, audit: loadAudit, event: loadEvent, 'member-dashboard': loadMemberDashboard, profile: loadMemberProfile, attendance: loadMemberAttendance };
  if (loaders[view]) loaders[view]().catch(error => toast(error.message, 'error'));
}

async function initialize() {
  try {
    const session = await api('/api/auth/me');
    if (!session.authenticated) { showLogin(false); return; }
    applySession(session.user);
    if (session.user.role === 'organizer') { navigate('dashboard'); return; }
    if (session.user.role !== 'admin') { await loadMemberMailbox(); navigate('member-dashboard'); return; }
    const dashboard = await api('/api/dashboard');
    $('#storage-mode').textContent = ({ memory: 'Temporary memory - not saved', local: 'Local MongoDB - connected', atlas: 'MongoDB Atlas - connected' }[dashboard.mode] || 'Connecting system...');
    renderDashboard(dashboard);
    await loadNotifications();
  } catch (error) { toast(`System connection: ${error.message}`, 'error'); }
  const destination = window.location.hash.slice(1);
  navigate(['dashboard','create','schedule','resources','venues','data','campus','conflicts','agents','audit','event','member-dashboard','profile','attendance'].includes(destination) ? destination : 'dashboard');
}

function showLogin(openLogin = false) {
  state.user = null;
  state.currentView = 'login';
  $('#landing-page').classList.add('visible');
  $('#app-shell').classList.remove('authenticated');
  $('#app-shell').classList.toggle('login-open', openLogin);
  $('#app-shell').hidden = !openLogin;
  $$('.view').forEach(el => el.classList.toggle('active', openLogin && el.id === 'view-login'));
  $$('nav a').forEach(el => el.classList.remove('active'));
  $$('[data-admin-only],[data-member-only],[data-event-manager-only],[data-organizer-only]').forEach(el => { el.hidden = true; });
  $('#profile-button').innerHTML = 'Sign in <span>Account</span>';
  $('#notification-panel').classList.remove('show');
  $('#mail-panel').classList.remove('show');
  if (openLogin) {
    window.location.hash = 'login';
    setLoginTab('staff');
    setStaffRole('volunteer');
    const form = $('#login-form'); if (form) form.reset();
  }
}

function setLoginTab(tab) {
  state.loginTab = tab;
  $$('[data-login-tab]').forEach(el => el.classList.toggle('active', el.dataset.loginTab === tab));
  $('#staff-role-toggle').style.display = tab === 'staff' ? 'flex' : 'none';
  if (tab === 'admin') {
    $('#username-label').firstChild.textContent = 'Admin username';
    $('#login-form [name="username"]').placeholder = 'e.g. admin';
    $('#login-note').textContent = 'Use the administrator username and password configured for CampusFlow.';
  } else {
    setStaffRole(state.staffRole);
  }
}
function setStaffRole(role) {
  state.staffRole = role;
  $$('[data-staff-role]').forEach(el => el.classList.toggle('active', el.dataset.staffRole === role));
  const label = role === 'faculty' ? 'Faculty' : role === 'organizer' ? 'Organizer' : 'Volunteer';
  $('#username-label').firstChild.textContent = `${label} ID`;
  $('#login-form [name="username"]').placeholder = role === 'faculty' ? 'Enter your faculty ID' : role === 'organizer' ? 'Enter your organizer ID' : 'Enter your volunteer ID';
  $('#login-note').textContent = `Use the ${label} ID and password supplied by your CampusFlow administrator.`;
}
function applySession(user) {
  state.user = user;
  const isAdmin = user.role === 'admin';
  const isOrganizer = user.role === 'organizer';
  $('#landing-page').classList.remove('visible');
  $('#app-shell').classList.remove('login-open');
  $('#app-shell').hidden = false;
  $('#app-shell').classList.add('authenticated');
  $$('[data-admin-only]').forEach(el => { el.hidden = !isAdmin; });
  $$('[data-event-manager-only]').forEach(el => { el.hidden = !(isAdmin || isOrganizer); });
  $$('[data-member-only]').forEach(el => { el.hidden = isAdmin || isOrganizer; });
  $$('[data-organizer-only]').forEach(el => { el.hidden = !isOrganizer; });
  $('#profile-button').innerHTML = `${esc(user.display_name)} <span>${nice(user.role)}</span>`;
}
async function signIn(form) {
  const button = form.querySelector('[type="submit"]'); button.disabled = true;
  try {
    const values = Object.fromEntries(new FormData(form).entries());
    const result = await api('/api/auth/login', { method: 'POST', body: JSON.stringify(values) });
    const expectedRole = state.loginTab === 'admin' ? 'admin' : state.staffRole;
    if (result.user.role !== expectedRole) {
      await api('/api/auth/logout', { method: 'POST' }).catch(() => {});
      const actualLabel = nice(result.user.role);
      toast(result.user.role === 'admin' ? 'That is an administrator account. Use the Administrator tab to sign in.' : `That ID belongs to a ${actualLabel} account. Select ${actualLabel} above and sign in again.`, 'error');
      return;
    }
    applySession(result.user);
    toast(`Signed in as ${nice(result.user.role)}.`);
    if (result.user.role === 'admin') loadNotifications().catch(error => toast(error.message, 'error'));
    else loadMemberMailbox().catch(error => toast(error.message, 'error'));
    navigate(['admin', 'organizer'].includes(result.user.role) ? 'dashboard' : 'member-dashboard');
  } catch (error) { toast(error.message, 'error'); }
  finally { button.disabled = false; }
}
async function signOut() {
  try { await api('/api/auth/logout', { method: 'POST' }); } catch (_) { /* The local view is still safely cleared. */ }
  showLogin(false);
}

function renderDashboard(data) {
  const metrics = [
    ['Active events', data.metrics.active_events, 'Plans in motion', 'teal'], ['Upcoming', data.metrics.upcoming_events, 'On the horizon', 'blue'],
    ['Resource utilization', `${data.metrics.resource_utilization}%`, 'Lock-aware capacity', 'purple'], ['Conflicts', data.metrics.conflicts, 'Needs attention', 'red'], ['Event readiness', `${data.metrics.readiness}%`, 'Average confidence', 'orange']
  ];
  $('#metric-grid').innerHTML = metrics.map(([label, value, note, color]) => `<article class="metric metric-${color}"><span class="label">${label}</span><strong>${value}</strong><small>${note}</small></article>`).join('');
  $('#active-events').innerHTML = data.events.length ? data.events.map(event => `<div class="event-row"><span class="event-icon">✦</span><span class="event-info"><b>${esc(event.title)}</b><span>${compactDate(event.start_datetime)} · ${compactTime(event.start_datetime)}${state.user?.role === 'admin' && event.organizer_name ? ` · ${esc(event.organizer_name)}` : ''}</span></span><span class="status ${event.status}">${nice(event.status)}</span><span class="event-row-actions"><button class="text-button event-open" data-id="${event.event_id}">Open</button><button class="text-button" data-action="edit-event" data-event-id="${event.event_id}">Edit</button></span></div>`).join('') : empty('No events yet', state.user?.role === 'organizer' ? 'Create your first organizer event.' : 'Use Create event to add your first event.');
  $('#activity-list').innerHTML = data.activity.length ? [...data.activity].reverse().map(row => `<div class="activity-item"><i>✦</i><div><b>${esc(row.action)}</b><span>${esc(row.details)}</span></div><time>${compactDate(row.timestamp)}</time></div>`).join('') : empty('No operational activity yet', 'Actions will appear here as plans are generated.');
}
async function loadDashboard() { renderDashboard(await api('/api/dashboard')); }

async function openDashboardEventEditor(eventId) {
  try {
    const data = await api(`/api/events/${eventId}`);
    state.dashboardEvent = data.event;
    const event = data.event;
    $('#dashboard-event-editor').innerHTML = `<article class="panel dashboard-editor"><div class="panel-title"><div><span class="label">EDIT EVENT</span><h3>${esc(event.title)}</h3></div><button class="text-button" data-action="close-event-editor">Close ×</button></div><form id="event-name-form" class="inline-form" data-event-id="${event.event_id}"><label>Event name<input name="title" maxlength="120" value="${esc(event.title)}" required></label><p>Changing the event name keeps its AI plan and resource checks intact.</p><div><button class="secondary" type="button" data-action="open-event" data-event-id="${event.event_id}">Open event plan</button><button class="primary" type="submit">Save event name</button></div></form></article>`;
    $('#dashboard-event-editor').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (error) { toast(error.message, 'error'); }
}

async function saveEventName(form) {
  const button = form.querySelector('[type="submit"]'); button.disabled = true;
  try {
    const result = await api(`/api/events/${form.dataset.eventId}`, { method: 'PUT', body: JSON.stringify({ title: new FormData(form).get('title') }) });
    toast(`Event renamed to ${result.event.title}.`);
    $('#dashboard-event-editor').innerHTML = '';
    await loadDashboard();
  } catch (error) { toast(error.message, 'error'); }
  finally { button.disabled = false; }
}

async function generatePlan() {
  const prompt = $('#event-prompt').value.trim();
  if (prompt.length < 12) { toast('Add a little more detail so the agents can build a reliable plan.', 'error'); return; }
  const button = $('#generate-plan'); button.disabled = true; button.textContent = 'Creating brief…';
  try {
    const created = await api('/api/events', { method: 'POST', body: JSON.stringify({ prompt }) });
    state.eventId = created.event.event_id;
    $('#planning-title').textContent = `Building ${created.event.title}`;
    $('#planning-subtitle').textContent = 'Specialists are translating your brief into a safe operational proposal.';
    $('#planning-result').innerHTML = '';
    renderWorkflow(['waiting','waiting','waiting','waiting','waiting','waiting','waiting']);
    navigate('planning');
    const planRequest = api(`/api/events/${state.eventId}/plan`, { method: 'POST' });
    for (let index = 0; index < 7; index++) { renderWorkflow(Array.from({ length: 7 }, (_, i) => i < index ? 'completed' : i === index ? 'working' : 'waiting')); await delay(340); }
    const result = await planRequest;
    renderWorkflow(result.workflow.map(agent => agent.status));
    renderPlanningResult(result);
    if (!result.ok) toast('The plan found a constraint conflict. Review the checks below.', 'error');
  } catch (error) { toast(error.message, 'error'); navigate('create'); }
  finally { button.disabled = false; button.innerHTML = 'Generate AI plan <b>✦</b>'; }
}
function renderWorkflow(statuses) {
  const labels = ['Event Understanding', 'Schedule Agent', 'Venue Agent', 'People Agent', 'Resource Agent', 'Conflict Agent', 'Coordinator'];
  $('#agent-workflow').innerHTML = labels.map((label, i) => `<article class="agent-step ${statuses[i] || 'waiting'}"><span class="agent-number">0${i + 1} · AGENT</span><span class="check">${statuses[i] === 'completed' ? '✓' : statuses[i] === 'conflict' ? '!' : statuses[i] === 'working' ? '◌' : '·'}</span><b>${label}</b><span>${statuses[i] === 'working' ? 'Analysing resources…' : statuses[i] === 'completed' ? 'Decision complete' : statuses[i] === 'conflict' ? 'Constraint attention' : 'Waiting for hand-off'}</span></article>`).join('');
}
function renderPlanningResult(result) {
  const validation = result.validation || { checks: [], errors: [] };
  const checks = validation.checks.map(check => `<span class="validation-chip ${check.passed ? '' : 'fail'}">${check.passed ? '✓' : '×'} ${esc(check.label)}</span>`).join('');
  const plan = result.plan;
  $('#planning-status-text').textContent = validation.valid ? 'PLAN READY' : 'CONFLICT FOUND';
  $('#planning-result').innerHTML = `<div class="plan-summary"><div><span class="status ${validation.valid ? 'approved' : 'conflict'}">${validation.valid ? 'Validated proposal' : 'Blocking conflicts'}</span><h3>${validation.valid ? 'A constraint-checked plan is ready for human approval.' : 'The AI could not reserve every requested resource at that time.'}</h3><p>${esc(result.explanation || validation.errors.join(' '))}</p></div>${validation.valid ? `<button class="primary" data-action="open-event">Review command center <b>→</b></button>` : `<button class="secondary" data-go="create">Revise & replan</button>`}</div><div class="validation-strip">${checks}</div>`;
}

async function loadEvent() {
  if (!state.eventId) { const list = await api('/api/events'); state.eventId = list.events.find(e => e.status !== 'approved')?.event_id || list.events[0]?.event_id; }
  if (!state.eventId) { $('#event-command').innerHTML = empty('No event selected', 'Create a brief to unlock the command center.'); return; }
  const data = await api(`/api/events/${state.eventId}`); state.currentEvent = data.event; renderEvent(data.event);
}
function items(group) { return group?.length ? group.map(item => `<div class="resource-line"><b>${esc(item.name || item.resource_id)}</b><span>${item.score ? `${item.score}% match` : item.quantity > 1 ? `${item.quantity} units` : nice(item.assignment_type || item.resource_type)}</span></div>`).join('') : '<div class="resource-line"><span>Not required for this event</span></div>'; }
async function recheckResources(resourceType) {
  try {
    const label = resourceType === 'labs' ? 'lab' : 'venue';
    const result = await api(`/api/events/${state.eventId}/recheck-resources/${resourceType}`, { method: 'POST' });
    const message = !result.best_fit ? `No available ${label} fits this prompt and time slot.` : result.updated ? `Best-fit ${label} selected and saved.` : `Current ${label} is already the best available fit.`;
    toast(result.validation?.valid ? message : `${message} Review the validation checks.`, result.validation?.valid ? '' : 'error');
    await loadEvent();
  } catch (error) { toast(error.message, 'error'); }
}
async function replanTimeline() {
  try {
    const result = await api(`/api/events/${state.eventId}/replan-timeline`, { method: 'POST' });
    toast(result.updated ? `Best event timeline selected and saved (${result.count}).` : `Current timeline is already the most complete option (${result.count}).`);
    await loadEvent();
  } catch (error) { toast(error.message, 'error'); }
}
function renderEvent(event) {
  const plan = event.active_plan || event.proposed_plan;
  if (!plan) { $('#event-command').innerHTML = empty('This event has no plan yet', 'Generate an AI plan from the event list.'); return; }
  const locations = [...(plan.labs || []), ...(plan.venues || [])];
  const requirements = event.prompt || '';
  const isPending = event.status === 'plan_ready'; const isReplan = event.status === 'replan_pending'; const isConflict = event.status === 'conflict';
  const canComplete = event.status === 'approved' && new Date(plan.end_datetime) < new Date();
  $('#event-command').innerHTML = `<div class="command-header"><div><div class="eyebrow"><span></span> Event command center</div><h2>${esc(event.title)}</h2><p>${compactDate(plan.start_datetime)} · ${compactTime(plan.start_datetime)}–${compactTime(plan.end_datetime)} · <span class="status ${event.status}">${nice(event.status)}</span></p></div><div class="command-actions"><div class="readiness-card" title="Readiness measures six checks: space, faculty, volunteers, equipment, validation, and approval."><strong>${event.readiness || 0}%</strong><span>READINESS</span></div>${isPending ? `<button class="primary" data-action="approve-plan">Approve & lock <b>✓</b></button>` : ''}${isConflict ? `<button class="secondary" data-go="create">Revise & replan</button>` : ''}${event.status === 'approved' ? `<button class="secondary" data-action="simulate">Report resource conflict</button>` : ''}${canComplete ? `<button class="primary" data-action="complete-event">Mark completed</button>` : ''}${isReplan ? `<button class="primary" data-action="approve-replan">Approve new plan <b>✓</b></button><button class="secondary" data-action="reject-replan">Reject</button>` : ''}<button class="secondary" data-action="delete-event">Delete event</button></div></div>
    <div class="command-grid"><div><article class="panel overview-card"><span class="label">AI COORDINATOR BRIEF</span><h3>Operational recommendation</h3><p>${esc(event.ai_explanation || 'This plan was evaluated with deterministic availability, capacity and workload checks.')}</p><div class="tag-row">${locations.map(x => `<span class="tag">${esc(x.name)}</span>`).join('')}${(plan.equipment || []).map(x => `<span class="tag">${esc(x.name)} ×${x.quantity}</span>`).join('')}</div></article><div class="detail-grid"><article class="panel"><div class="panel-title"><div><span class="label">RUN OF SHOW</span><h3>Event timeline</h3></div><button class="secondary" data-action="replan-timeline">Replan timeline (${event.timeline_replan_count || 0})</button></div><div class="timeline">${(plan.timeline || []).map(t => `<div class="timeline-row"><time>${esc(t.time)}</time><div><b>${esc(t.title)}</b><span>${esc(t.description || t.owner)}</span>${t.description ? `<small>${esc(t.owner)}</small>` : ''}</div></div>`).join('')}</div></article><article class="panel"><span class="label">EXECUTION TASKS</span><h3>Readiness checklist</h3>${event.tasks?.map(task => `<div class="task">${esc(task.title)}<span>${esc(task.priority)}</span></div>`).join('') || empty('Tasks are being created', '')}</article></div></div><div><article class="panel"><div class="panel-title"><div><span class="label">LOCKABLE RESOURCES</span><h3>Space & systems</h3></div><div class="assignment-actions"><button class="secondary" data-action="recheck-labs">Recheck labs (${(event.resource_recheck_counts || {}).labs || 0})</button><button class="secondary" data-action="recheck-venues">Recheck venues (${(event.resource_recheck_counts || {}).venues || 0})</button></div></div>${items(locations)}</article><article class="panel" style="margin-top:16px"><span class="label">PEOPLE MATCHING</span><h3>Faculty</h3>${items(plan.faculty)}<h3 style="margin-top:16px">Volunteer crew</h3>${items(plan.volunteers)}<h3 style="margin-top:16px">Guest speaker</h3>${items(plan.guests)}${renderAssignmentAlternatives(event)}</article></div></div>${isReplan ? renderReplan(event.pending_replan) : ''}`;
}
function renderAssignmentAlternatives(event) {
  const unresolved = new Set(event.assignment_conflicts || []);
  const declined = (event.assignments || []).filter(item => item.acceptance === 'declined' && unresolved.has(item.assignment_id));
  return declined.map(item => `<div class="replacement-box" data-assignment-id="${esc(item.assignment_id)}"><p><b>${esc(item.resource_id)}</b> declined this assignment.</p><button class="secondary" data-action="find-alternatives" data-assignment-id="${esc(item.assignment_id)}">Show suitable alternative</button><div class="alternatives"></div></div>`).join('');
}
async function findAlternatives(button) {
  const box = button.closest('.replacement-box');
  try {
    const data = await api(`/api/events/${state.eventId}/assignments/${button.dataset.assignmentId}/alternatives`);
    box.querySelector('.alternatives').innerHTML = data.alternatives.length ? data.alternatives.map(item => `<button class="text-button" data-action="replace-assignment" data-assignment-id="${esc(button.dataset.assignmentId)}" data-resource-id="${esc(item.resource_id)}">${esc(item.name)} · ${item.score}% match</button>`).join('') : '<span>No suitable available replacement found.</span>';
  } catch (error) { toast(error.message, 'error'); }
}
async function replaceAssignment(button) {
  try { await api(`/api/events/${state.eventId}/assignments/${button.dataset.assignmentId}/replace`, { method: 'POST', body: JSON.stringify({ resource_id: button.dataset.resourceId }) }); toast('The declined assignment was replaced with a suitable available person.'); await loadEvent(); } catch (error) { toast(error.message, 'error'); }
}
function renderReplan(replan) {
  if (!replan) return '';
  const before = state.currentEvent.active_plan || {};
  return `<article class="conflict-card" style="margin-top:16px"><span class="status conflict">Replanning proposal · ${esc(replan.impact)}</span><h3>Human approval required for the new operational plan</h3><p>${esc(replan.reason)}</p><div class="conflict-details"><span>Previous: ${esc((before.labs || before.venues || []).map(x => x.name).join(' + '))}</span><span>Proposed: ${esc((replan.proposal.labs || replan.proposal.venues || []).map(x => x.name).join(' + '))}</span>${replan.changes.map(c => `<span>${esc(c)}</span>`).join('')}</div><div class="validation-strip">${replan.validation.checks.map(c => `<span class="validation-chip ${c.passed ? '' : 'fail'}">${c.passed ? '✓' : '×'} ${esc(c.label)}</span>`).join('')}</div></article>`;
}
async function approvePlan() {
  try { await api(`/api/events/${state.eventId}/approve`, { method: 'POST' }); toast('Plan approved. Time-slot assignments are now locked.'); await loadEvent(); } catch (error) { toast(error.message, 'error'); }
}
async function completeEvent() {
  try { await api(`/api/events/${state.eventId}/complete`, { method: 'POST' }); toast('Event completed. Participant attendance and event counts were updated.'); await loadEvent(); } catch (error) { toast(error.message, 'error'); }
}
async function simulateConflict() {
  try { const result = await api(`/api/events/${state.eventId}/simulate-conflict`, { method: 'POST', body: JSON.stringify({}) }); toast(result.ok ? 'Resource conflict detected. A valid replan is ready for approval.' : 'Conflict found; no valid replan is available yet.', result.ok ? '' : 'error'); await loadEvent(); } catch (error) { toast(error.message, 'error'); }
}
async function approveReplan() { try { await api(`/api/events/${state.eventId}/approve-replan`, { method: 'POST' }); toast('New plan approved; old locks released and replacements locked.'); await loadEvent(); } catch (error) { toast(error.message, 'error'); } }
async function rejectReplan() { try { await api(`/api/events/${state.eventId}/reject-replan`, { method: 'POST' }); toast('Replan rejected. The event remains in the conflict queue.'); await loadEvent(); } catch (error) { toast(error.message, 'error'); } }
async function deleteEvent() {
  if (!confirm('Delete this event and all related assignments, tasks, requirements and notifications?')) return;
  try { await api(`/api/events/${state.eventId}`, { method: 'DELETE' }); toast('Event and related records deleted. Assigned people are available again.'); state.eventId = null; navigate('dashboard'); } catch (error) { toast(error.message, 'error'); }
}

async function loadSchedule() {
  const data = await api('/api/schedule');
  const events = data.events.filter(e => e.start_datetime);
  const dates = [...new Set(events.map(e => e.start_datetime.slice(0, 10)))].slice(0, 6);
  if (!dates.length) { $('#schedule-board').innerHTML = empty('No scheduled events', 'Approved event plans will appear as time blocks here.'); return; }
  const datesHtml = dates.map(day => `<span>${new Date(`${day}T12:00`).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}</span>`).join('');
  $('#schedule-board').innerHTML = `<div class="schedule-head"><span>OPERATIONS TRACK</span>${datesHtml}</div>${['Event schedule', 'Locked assignments'].map((row, idx) => `<div class="schedule-line"><span>${row}</span><div class="time-grid">${Array.from({ length: 8 }, () => '<i></i>').join('')}${events.map((event, eventIndex) => { const dayIndex = dates.indexOf(event.start_datetime.slice(0, 10)); if (dayIndex < 0 || (idx && event.status === 'draft')) return ''; return `<span class="schedule-event ${event.status === 'replan_pending' || event.status === 'conflict' ? 'conflict' : 'approved'}" style="left:calc(${dayIndex} * 12.5% + 3px);width:calc(12.5% - 6px);top:${12 + (eventIndex % 2) * 25}px">${esc(event.title)}</span>`; }).join('')}</div></div>`).join('')}`;
}

const resourceLabels = { faculty: 'Faculty', volunteers: 'Volunteers', organizers: 'Organizers', guests: 'Guests', labs: 'Labs', equipment: 'Equipment', vehicles: 'Vehicles' };
function resourceCard(row, resourceType) {
  const title = resourceType === 'labs' ? row.lab_name || row.name || row.block_name || row.type || row.vehicle_id : row.name || row.block_name || row.lab_name || row.type || row.vehicle_id;
  const subtitle = resourceType === 'blocks' ? row.location || row.description || `Block ${row.block_id}` : row.block_name || row.block || row.block_id || row.department || row.organization || row.location || row.driver || row.type || 'Campus resource';
  const capacity = row.capacity || row.number_of_systems || row.total_quantity || row.number_of_labs;
  const visual = row.image ? `<img class="resource-avatar resource-image" src="${esc(row.image)}" alt="${esc(title)}" loading="lazy">` : `<div class="resource-avatar">${esc(title).slice(0, 2).toUpperCase()}</div>`;
  const status = resourceType === 'blocks' ? 'Campus block' : row.assignment_count ? 'Assigned' : 'Available now';
  const details = capacity ? `${capacity} ${resourceType === 'equipment' ? 'total units' : resourceType === 'blocks' ? 'labs' : 'capacity'}` : resourceType === 'blocks' ? 'Campus block' : 'Active';
  const locks = resourceType === 'blocks' ? row.block_id : `${row.assignment_count} active lock${row.assignment_count === 1 ? '' : 's'}`;
  return `<article class="resource-card${row.image ? ' has-image' : ''}">${visual}<span class="status ${row.assignment_count ? 'plan_ready' : 'approved'}" style="position:absolute;top:15px;right:14px">${esc(status)}</span><h3>${esc(title)}</h3><p>${esc(subtitle)}</p><div class="resource-meta"><span>${esc(details)}</span><span class="assignment-badge">${esc(locks)}</span></div></article>`;
}
async function loadResources() {
  if (!resourceLabels[state.resourcesType]) state.resourcesType = 'faculty';
  $('#resource-tabs').innerHTML = Object.entries(resourceLabels).map(([key, label]) => `<button class="${state.resourcesType === key ? 'active' : ''}" data-resource-type="${key}">${label}</button>`).join('');
  const data = await api(`/api/resources?type=${state.resourcesType}`);
  $('#resource-grid').innerHTML = data.resources.length ? data.resources.map(row => resourceCard(row, state.resourcesType)).join('') : empty(`No ${resourceLabels[state.resourcesType].toLowerCase()} yet`, 'Add a resource to make it available for AI event planning.');
}
async function checkAvailability(form) {
  const values = Object.fromEntries(new FormData(form).entries());
  const result = await api(`/api/availability?${new URLSearchParams(values)}`);
  $('#availability-result').textContent = result.matches.length ? result.matches.map(item => `${item.name}: ${item.available ? 'Available' : 'Busy'}`).join(' · ') : 'No resource found';
}
async function loadVenues() {
  const venueTypes = { venues: 'Venues', blocks: 'Blocks' };
  if (!venueTypes[state.venuesType]) state.venuesType = 'venues';
  const type = state.venuesType;
  const isBlocks = type === 'blocks';
  $('#venue-tabs').innerHTML = Object.entries(venueTypes).map(([key, label]) => `<button class="${key === type ? 'active' : ''}" data-venue-type="${key}">${label}</button>`).join('');
  $('#venue-heading').textContent = venueTypes[type];
  $('#venue-description').textContent = isBlocks ? 'View campus blocks, their location, and the number of labs in each block.' : 'Add and manage campus venues. The AI only selects venues that meet the event requirements and are free at the chosen time.';
  $('#venue-add-button').innerHTML = `Add ${isBlocks ? 'block' : 'venue'} <b>+</b>`;
  const data = await api(`/api/resources?type=${type}`);
  $('#venue-grid').innerHTML = data.resources.length ? data.resources.map(row => resourceCard(row, type)).join('') : empty(`No ${venueTypes[type].toLowerCase()} yet`, `Add a ${isBlocks ? 'block to organize campus spaces' : 'venue so the AI can schedule events in it'}.`);
}

const dataTypes = {
  faculty: { label: 'Faculty', id: 'faculty_id', required: ['name', 'department'], fields: ['faculty_id', 'name', 'department', 'subjects', 'expertise', 'skills', 'contact', 'email', 'image', 'max_events_per_day', 'status'] },
  volunteers: { label: 'Volunteers', id: 'volunteer_id', required: ['name', 'department'], fields: ['volunteer_id', 'name', 'department', 'year', 'skills', 'interests', 'preferred_roles', 'email', 'image', 'max_events_per_day', 'status'] },
  organizers: { label: 'Organizers', id: 'organizer_id', required: ['name', 'department'], fields: ['organizer_id', 'name', 'department', 'organization', 'phone', 'email', 'image', 'status'] },
  guests: { label: 'Guests', id: 'guest_id', required: ['name', 'organization'], fields: ['guest_id', 'name', 'designation', 'organization', 'expertise', 'relevant_departments', 'relevant_subjects', 'suitable_event_types', 'contact', 'email', 'image', 'previous_events', 'status'] },
  blocks: { label: 'Blocks', id: 'block_id', required: ['block_name'], fields: ['block_id', 'block_name', 'image', 'location', 'number_of_labs', 'description'] },
  labs: { label: 'Labs', id: 'lab_id', required: ['lab_name', 'block_id', 'capacity', 'number_of_systems'], fields: ['lab_id', 'lab_name', 'block_id', 'floor', 'capacity', 'number_of_systems', 'operating_system', 'installed_software', 'projectors', 'microphones', 'internet', 'image', 'status'] },
  venues: { label: 'Venues', id: 'venue_id', required: ['name', 'block', 'type', 'capacity'], fields: ['venue_id', 'name', 'block', 'floor', 'type', 'image', 'capacity', 'chairs', 'tables', 'projectors', 'microphones', 'speakers', 'computers', 'air_conditioning', 'internet', 'accessibility', 'status'] },
  equipment: { label: 'Equipment', id: 'equipment_id', required: ['type', 'name', 'total_quantity'], fields: ['equipment_id', 'type', 'name', 'total_quantity', 'location', 'condition', 'image', 'status'] },
  vehicles: { label: 'Vehicles', id: 'vehicle_id', required: ['type', 'capacity', 'driver'], fields: ['vehicle_id', 'type', 'capacity', 'driver', 'image', 'status'] },
  academic_calendar: { label: 'Academic calendar', id: 'calendar_id', required: ['date', 'type', 'reason'], fields: ['calendar_id', 'date', 'type', 'reason', 'image', 'available'] }
};
const listFields = new Set(['subjects', 'expertise', 'skills', 'interests', 'preferred_roles', 'relevant_departments', 'relevant_subjects', 'suitable_event_types', 'operating_system', 'installed_software']);
const numberFields = new Set(['max_events_per_day', 'year', 'previous_events', 'number_of_labs', 'floor', 'capacity', 'number_of_systems', 'projectors', 'microphones', 'chairs', 'tables', 'speakers', 'computers', 'total_quantity']);
const booleanFields = new Set(['internet', 'air_conditioning', 'accessibility', 'available']);
function fieldLabel(field) { return nice(field); }
function fieldControl(field, required, idField, values = {}) {
  const optionalId = field === idField;
  const requiredAttr = required ? 'required' : '';
  const help = optionalId ? ` <small>${values[idField] ? 'fixed after creation' : 'leave empty to generate'}</small>` : listFields.has(field) ? ' <small>comma-separated</small>' : '';
  const sourceValue = values[field];
  const value = Array.isArray(sourceValue) ? sourceValue.join(', ') : (sourceValue ?? (field === 'status' ? 'active' : ''));
  if (field === 'image') return `<div class="entry-field wide image-entry"><label>Image <small>JPG, PNG, GIF or WebP; 5 MB maximum</small></label><input type="hidden" name="image" value="${esc(value)}"><input type="file" name="image_file" accept="image/jpeg,image/png,image/gif,image/webp">${value ? `<img class="image-preview" src="${esc(value)}" alt="Current record image">` : ''}</div>`;
  if (booleanFields.has(field)) return `<div class="entry-field"><label>${fieldLabel(field)}${help}</label><select name="${field}"><option value="true" ${String(value) !== 'false' ? 'selected' : ''}>Yes</option><option value="false" ${String(value) === 'false' ? 'selected' : ''}>No</option></select></div>`;
  if (field === 'description') return `<div class="entry-field wide"><label>${fieldLabel(field)}${help}</label><textarea name="${field}" placeholder="Optional description">${esc(value)}</textarea></div>`;
  const type = field === 'date' ? 'date' : field === 'email' ? 'email' : (numberFields.has(field) && !(field === 'floor' && state.dataType === 'venues')) ? 'number' : 'text';
  const placeholder = optionalId ? 'Generated automatically' : listFields.has(field) ? 'Example: Python, VS Code, AI' : '';
  return `<div class="entry-field ${listFields.has(field) ? 'wide' : ''}"><label>${fieldLabel(field)}${help}</label><input type="${type}" name="${field}" value="${esc(value)}" placeholder="${placeholder}" ${optionalId && values[idField] ? 'readonly' : ''} ${requiredAttr}></div>`;
}
function renderDataForm() {
  const spec = dataTypes[state.dataType];
  const record = state.dataEdit;
  const singular = spec.label.endsWith('s') ? spec.label.slice(0, -1) : spec.label;
  const timetableImport = state.dataType === 'academic_calendar' ? `<form id="calendar-image-form" class="calendar-image-import"><div><span class="label">TIMETABLE IMAGE</span><h4>Read working days and holidays</h4><p>Upload a clear JPG, PNG, GIF, or WebP timetable. Gemini Vision reads clearly dated entries; review them before saving.</p></div><input type="file" name="image" accept="image/jpeg,image/png,image/gif,image/webp" required><button class="primary" type="submit">Read timetable image</button></form><div class="calendar-legend" aria-label="Calendar color legend"><span class="calendar-legend-item working"><i></i> Green: working day, available for events</span><span class="calendar-legend-item holiday"><i></i> Red: holiday or unavailable day</span></div><div id="calendar-image-results"></div>` : '';
  $('#data-form-content').innerHTML = `<div class="data-form-head"><span class="label">${record ? 'EDIT' : 'ADD'} ${esc(spec.label).toUpperCase()}</span><h3>${record ? `Edit ${esc(singular)}` : `New ${esc(singular)} record`}</h3><p>Required fields are marked by the browser. Upload an image or retain the current one.</p></div>${timetableImport}<form id="csv-import-form" class="csv-import" data-type="${state.dataType}"><div><span class="label">CSV IMPORT</span><h4>Import ${esc(spec.label)}</h4><p>Download the header template, add one record per row, and use <code>|</code> between list values.</p></div><input type="file" name="file" accept=".csv,text/csv" required><div class="csv-import-actions"><button class="secondary" type="button" data-action="download-csv-template" data-data-type="${state.dataType}">Download template</button><button class="primary" type="submit">Import CSV</button></div></form><form id="data-entry-form" class="entry-form" data-type="${state.dataType}" data-record-id="${record ? esc(record[spec.id]) : ''}">${spec.fields.map(field => fieldControl(field, spec.required.includes(field), spec.id, record || {})).join('')}<div class="form-actions">${record ? '<button class="secondary" type="button" data-action="cancel-edit">Cancel</button>' : ''}<button class="primary" type="submit">${record ? 'Save changes' : `Save ${esc(spec.label)}`} <b>+</b></button></div></form>`;
}
async function loadDataManager() {
  const allowedTypes = state.dataContext === 'venues'
    ? ['venues']
    : Object.keys(dataTypes);
  if (!allowedTypes.includes(state.dataType)) state.dataType = allowedTypes[0];
  const spec = dataTypes[state.dataType];
  $('#data-tabs').innerHTML = allowedTypes.map(key => `<button class="${key === state.dataType ? 'active' : ''}" data-data-type="${key}">${dataTypes[key].label}</button>`).join('');
  renderDataForm();
  const data = await api(`/api/data/${state.dataType}`);
  state.dataRecords = data.records;
  $('#data-record-title').textContent = spec.label;
  $('#data-record-count').textContent = `${data.records.length} record${data.records.length === 1 ? '' : 's'}`;
  $('#data-record-list').innerHTML = data.records.length ? data.records.map(record => {
    const title = record.name || record.lab_name || record.block_name || record.type || record.reason || record[spec.id];
    const sub = record.department || record.block || record.organization || record.location || record.date || record[spec.id];
    const recordState = state.dataType === 'academic_calendar' ? `<span class="calendar-status ${record.available ? 'working' : 'holiday'}">${record.available ? 'Working day' : 'Holiday'}</span>` : `<span>${esc(record[spec.id])}</span>`;
    return `<div class="data-record"><i>✓</i><div><b>${esc(title)}</b><span>${esc(sub)}</span></div>${recordState}<button class="text-button" data-edit-record="${esc(record[spec.id])}">Edit</button></div>`;
  }).join('') : empty(`No ${spec.label.toLowerCase()} yet`, 'Use the form to add your first real record.');
  $$('.data-record', $('#data-record-list')).forEach((item, index) => {
    const record = data.records[index];
    if (!record.image) return;
    const marker = $('i', item);
    if (!marker) return;
    const image = document.createElement('img');
    image.className = 'data-record-image';
    image.src = record.image;
    image.alt = record.name || record.lab_name || record.block_name || record.type || 'Campus record';
    image.loading = 'lazy';
    marker.replaceWith(image);
  });
}
async function saveDataRecord(form) {
  const type = form.dataset.type;
  const formData = new FormData(form);
  const image = formData.get('image_file');
  try {
    if (image instanceof File && image.size) {
      const upload = new FormData(); upload.append('image', image);
      const response = await fetch('/api/uploads', { method: 'POST', body: upload });
      const uploaded = await response.json().catch(() => ({ error: 'Image upload failed.' }));
      if (!response.ok) throw new Error(uploaded.error || 'Image upload failed.');
      formData.set('image', uploaded.image);
    }
    formData.delete('image_file');
    const values = Object.fromEntries(formData.entries());
    const recordId = form.dataset.recordId;
    await api(recordId ? `/api/data/${type}/${encodeURIComponent(recordId)}` : `/api/data/${type}`, { method: recordId ? 'PUT' : 'POST', body: JSON.stringify({ data: values }) });
    toast(`${dataTypes[type].label} record ${recordId ? 'updated' : 'saved'}.`);
    state.dataEdit = null;
    await loadDataManager();
  } catch (error) { toast(error.message, 'error'); }
}
function csvCell(value) { return `"${String(value).replaceAll('"', '""')}"`; }
function downloadCsvTemplate(type) {
  const fields = dataTypes[type].fields.filter(field => field !== 'image');
  const blob = new Blob([`${fields.map(csvCell).join(',')}\n`], { type: 'text/csv;charset=utf-8' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `${type}-template.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 0);
}
async function importCsv(form) {
  const type = form.dataset.type;
  try {
    const response = await fetch(`/api/data/${encodeURIComponent(type)}/csv`, { method: 'POST', body: new FormData(form) });
    const result = await response.json().catch(() => ({ error: 'CSV import failed.' }));
    if (!response.ok) throw new Error(result.error || 'CSV import failed.');
    toast(`${result.imported} ${dataTypes[type].label.toLowerCase()} record${result.imported === 1 ? '' : 's'} imported.`);
    state.dataEdit = null;
    await loadDataManager();
  } catch (error) { toast(error.message, 'error'); }
}
function renderCalendarImageResults() {
  const target = $('#calendar-image-results');
  if (!target) return;
  if (!state.calendarImageRecords.length) { target.innerHTML = ''; return; }
  target.innerHTML = `<div class="calendar-image-results"><div><span class="label">REVIEW RECOGNIZED DAYS</span><h4>${state.calendarImageRecords.length} timetable day${state.calendarImageRecords.length === 1 ? '' : 's'} found</h4><p>Check the dates and status below before saving them to the calendar.</p></div><div class="calendar-scan-list">${state.calendarImageRecords.map(record => `<div class="calendar-scan-row"><span class="calendar-status ${record.available ? 'working' : 'holiday'}">${record.available ? 'Working day' : 'Holiday'}</span><b>${esc(record.date)}</b><span>${esc(record.reason)}</span></div>`).join('')}</div><button class="primary" type="button" data-action="import-calendar-image">Save recognized days</button></div>`;
}
async function scanCalendarImage(form) {
  try {
    const response = await fetch('/api/data/academic_calendar/scan-image', { method: 'POST', body: new FormData(form) });
    const result = await response.json().catch(() => ({ error: 'Timetable image could not be read.' }));
    if (!response.ok) throw new Error(result.error || 'Timetable image could not be read.');
    state.calendarImageRecords = result.records;
    renderCalendarImageResults();
    toast(`${result.records.length} timetable day${result.records.length === 1 ? '' : 's'} recognized. Review before saving.`);
  } catch (error) { toast(error.message, 'error'); }
}
async function importCalendarImageRecords() {
  try {
    const result = await api('/api/data/academic_calendar/image-import', { method: 'POST', body: JSON.stringify({ records: state.calendarImageRecords }) });
    toast(`${result.created} calendar day${result.created === 1 ? '' : 's'} added${result.updated ? ` and ${result.updated} updated` : ''}.`);
    state.calendarImageRecords = [];
    await loadDataManager();
  } catch (error) { toast(error.message, 'error'); }
}

function memberStatus(availability) {
  const pending = availability.assignments.filter(item => item.acceptance === 'pending');
  return {
    badge: availability.available ? 'approved' : pending.length ? 'conflict' : 'plan_ready',
    label: availability.available ? 'Available' : pending.length ? 'Response needed' : 'Assigned',
    pending,
  };
}
function memberEventRow(event, live) {
  return `<div class="event-row"><span class="event-icon">${live ? '●' : '✦'}</span><span class="event-info"><b>${esc(event.title)}</b><span>${compactDate(event.start_datetime)} · ${compactTime(event.start_datetime)}</span></span><span class="status ${event.status}">${nice(event.status)}</span></div>`;
}
function assignmentRow(item) {
  return `<div class="my-assignment"><div><b>${esc(item.event_title)}</b><span>${esc(nice(item.assignment_type || item.resource_type))} · <span class="status ${item.acceptance === 'accepted' ? 'approved' : item.acceptance === 'declined' ? 'conflict' : 'plan_ready'}">${nice(item.acceptance || 'pending')}</span></span>${item.acceptance === 'pending' ? `<div class="assignment-actions"><button class="primary" data-action="accept-assignment" data-assignment-id="${item.assignment_id}">Accept <b>✓</b></button><button class="secondary" data-action="decline-assignment" data-assignment-id="${item.assignment_id}">Decline</button></div>` : ''}${item.acceptance === 'declined' ? `<div class="assignment-actions"><button class="secondary" data-action="find-alternatives" data-event-id="${item.event_id}" data-assignment-id="${item.assignment_id}">Find alternative</button></div><div class="alternative-list" id="alternatives-${item.assignment_id}"></div>` : ''}</div><time>${compactDate(item.start_datetime)} · ${compactTime(item.start_datetime)}–${compactTime(item.end_datetime)}</time></div>`;
}

async function loadMemberDashboard() {
  const [availability, events] = await Promise.all([api('/api/auth/my-availability'), api('/api/auth/my-events')]);
  const status = memberStatus(availability);
  $('#member-dashboard').innerHTML = `<div class="page-heading"><div><div class="eyebrow"><span></span> ${esc(nice(state.user.role))} workspace</div><h2>Dashboard</h2><p>Running and upcoming campus events, plus your current assignments.</p></div><span class="status ${status.badge}">${status.label}</span></div><div class="member-dashboard-grid"><article class="panel assignment-panel"><div class="panel-title"><div><span class="label">MY AVAILABILITY</span><h3>${status.label}</h3></div></div><p>${esc(availability.message)}</p><div class="panel-title" style="margin-top:16px"><div><span class="label">EVENT ASSIGNMENTS</span><h3>${availability.assignments.length ? `${availability.assignments.length} active assignment${availability.assignments.length === 1 ? '' : 's'}` : 'No active assignments'}</h3></div></div>${availability.assignments.length ? availability.assignments.map(assignmentRow).join('') : empty('You are available', 'A mailbox message will arrive when the AI assigns you to an available event slot.')}</article><div><article class="panel"><div class="panel-title"><div><span class="label">LIVE NOW</span><h3>Running events</h3></div></div><div class="event-list">${events.running.length ? events.running.map(event => memberEventRow(event, true)).join('') : empty('Nothing running right now', 'Approved events in progress will appear here.')}</div></article><article class="panel member-section"><div class="panel-title"><div><span class="label">ON THE HORIZON</span><h3>Upcoming events</h3></div></div><div class="event-list">${events.upcoming.length ? events.upcoming.map(event => memberEventRow(event, false)).join('') : empty('No upcoming events', 'Approved events will appear here once scheduled.')}</div></article></div></div>`;
  await loadMemberMailbox();
}

const memberProfileFields = {
  faculty: ['name', 'department', 'subjects', 'expertise', 'skills', 'contact', 'email', 'image'],
  volunteer: ['name', 'department', 'year', 'skills', 'interests', 'preferred_roles', 'email', 'image'],
  organizer: ['name', 'department', 'organization', 'phone', 'email', 'image'],
};
function profileFieldControl(field, profile) {
  const source = profile[field];
  const value = Array.isArray(source) ? source.join(', ') : (source ?? '');
  const help = ['subjects', 'expertise', 'skills', 'interests', 'preferred_roles'].includes(field) ? ' <small>comma-separated</small>' : '';
  const inputType = field === 'image' ? 'url' : field === 'year' ? 'number' : 'text';
  return `<div class="entry-field ${field === 'image' ? 'wide' : ''}"><label>${fieldLabel(field)}${help}</label><input type="${inputType}" name="${field}" value="${esc(value)}" ${field === 'year' ? 'min="1" max="12"' : ''}></div>`;
}
async function loadMemberProfile() {
  const data = await api('/api/auth/my-profile');
  const profile = data.profile;
  const fields = memberProfileFields[state.user.role] || [];
  const profileId = profile[state.user.role === 'faculty' ? 'faculty_id' : state.user.role === 'volunteer' ? 'volunteer_id' : 'organizer_id'] || '';
  $('#member-profile').innerHTML = `<div class="page-heading"><div><div class="eyebrow"><span></span> ${esc(nice(state.user.role))} record</div><h2>My profile</h2><p>Keep your details current so your organizer identity is visible on planned events.</p></div></div><div class="profile-layout"><article class="panel identity-card">${profile.image ? `<img class="profile-image" src="${esc(profile.image)}" alt="${esc(profile.name)}">` : `<div class="profile-avatar">${esc(profile.name).slice(0, 2).toUpperCase()}</div>`}<span class="label">${esc(nice(state.user.role))} ID · ${esc(profileId)}</span><h3>${esc(profile.name)}</h3><p>${esc(profile.department || '')}${profile.organization ? ` · ${esc(profile.organization)}` : ''}</p><div class="availability-state"><b>${esc(nice(profile.status || 'active'))} account</b><span>Your changes update only your own profile.</span></div></article><article class="panel"><div class="panel-title"><div><span class="label">EDIT DETAILS</span><h3>Profile information</h3></div></div><form id="profile-form" class="entry-form">${fields.map(field => profileFieldControl(field, profile)).join('')}<div class="form-actions"><button class="primary" type="submit">Save profile</button></div></form></article></div>`;
}
async function saveMemberProfile(form) {
  const button = form.querySelector('[type="submit"]'); button.disabled = true;
  try {
    const profile = Object.fromEntries(new FormData(form).entries());
    const result = await api('/api/auth/my-profile', { method: 'PUT', body: JSON.stringify({ profile }) });
    if (result.user) applySession(result.user);
    toast('Your profile was updated.');
    await loadMemberProfile();
  } catch (error) { toast(error.message, 'error'); }
  finally { button.disabled = false; }
}
async function loadMemberAttendance() {
  const data = await api('/api/auth/my-availability');
  const attendance = data.attendance;
  $('#member-attendance').innerHTML = `<div class="page-heading"><div><div class="eyebrow"><span></span> Participation record</div><h2>Attendance</h2><p>Attendance points are recorded when an accepted event is completed.</p></div></div><article class="panel attendance-panel"><div class="attendance-summary"><div><strong>${attendance.total_events}</strong><span>Completed events</span></div><div><strong>${attendance.total_points}</strong><span>Total points</span></div><div><strong>${attendance.points_per_event}</strong><span>Points / event</span></div></div><div class="panel-title"><div><span class="label">MONTHLY BREAKDOWN</span><h3>My attendance history</h3></div></div>${attendance.monthly.length ? attendance.monthly.map(row => `<div class="attendance-row"><b>${esc(row.month)}</b><span>${row.events} event${row.events === 1 ? '' : 's'} · ${row.points} pts</span></div>`).join('') : empty('No attendance yet', 'Accept an event assignment, then wait for the event to be completed.')}</article>`;
}

async function respondAssignment(assignmentId, decision) {
  try {
    await api(`/api/auth/assignments/${assignmentId}/respond`, { method: 'POST', body: JSON.stringify({ decision }) });
    toast(decision === 'accept' ? 'Assignment accepted. Attendance points recorded.' : 'Assignment declined.');
    await loadMemberDashboard();
  } catch (error) { toast(error.message, 'error'); }
}

async function loadCampus() {
  const data = await api('/api/campus/blocks');
  $('#campus-grid').innerHTML = data.blocks.map(block => `<article class="campus-card" data-block="${block.block_id}"><div class="image-placeholder"><span>REAL IMAGE PLACEHOLDER · ${esc(block.image)}</span></div><div class="campus-card-body"><h3>${esc(block.block_name)}</h3><p>${esc(block.location)}</p><div class="campus-stats"><span><b>${block.labs}</b>Labs</span><span><b>${block.systems}</b>Systems</span></div></div></article>`).join('');
  $$('.campus-card', $('#campus-grid')).forEach((card, index) => {
    const block = data.blocks[index];
    if (!block.image) return;
    const placeholder = $('.image-placeholder', card);
    if (!placeholder) return;
    const image = document.createElement('img');
    image.className = 'campus-image';
    image.src = block.image;
    image.alt = block.block_name;
    image.loading = 'lazy';
    placeholder.replaceWith(image);
    card.classList.add('has-image');
  });
  $('#lab-drawer').classList.remove('show');
}
async function loadLabs(blockId) {
  const data = await api(`/api/campus/blocks/${blockId}/labs`);
  $('#lab-drawer').classList.add('show');
  $('#lab-drawer').innerHTML = `<div class="lab-head"><div><span class="label">${esc(data.block.block_name)}</span><h3>Available lab detail</h3></div><button class="text-button" data-action="close-labs">Close ×</button></div><div class="lab-grid">${data.labs.map(lab => `<article class="lab-card"><div class="image-placeholder" style="min-height:80px"><span>${esc(lab.image)}</span></div><h3>${esc(lab.lab_name)}</h3><p>${lab.capacity} seats · ${lab.number_of_systems} systems · ${lab.current_assignments.length ? `${lab.current_assignments.length} active assignment` : 'No active assignment'}</p>${lab.installed_software.map(s => `<span class="lab-feature">${esc(s)}</span>`).join('')}<span class="lab-feature">${lab.projectors ? 'Projector' : 'No projector'}</span><span class="lab-feature">Internet</span></article>`).join('')}</div>`;
  $$('.lab-card', $('#lab-drawer')).forEach((card, index) => {
    const lab = data.labs[index];
    const details = $('p', card);
    if (details) details.textContent = `${data.block.block_name} - ${lab.capacity} seats - ${lab.number_of_systems} systems`;
    if (!lab.image) return;
    const placeholder = $('.image-placeholder', card);
    if (!placeholder) return;
    const image = document.createElement('img');
    image.className = 'lab-image';
    image.src = lab.image;
    image.alt = lab.lab_name;
    image.loading = 'lazy';
    placeholder.replaceWith(image);
    card.classList.add('has-image');
  });
  $('#lab-drawer').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function loadConflicts() {
  const data = await api('/api/conflicts');
  $('#conflict-list').innerHTML = data.conflicts.length ? data.conflicts.map(event => { const replan = event.pending_replan; return `<article class="conflict-card"><span class="status ${event.status}">${nice(event.status)}</span><h3>${esc(event.title)}</h3><p>${esc(replan?.reason || event.validation?.errors?.join(' · ') || 'This event needs an operations review.')}</p><div class="conflict-details"><span>Impact: ${esc(replan?.impact || 'Review required')}</span><span>${esc(event.approval_status || 'Approval blocked')}</span>${(replan?.changes || []).map(c => `<span>${esc(c)}</span>`).join('')}</div>${event.status === 'replan_pending' ? `<button class="primary event-open" data-id="${event.event_id}">Review proposal <b>→</b></button>` : `<button class="secondary event-open" data-id="${event.event_id}">Open event</button>`}</article>`; }).join('') : empty('No active conflicts', 'CampusFlow will surface exceptions requiring human attention here.');
}
async function loadAgents() {
  const data = await api('/api/agents');
  const descriptions = { 'Event Understanding': 'Turns natural language into structured, validated requirements.', 'Schedule Agent': 'Finds working dates inside campus rules.', 'Venue Agent': 'Matches capacity, software and time-slot availability.', 'People Agent': 'Ranks faculty, volunteers and guests with explainable scores.', 'Resource Agent': 'Allocates quantity-aware equipment and transport.', 'Conflict Agent': 'Enforces deterministic overlap and workload rules.', 'Coordinator': 'Combines specialist decisions into a human-reviewable plan.' };
  $('#agent-network').innerHTML = data.agents.map((agent, index) => `<article class="network-node"><div class="node-icon">${index + 1}</div><span class="status ${agent.status === 'waiting' ? 'plan_ready' : agent.status}">${nice(agent.status)}</span><h3>${esc(agent.name)}</h3><p>${esc(agent.detail || descriptions[agent.name] || '')}</p></article>`).join('');
}
async function loadAudit() {
  const data = await api('/api/audit');
  $('#audit-list').innerHTML = data.logs.length ? data.logs.map(row => `<div class="audit-row"><time>${new Date(row.timestamp).toLocaleString()}</time><div><b>${esc(row.action)}</b><span>${esc(row.details)}</span></div><span>${esc(row.actor)}</span></div>`).join('') : empty('No audit entries', 'Meaningful actions will appear here.');
}
async function loadNotifications() {
  const data = await api('/api/notifications'); state.notifications = data.notifications;
  const count = data.notifications.length; $('#notification-count').textContent = count; $('#notification-count').style.display = count ? 'block' : 'none';
  $('#notification-panel').innerHTML = `<div class="panel-title"><h3>In-app notifications</h3><div><span class="live-chip">${count} new</span>${count ? '<button class="text-button" data-action="delete-notifications">Delete all</button>' : ''}</div></div>${data.notifications.length ? data.notifications.map(note => `<div class="notice"><b>${esc(note.title)}</b><p>${esc(note.message)}</p></div>`).join('') : '<div class="empty">No notifications yet.</div>'}`;
}
async function deleteNotifications() {
  try { await api('/api/notifications', { method: 'DELETE' }); await loadNotifications(); toast('All notifications deleted.'); } catch (error) { toast(error.message, 'error'); }
}
async function loadMemberMailbox() {
  const data = await api('/api/auth/my-mailbox');
  const count = data.messages.length;
  $('#mail-count').textContent = count; $('#mail-count').style.display = count ? 'block' : 'none';
  $('#mail-panel').innerHTML = `<div class="panel-title"><div><span class="label">MAILBOX</span><h3>Assignment messages</h3></div><span class="live-chip">${count} message${count === 1 ? '' : 's'}</span></div>${data.messages.length ? data.messages.map(note => `<div class="notice"><b>${esc(note.title)}</b><p>${esc(note.message)}</p><time>${compactDate(note.created_at)} · ${compactTime(note.created_at)}</time></div>`).join('') : '<div class="empty">No messages yet. You will receive an in-app mail when an available event slot is assigned to you.</div>'}`;
}
function empty(title, copy) { return `<div class="empty"><strong>${esc(title)}</strong>${esc(copy)}</div>`; }

document.addEventListener('click', event => {
  const loginTab = event.target.closest('[data-login-tab]'); if (loginTab) { setLoginTab(loginTab.dataset.loginTab); return; }
  const staffRole = event.target.closest('[data-staff-role]'); if (staffRole) { setStaffRole(staffRole.dataset.staffRole); return; }
  const nav = event.target.closest('[data-view]'); if (nav) { event.preventDefault(); if (nav.dataset.view === 'data') { state.dataContext = 'resources'; state.dataEdit = null; } navigate(nav.dataset.view); return; }
  const go = event.target.closest('[data-go]'); if (go) { navigate(go.dataset.go); return; }
  const landingLogin = event.target.closest('[data-action="landing-login"]'); if (landingLogin) { showLogin(true); $('#login-form [name="username"]').focus(); return; }
  const hint = event.target.closest('[data-prompt]'); if (hint) { $('#event-prompt').value = hint.dataset.prompt; return; }
  const open = event.target.closest('.event-open'); if (open) { state.eventId = open.dataset.id; navigate('event'); return; }
  const resource = event.target.closest('[data-resource-type]'); if (resource) { state.resourcesType = resource.dataset.resourceType; loadResources().catch(e => toast(e.message, 'error')); return; }
  const venueType = event.target.closest('[data-venue-type]'); if (venueType) { state.venuesType = venueType.dataset.venueType; loadVenues().catch(e => toast(e.message, 'error')); return; }
  const dataType = event.target.closest('[data-data-type]'); if (dataType) { state.dataType = dataType.dataset.dataType; state.dataEdit = null; loadDataManager().catch(e => toast(e.message, 'error')); return; }
  const editRecord = event.target.closest('[data-edit-record]'); if (editRecord) { const spec = dataTypes[state.dataType]; state.dataEdit = state.dataRecords.find(record => record[spec.id] === editRecord.dataset.editRecord) || null; renderDataForm(); return; }
  const block = event.target.closest('[data-block]'); if (block) { loadLabs(block.dataset.block).catch(e => toast(e.message, 'error')); return; }
  const action = event.target.closest('[data-action]'); if (!action) return;
  if (action.dataset.action === 'add-resource') { state.dataContext = 'resources'; state.dataType = state.resourcesType; state.dataEdit = null; navigate('data'); return; }
  if (action.dataset.action === 'add-venue-or-block') { state.dataContext = 'venues'; state.dataType = state.venuesType; state.dataEdit = null; navigate('data'); return; }
  if (action.dataset.action === 'download-csv-template') { downloadCsvTemplate(action.dataset.dataType); return; }
  if (action.dataset.action === 'import-calendar-image') { importCalendarImageRecords(); return; }
  if (action.dataset.action === 'cancel-edit') { state.dataEdit = null; renderDataForm(); return; }
  if (action.dataset.action === 'logout') { signOut(); return; }
  if (action.dataset.action === 'open-event') { if (action.dataset.eventId) state.eventId = action.dataset.eventId; navigate('event'); return; }
  if (action.dataset.action === 'edit-event') { openDashboardEventEditor(action.dataset.eventId); return; }
  if (action.dataset.action === 'close-event-editor') { $('#dashboard-event-editor').innerHTML = ''; return; }
  if (action.dataset.action === 'approve-plan') approvePlan();
  if (action.dataset.action === 'complete-event') completeEvent();
  if (action.dataset.action === 'simulate') simulateConflict();
  if (action.dataset.action === 'approve-replan') approveReplan();
  if (action.dataset.action === 'reject-replan') rejectReplan();
  if (action.dataset.action === 'delete-event') deleteEvent();
  if (action.dataset.action === 'recheck-labs') recheckResources('labs');
  if (action.dataset.action === 'recheck-venues') recheckResources('venues');
  if (action.dataset.action === 'replan-timeline') replanTimeline();
  if (action.dataset.action === 'delete-notifications') deleteNotifications();
  if (action.dataset.action === 'close-labs') $('#lab-drawer').classList.remove('show');
  if (action.dataset.action === 'accept-assignment') respondAssignment(action.dataset.assignmentId, 'accept');
  if (action.dataset.action === 'decline-assignment') respondAssignment(action.dataset.assignmentId, 'decline');
  if (action.dataset.action === 'find-alternatives') findAlternatives(action);
  if (action.dataset.action === 'replace-assignment') replaceAssignment(action);
});
document.addEventListener('submit', event => {
  const availabilityForm = event.target.closest('#availability-form');
  if (availabilityForm) { event.preventDefault(); checkAvailability(availabilityForm).catch(error => toast(error.message, 'error')); return; }
  const login = event.target.closest('#login-form');
  if (login) { event.preventDefault(); signIn(login); return; }
  const calendarImage = event.target.closest('#calendar-image-form');
  if (calendarImage) { event.preventDefault(); const submit = calendarImage.querySelector('[type="submit"]'); submit.disabled = true; scanCalendarImage(calendarImage).finally(() => { submit.disabled = false; }); return; }
  const csvImport = event.target.closest('#csv-import-form');
  if (csvImport) { event.preventDefault(); const submit = csvImport.querySelector('[type="submit"]'); submit.disabled = true; importCsv(csvImport).finally(() => { submit.disabled = false; }); return; }
  const form = event.target.closest('#data-entry-form');
  const profileForm = event.target.closest('#profile-form');
  if (profileForm) { event.preventDefault(); saveMemberProfile(profileForm); return; }
  const eventNameForm = event.target.closest('#event-name-form');
  if (eventNameForm) { event.preventDefault(); saveEventName(eventNameForm); return; }
  if (!form) return;
  event.preventDefault();
  const submit = form.querySelector('[type="submit"]');
  submit.disabled = true;
  saveDataRecord(form).finally(() => { submit.disabled = false; });
});
$('#generate-plan').addEventListener('click', generatePlan);
$('#notification-button').addEventListener('click', () => $('#notification-panel').classList.toggle('show'));
$('#mail-button').addEventListener('click', () => $('#mail-panel').classList.toggle('show'));
function setupLandingScroll() {
  const sections = $$('.landing-page .landing-section');
  if (!('IntersectionObserver' in window)) { sections.forEach(section => section.classList.add('is-visible')); return; }
  const observer = new IntersectionObserver(entries => entries.forEach(entry => {
    if (entry.isIntersecting) { entry.target.classList.add('is-visible'); observer.unobserve(entry.target); }
  }), { threshold: 0.18 });
  sections.forEach(section => observer.observe(section));
}
setupLandingScroll();
initialize();
