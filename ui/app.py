import base64
import json
import os
import requests
import streamlit as st

API_BASE=os.getenv('UI_API_BASE_URL','http://127.0.0.1:8000').rstrip('/')
st.set_page_config(page_title='TrackoBit Support',page_icon='🛰️',layout='wide',initial_sidebar_state='expanded')

st.markdown('''
<style>
:root { --tb-ink:#14253d; --tb-blue:#185adb; --tb-muted:#66758a; --tb-border:#e4eaf2; --tb-soft:#f4f7fb; }
.block-container {padding-top: 1.3rem; padding-bottom: 2rem; max-width: 1320px;}
[data-testid="stSidebar"] {background:#f7f9fc; border-right:1px solid #e6ebf2;}
.brand-row {display:flex; align-items:center; gap:12px; margin: 5px 0 22px;}
.brand-icon {display:flex; width:43px; height:43px; align-items:center; justify-content:center; border-radius:13px; color:white; background:linear-gradient(135deg,#1758db,#4b8cff); font-size:23px;}
.brand-name {font-size:19px; font-weight:750; color:#14253d; line-height:1.1;}
.brand-sub {font-size:11px; letter-spacing:.11em; text-transform:uppercase; color:#6b7b91; margin-top:4px;}
.main-header {display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #e7ecf3; padding:0 0 17px 0; margin-bottom:16px;}
.main-title {font-size:25px; font-weight:750; letter-spacing:-.02em; color:#14253d;}
.main-sub {color:#738096; font-size:13px; margin-top:4px;}
.status-pill {display:inline-flex; align-items:center; gap:7px; border:1px solid #caeadb; color:#17764c; border-radius:100px; padding:5px 11px; font-size:12px; background:#f3fbf7;}
.dot {height:7px; width:7px; border-radius:50%; background:#27ad72; display:inline-block;}
.welcome {padding:24px; border:1px solid #e0e7f0; border-radius:20px; background:linear-gradient(135deg,#f5f9ff,#ffffff 70%); margin: 8px 0 20px;}
.welcome-title {font-size:24px; font-weight:720; color:#14253d; margin-bottom:7px;}
.welcome-copy {color:#617188; font-size:14px; max-width:710px;}
.metric-label {font-size:11px; color:#7d8a9b; text-transform:uppercase; letter-spacing:.08em;}
.session-hint {color:#718096; font-size:12px; margin-top:2px;}
div[data-testid="stChatMessage"] {border:1px solid #e7ecf2; border-radius:16px; padding:14px 16px; margin-bottom:10px; background:white;}
div[data-testid="stChatInput"] {border-radius:14px;}
div[data-testid="stButton"] button {border-radius:10px;}
section[data-testid="stSidebar"] .stButton button {text-align:left; border:1px solid transparent; background:transparent; color:#26354b; padding:9px 10px;}
section[data-testid="stSidebar"] .stButton button:hover {background:#eaf1fb; border-color:#dae6f9;}
.side-caption {font-size:11px; color:#8390a2; text-transform:uppercase; letter-spacing:.09em; font-weight:700; margin:20px 0 8px;}
.feature-card {border:1px solid #e5ebf3; border-radius:14px; padding:14px; height:100%; background:#fff;}
.feature-title {color:#1b2d45;font-weight:650;font-size:14px;margin-bottom:5px;}
.feature-copy {font-size:12px;color:#6b7a90;line-height:1.4;}
footer {visibility:hidden;}
</style>
''', unsafe_allow_html=True)

def api_get(path):
    return requests.get(f'{API_BASE}{path}',timeout=4)
def api_post(path,payload=None):
    return requests.post(f'{API_BASE}{path}',json=payload or {},timeout=90)


def iter_sse_events(response):
    """Yield (event, JSON payload) pairs from a Server-Sent Events response."""
    event_name = "message"
    data_lines = []
    for raw_line in response.iter_lines(decode_unicode=True):
        if raw_line is None:
            continue
        if isinstance(raw_line, bytes):
            raw_line = raw_line.decode("utf-8", errors="replace")
        line = raw_line.strip("\r")
        if not line:
            if data_lines:
                raw_data = "\n".join(data_lines)
                try:
                    payload = json.loads(raw_data)
                except json.JSONDecodeError:
                    payload = {"detail": raw_data}
                yield event_name, payload
            event_name = "message"
            data_lines = []
        elif line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if data_lines:
        try:
            payload = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            payload = {"detail": "\n".join(data_lines)}
        yield event_name, payload

def fetch_sessions():
    try:
        r=api_get('/sessions'); r.raise_for_status(); return r.json().get('sessions',[])
    except Exception as exc:
        st.session_state.backend_error=str(exc); return None

