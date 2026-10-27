import base64
import json
import os
import requests
import streamlit as st

API_BASE=os.getenv('UI_API_BASE_URL','http://127.0.0.1:8000').strip().rstrip('/')
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
def api_delete(path):
    return requests.delete(f'{API_BASE}{path}',timeout=15)


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

if 'active_view' not in st.session_state:
    st.session_state.active_view = "💬 Customer Support Chat"

view = st.radio(
    "Navigation",
    ["💬 Customer Support Chat", "🐞 Known Software Bugs (Pinecone RAG)"],
    horizontal=True,
    label_visibility="collapsed",
    key="active_view",
)

if view == "💬 Customer Support Chat":
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

else:
    st.markdown("### 🐞 Known Issues & Outages Management (Pinecone RAG)")
    st.caption("Active software issues and portal outages stored in Pinecone for semantic vector search. Support agents can add, edit, or delete bugs in real-time.")

    # Fetch current bugs from API
    try:
        bugs_res = api_get('/bugs')
        known_bugs = bugs_res.json().get('bugs', []) if bugs_res.ok else []
    except Exception:
        known_bugs = []

    col_list, col_form = st.columns([1.2, 1])

    with col_list:
        st.subheader(f"Active Incidents ({len(known_bugs)})")
        if not known_bugs:
            st.info("No active bugs or outages currently reported. Tracking queries follow standard hardware troubleshooting.")
        else:
            for bug in known_bugs:
                bid = bug.get('bug_id', 'UNKNOWN')
                btitle = bug.get('title', 'Untitled Bug')
                bsev = bug.get('severity', 'Medium')
                bstatus = bug.get('status', 'active')
                bworkaround = bug.get('workaround') or 'None provided'
                beta = bug.get('eta') or 'In progress'
                bsymptoms = bug.get('symptoms', '')

                sev_color = {'Critical': '#ff4b4b', 'High': '#ff8c00', 'Medium': '#185adb', 'Low': '#27ad72'}.get(bsev, '#185adb')

                with st.expander(f"**[{bid}] {btitle}** ({bsev})", expanded=True):
                    is_editing = (st.session_state.get('editing_bug_id') == bid)

                    if not is_editing:
                        st.markdown(f"**Severity**: <span style='color:{sev_color};font-weight:700;'>{bsev}</span> &nbsp;|&nbsp; **Status**: `{bstatus}`", unsafe_allow_html=True)
                        st.markdown(f"**Symptoms / Customer phrasing**: `{bsymptoms}`")
                        st.markdown(f"**Workaround**: {bworkaround}")
                        st.markdown(f"**Estimated Fix**: {beta}")

                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            if st.button(f"✏️ Edit Bug", key=f"edit_btn_{bid}", use_container_width=True):
                                st.session_state.editing_bug_id = bid
                                st.rerun()
                        with col_btn2:
                            if st.button(f"🗑️ Delete / Resolve", key=f"del_bug_{bid}", type="secondary", use_container_width=True):
                                try:
                                    del_res = api_delete(f"/bugs/{bid}")
                                    if del_res.ok:
                                        st.success(f"Bug {bid} deleted from Pinecone.")
                                        st.rerun()
                                    else:
                                        st.error(f"Failed to delete bug: {del_res.text}")
                                except Exception as e:
                                    st.error(f"Error deleting bug: {e}")
                    else:
                        st.markdown(f"#### ✏️ Edit Incident `{bid}`")
                        with st.form(key=f"edit_bug_form_{bid}"):
                            edit_title = st.text_input("Title / Component*", value=btitle)
                            edit_symptoms = st.text_area(
                                "Customer Symptoms / Keywords*",
                                value=bsymptoms,
                                help="Phrases that customers might say. Re-indexes in Pinecone for semantic vector search."
                            )
                            edit_workaround = st.text_input("Workaround", value=bworkaround if bworkaround != 'None provided' else "")
                            edit_eta = st.text_input("Estimated Fix Time (ETA)", value=beta if beta != 'In progress' else "")
                            
                            sev_options = ["Critical", "High", "Medium", "Low"]
                            sev_idx = sev_options.index(bsev) if bsev in sev_options else 2
                            edit_sev = st.selectbox("Severity", sev_options, index=sev_idx)
                            
                            status_options = ["active", "resolved"]
                            status_idx = status_options.index(bstatus) if bstatus in status_options else 0
                            edit_status = st.selectbox("Status", status_options, index=status_idx)

                            save_col1, save_col2 = st.columns(2)
                            with save_col1:
                                save_clicked = st.form_submit_button("💾 Save Changes to Pinecone", type="primary", use_container_width=True)
                            with save_col2:
                                cancel_clicked = st.form_submit_button("❌ Cancel", use_container_width=True)

                            if save_clicked:
                                if not edit_title.strip() or not edit_symptoms.strip():
                                    st.error("Title and Symptoms are required.")
                                else:
                                    update_payload = {
                                        "bug_id": bid,
                                        "title": edit_title.strip(),
                                        "symptoms": edit_symptoms.strip(),
                                        "workaround": edit_workaround.strip(),
                                        "eta": edit_eta.strip(),
                                        "severity": edit_sev,
                                        "status": edit_status,
                                    }
                                    try:
                                        res = api_post('/bugs', update_payload)
                                        if res.ok:
                                            st.success(f"✅ Bug {bid} updated successfully in Pinecone!")
                                            st.session_state.editing_bug_id = None
                                            st.rerun()
                                        else:
                                            st.error(f"Failed to update bug: {res.text}")
                                    except Exception as e:
                                        st.error(f"Error calling API: {e}")
                            elif cancel_clicked:
                                st.session_state.editing_bug_id = None
                                st.rerun()

    with col_form:
        st.subheader("➕ Add / Index New Bug")
        with st.form("add_bug_form", clear_on_submit=True):
            new_id = st.text_input("Bug / Incident ID*", placeholder="e.g. BUG-101", help="Unique reference code")
            new_title = st.text_input("Title / Component*", placeholder="e.g. Web Portal Live Tracking Buffering")
            new_symptoms = st.text_area(
                "Customer Symptoms / Keywords*",
                placeholder="e.g. device is buffering, live map updates delayed, screen freezing, coordinates not advancing",
                help="Enter natural language phrases that customers might say. Pinecone embeds this for semantic vector search."
            )
            new_workaround = st.text_input("Customer Workaround", placeholder="e.g. Please use the Trackobit Mobile App while web streaming is being patched.")
            new_eta = st.text_input("Estimated Fix Time (ETA)", placeholder="e.g. Today by 3:00 PM IST")
            new_sev = st.selectbox("Severity", ["Critical", "High", "Medium", "Low"], index=2)

            submitted = st.form_submit_button("➕ Index Bug into Pinecone", type="primary", use_container_width=True)
            if submitted:
                if not new_id.strip() or not new_title.strip() or not new_symptoms.strip():
                    st.error("Please fill in Bug ID, Title, and Symptoms.")
                else:
                    payload = {
                        "bug_id": new_id.strip(),
                        "title": new_title.strip(),
                        "symptoms": new_symptoms.strip(),
                        "workaround": new_workaround.strip(),
                        "eta": new_eta.strip(),
                        "severity": new_sev,
                        "status": "active"
                    }
                    try:
                        add_res = api_post('/bugs', payload)
                        if add_res.ok:
                            st.success(f"✅ Bug {new_id} indexed in Pinecone successfully!")
                            st.rerun()
                        else:
                            st.error(f"Error indexing bug: {add_res.text}")
                    except Exception as e:
                        st.error(f"Error calling API: {e}")

        st.divider()
        st.subheader("🔍 Vector Search Sandbox")
        st.caption("Test how a customer complaint matches known bugs in Pinecone in real-time.")
        test_query = st.text_input("Test customer phrase:", placeholder="e.g. vehicles are lagging behind real-time on dashboard")
        test_thresh = st.slider("Min similarity score", min_value=0.50, max_value=0.95, value=0.65, step=0.01)
        if st.button("Test Search in Pinecone", use_container_width=True):
            if test_query.strip():
                try:
                    s_res = api_post('/bugs/search', {"query": test_query.strip(), "min_similarity": test_thresh})
                    if s_res.ok:
                        match = s_res.json().get('match')
                        if match:
                            st.success(f"🎯 Matched: **{match.get('title')}** (Score: `{match.get('similarity_score')}`)")
                            st.json(match)
                        else:
                            st.warning("No active bug matched above the similarity threshold. The bot will proceed with normal troubleshooting.")
                    else:
                        st.error(f"Search failed: {s_res.text}")
                except Exception as e:
                    st.error(f"Error: {e}")