def create_session():
    r=api_post('/sessions',{})
    r.raise_for_status(); data=r.json()
    st.session_state.active_session_id=data['session_id']
    st.session_state.messages=[]
    st.session_state.session_refresh+=1

def load_session(sid):
    r=api_get(f'/sessions/{sid}'); r.raise_for_status(); data=r.json()
    st.session_state.active_session_id=sid
    st.session_state.messages=data.get('messages',[])
    st.session_state.session_detail=data

if 'active_session_id' not in st.session_state: st.session_state.active_session_id=None
if 'session_refresh' not in st.session_state: st.session_state.session_refresh=0
if 'upload_version' not in st.session_state: st.session_state.upload_version=0
if 'messages' not in st.session_state: st.session_state.messages=[]

# Sidebar: brand, session history, and session creation.
with st.sidebar:
    st.markdown('<div class="brand-row"><div class="brand-icon">⌁</div><div><div class="brand-name">TrackoBit</div><div class="brand-sub">Support workspace</div></div></div>',unsafe_allow_html=True)
    if st.button('＋  Start a new chat',use_container_width=True,type='primary'):
        try: create_session(); st.rerun()
        except Exception as exc: st.error(f'Could not create a chat: {exc}')
    st.markdown('<div class="side-caption">Your conversations</div>',unsafe_allow_html=True)
    sessions=fetch_sessions()
    if sessions is None:
        st.error('Backend API is not reachable.')
        st.caption('Start the app with `start_windows.bat` or run the API and UI separately.')
    elif not sessions:
        st.caption('Your support chats will appear here.')
    else:
        for item in sessions[:30]:
            selected=item['session_id']==st.session_state.active_session_id
            title=item.get('title') or 'Support chat'
            subtitle=item.get('last_message') or item.get('status','open').title()
            label=('●  ' if selected else '◦  ')+title
            if st.button(label,key='session_'+item['session_id'],use_container_width=True,help=subtitle):
                try: load_session(item['session_id']); st.rerun()
                except Exception as exc: st.error(f'Could not open session: {exc}')
    st.markdown('<div class="side-caption">Session tips</div>',unsafe_allow_html=True)
    st.caption('Each chat keeps its own history and troubleshooting step. You can return to a previous chat from this panel.')
    st.divider()
    st.caption('Local development · Session history is stored in `data/sessions`.')

# Auto-create the first session when the backend is available.
if not st.session_state.active_session_id and sessions is not None:
    try:
        if sessions: load_session(sessions[0]['session_id'])
        else: create_session()
        st.rerun()
    except Exception as exc:
        st.warning(f'Could not open a support session: {exc}')

st.markdown('''
<div class="main-header"><div><div class="main-title">Support chat</div><div class="main-sub">Real-time help for vehicle tracking and device diagnostics</div></div><div class="status-pill"><span class="dot"></span> Assistant ready</div></div>
''',unsafe_allow_html=True)

if not st.session_state.active_session_id:
    st.info('Start the API server, then create a support chat to begin.')
    st.stop()

# Header context card
try:
    detail=api_get(f"/sessions/{st.session_state.active_session_id}").json()
    state=detail.get('state') or {}
except Exception: state={}
vehicle=state.get('vehicle_no') or 'Not provided yet'
workflow=state.get('active_workflow') or 'none'
awaiting=state.get('awaiting') or 'none'
status_cols=st.columns([1.4,1,1,1.2])
with status_cols[0]:
    st.markdown(f'<div class="metric-label">Current session</div><div style="font-weight:650;color:#26354b;margin-top:4px;">{st.session_state.active_session_id[:8]}…</div>',unsafe_allow_html=True)
with status_cols[1]:
    st.markdown(f'<div class="metric-label">Vehicle number</div><div style="font-weight:650;color:#26354b;margin-top:4px;">{vehicle}</div>',unsafe_allow_html=True)
with status_cols[2]:
    st.markdown(f'<div class="metric-label">Workflow</div><div style="font-weight:650;color:#26354b;margin-top:4px;">{workflow.replace("_"," ").title()}</div>',unsafe_allow_html=True)
with status_cols[3]:
    awaiting_label=awaiting.replace('_',' ').title() if awaiting != 'none' else 'Waiting for your query'
    st.markdown(f'<div class="metric-label">Next step</div><div style="font-weight:650;color:#26354b;margin-top:4px;">{awaiting_label}</div>',unsafe_allow_html=True)
st.divider()

if not st.session_state.messages:
    st.markdown('''<div class="welcome"><div class="welcome-title">How can we help today?</div><div class="welcome-copy">Describe a vehicle tracking problem or ask a product how-to question. The assistant will keep the conversation in this session and guide you through one step at a time.</div></div>''',unsafe_allow_html=True)
    suggestion_cols=st.columns(3)
    suggestions=[('📍','Location not updating','Diagnose a GPS or stale-location problem.'),('⚙️','Device troubleshooting','Check tracker health and device command output.'),('📘','Product how-to','Ask how to use a feature or setting.')]
    for col,(icon,title,copy) in zip(suggestion_cols,suggestions):
        with col:
            st.markdown(f'<div class="feature-card"><div class="feature-title">{icon} &nbsp; {title}</div><div class="feature-copy">{copy}</div></div>',unsafe_allow_html=True)

# Draw transcript from saved session, rather than only Streamlit's transient state.
for row in st.session_state.messages:
    role=row.get('role','assistant')
    if role not in {'user','assistant'}: continue
    with st.chat_message(role,avatar='🧑‍💼' if role=='user' else '🛰️'):
        st.markdown(row.get('content',''))
        if row.get('attachment_name'): st.caption(f"Attached: {row['attachment_name']}")

send_attachment=False
with st.expander('Attach a diagnostic screenshot (optional)',expanded=False):
    uploaded=st.file_uploader('PNG, JPG or WEBP · up to 8 MB',type=['png','jpg','jpeg','webp'],key=f'upload_{st.session_state.upload_version}')
    if uploaded: 
        st.caption(f'Ready to attach: {uploaded.name} · {uploaded.size/1024:.0f} KB')
        send_attachment=st.button('Send screenshot',key=f'send_screenshot_{st.session_state.upload_version}')

prompt=st.chat_input('Describe the issue or answer the assistant…')
if prompt is not None or send_attachment:
    prompt=prompt or ''
    payload={'message':prompt}
    if 'uploaded' in locals() and uploaded is not None:
        payload.update({'attachment_base64':base64.b64encode(uploaded.getvalue()).decode('ascii'),'attachment_name':uploaded.name,
                        'attachment_mime_type':uploaded.type or 'image/png'})
    visible_user_text = prompt or 'Please analyze the attached diagnostic screenshot.'
    if 'uploaded' in locals() and uploaded is not None:
        visible_user_text += f"\n\n_Attached screenshot: {uploaded.name}_"

    # Show the new turn immediately while the server streams graph progress.
    with st.chat_message('user', avatar='🧑‍💼'):
        st.markdown(visible_user_text)
    with st.chat_message('assistant', avatar='🛰️'):
        with st.status('Message received. Starting the support workflow…', expanded=True) as workflow_status:
            progress_line = st.empty()
            answer_placeholder = st.empty()
            rendered_answer = ''
            completed_data = None
            stream_error = None
            try:
                with requests.post(
                    f"{API_BASE}/sessions/{st.session_state.active_session_id}/messages/stream",
                    json=payload,
                    stream=True,
                    timeout=(5, 180),
                ) as response:
                    if not response.ok:
                        try:
                            detail = response.json().get('detail', response.text)
                        except Exception:
                            detail = response.text
                        raise RuntimeError(f'Support request failed ({response.status_code}): {detail}')
                    for event_name, data in iter_sse_events(response):
                        if event_name == 'progress':
                            label = data.get('label', 'Working through the next support step…')
                            workflow_status.update(label=label, state='running', expanded=True)
                            progress_line.caption(label)
                        elif event_name == 'answer_chunk':
                            rendered_answer += data.get('text', '')
                            answer_placeholder.markdown(rendered_answer + '▌')
                        elif event_name == 'answer_reset':
                            rendered_answer = ''
                            answer_placeholder.empty()
                        elif event_name == 'complete':
                            completed_data = data
                        elif event_name == 'error':
                            stream_error = data.get('detail', 'The support request could not be completed.')
                            workflow_status.update(label='The request needs attention', state='error', expanded=True)
                            st.error(stream_error)
            except Exception as exc:
                stream_error = str(exc)
                workflow_status.update(label='Could not complete the request', state='error', expanded=True)
                st.error(f'Could not reach the support API: {stream_error}')

            if completed_data:
                answer_placeholder.markdown(completed_data.get('response') or rendered_answer)
                workflow_status.update(label='Response ready', state='complete', expanded=False)
                st.session_state.messages = completed_data.get('messages', [])
                st.session_state.upload_version += 1
                st.rerun()
            elif not stream_error:
                st.error('The connection ended before the support response was received. Please retry.')

st.markdown('<div style="color:#8793a4;font-size:11px;text-align:center;margin-top:10px;">Please do not send passwords or sensitive personal information. Device commands should only be used according to approved support procedures.</div>',unsafe_allow_html=True)
