import base64
import logging
import os
import queue
import threading
import uuid
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from trackobit_assistant.config.settings import get_settings
from trackobit_assistant.adapters.session_store_json import JsonSessionStore
from trackobit_assistant.adapters.vehicle_api import HttpVehicleApiClient
from trackobit_assistant.adapters.ticket_client import HttpTicketClient, LoggingTicketClient
from trackobit_assistant.adapters.command_registry import YamlCommandRegistry
from trackobit_assistant.adapters.knowledge_base import FileKnowledgeBase
from trackobit_assistant.graph.runtime import Runtime
from trackobit_assistant.graph.builder import build_graph
from trackobit_assistant.llm.factory import create_chat_model
from trackobit_assistant.services.prompt_repository import PromptRepository
from trackobit_assistant.formatters.message_renderer import MessageRenderer
from trackobit_assistant.app.streaming import chunk_text, format_sse_event, progress_label

class _SessionLogFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, 'session_id'): record.session_id='-'
        return True

settings=get_settings()

# Configure logging with both console and rotating/persistent file handlers
_log_format = '%(asctime)s [%(levelname)s] [%(name)s] session=%(session_id)s %(message)s'
_log_file = settings.data_dir / 'assistant.log'
_log_file.parent.mkdir(parents=True, exist_ok=True)

_session_filter = _SessionLogFilter()
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(logging.Formatter(_log_format))
_console_handler.addFilter(_session_filter)

_file_handler = logging.FileHandler(_log_file, encoding='utf-8')
_file_handler.setFormatter(logging.Formatter(_log_format))
_file_handler.addFilter(_session_filter)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
# Clear old handlers and attach configured ones
root_logger.handlers.clear()
root_logger.addHandler(_console_handler)
root_logger.addHandler(_file_handler)

for _name in ('trackobit_assistant', 'trackobit_assistant.api', 'trackobit_assistant.nodes', 'trackobit_assistant.routes'):
    logging.getLogger(_name).setLevel(logging.INFO)

logger=logging.getLogger('trackobit_assistant.api')
logger.info(f"Logging initialized. Log file: {_log_file.resolve()}")

# LangSmith reads configuration from the process environment.
os.environ['LANGSMITH_TRACING']='true' if settings.langsmith_tracing else 'false'
os.environ['LANGSMITH_PROJECT']=settings.langsmith_project
if settings.langsmith_api_key: os.environ['LANGSMITH_API_KEY']=settings.langsmith_api_key
store=JsonSessionStore(settings.session_dir)
vehicle_client=HttpVehicleApiClient(settings)
ticket_client=HttpTicketClient(settings) if settings.ticket_api_url else LoggingTicketClient()
command_registry=YamlCommandRegistry(settings.commands_dir)
knowledge_base=FileKnowledgeBase(settings.knowledge_dir)
llm=create_chat_model(settings)
vision_llm=create_chat_model(settings,vision=True)
prompt_repo=PromptRepository(Path('prompts'), version_config=settings.prompt_versions)
message_renderer=MessageRenderer(Path('templates/messages'))
runtime=Runtime(settings=settings,session_store=store,vehicle_client=vehicle_client,ticket_client=ticket_client,
                command_registry=command_registry,knowledge_base=knowledge_base,llm=llm,vision_llm=vision_llm,prompts=prompt_repo,messages=message_renderer)
graph=build_graph(runtime)

app=FastAPI(title=settings.app_name,version='0.1.0',description='Session-based TrackoBit support assistant API')
app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:8501','http://127.0.0.1:8501'],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])

class CreateSessionRequest(BaseModel): title: str | None = None
class MessageRequest(BaseModel):
    message: str = ''
    attachment_base64: str | None = None
    attachment_name: str | None = None
    attachment_mime_type: str | None = None
class MessageResponse(BaseModel):
    session_id: str
    response: str
    messages: list[dict[str, Any]]
    status: str
    awaiting: str = 'none'
    active_workflow: str = 'none'
    vehicle_no: str | None = None
    sources: list[str] = Field(default_factory=list)
    ticket_info: dict[str, Any] | None = None

@app.get('/health')
def health():
    return {'status':'ok','app':settings.app_name,'llm_provider':settings.llm_provider,'model_enabled':llm is not None,
            'knowledge_documents':len(getattr(knowledge_base,'_docs',[])),'command_device_types':len(getattr(command_registry,'_registry',{}))}

@app.get('/sessions')
def list_sessions(): return {'sessions':store.list_sessions()}

@app.post('/sessions')
def create_session(req: CreateSessionRequest | None = None):
    record=store.create_session()
    if req and req.title:
        full=store.get_session(record['session_id']); full['title']=req.title[:80]; store._write(full); record['title']=full['title']
    return record

@app.get('/sessions/{session_id}')
def get_session(session_id: str):
    record=store.get_session(session_id)
    if not record or record.get('session_id') != session_id: raise HTTPException(status_code=404,detail='Session not found')
    # Don't leak absolute attachment paths or private graph state.
    return {'session_id':record['session_id'],'title':record['title'],'created_at':record['created_at'],'updated_at':record['updated_at'],
            'status':record.get('status','open'),'messages':record.get('messages',[]),'state':{
                'vehicle_no':(record.get('state') or {}).get('vehicle_no'), 'active_workflow':(record.get('state') or {}).get('active_workflow','none'),
                'awaiting':(record.get('state') or {}).get('awaiting','none'),'fault_category':(record.get('state') or {}).get('fault_category'),
                'ticket_info':(record.get('state') or {}).get('ticket_info')}}

def _process_message(session_id: str, req: MessageRequest, on_progress=None, on_token=None) -> MessageResponse:
    record=store.get_session(session_id)
    if not record or record.get('session_id') != session_id: raise HTTPException(status_code=404,detail='Session not found')
    message_text=req.message.strip()
    screenshot_path=None
    attachment_label=None
    if req.attachment_base64:
        if req.attachment_mime_type not in {'image/png','image/jpeg','image/webp'}:
            raise HTTPException(status_code=400,detail='Only PNG, JPEG or WEBP screenshots are supported')
        try: binary=base64.b64decode(req.attachment_base64,validate=True)
        except Exception: raise HTTPException(status_code=400,detail='Invalid screenshot encoding')
        if len(binary)>8*1024*1024: raise HTTPException(status_code=413,detail='Screenshot must be 8 MB or smaller')
        suffix={'image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp'}[req.attachment_mime_type]
        target_dir=settings.upload_dir/record['session_id']
        target_dir.mkdir(parents=True,exist_ok=True)
        screenshot_path=str(target_dir/f'{uuid.uuid4().hex}{suffix}')
        Path(screenshot_path).write_bytes(binary)
        attachment_label=req.attachment_name or 'diagnostic screenshot'
    if not message_text and not screenshot_path: raise HTTPException(status_code=400,detail='Enter a message or attach a screenshot')
    if not message_text: message_text='Please analyze the attached diagnostic screenshot.'
    display_content=message_text+(f'\n\n[Attached screenshot: {attachment_label}]' if attachment_label else '')
    
    logger.info(
        f"[API] ===> INCOMING MESSAGE session={session_id} | message='{message_text}' | attachment={attachment_label}",
        extra={'session_id': session_id}
    )
    prior_state = store.state_for(session_id) or {}
    logger.info(
        f"[API] Current state before processing: workflow='{prior_state.get('active_workflow', 'none')}', awaiting='{prior_state.get('awaiting', 'none')}', vehicle_no='{prior_state.get('vehicle_no')}', retry_counters={prior_state.get('retry_counters', {})}",
        extra={'session_id': session_id}
    )

    history=record.get('messages') or []
    messages=[]
    for row in history:
        role=row.get('role','user'); mid=row.get('id') or str(uuid.uuid4()); content=row.get('content','')
        cls={'user':HumanMessage,'assistant':AIMessage,'system':SystemMessage,'tool':ToolMessage}.get(role,HumanMessage)
        if cls is ToolMessage:
            messages.append(ToolMessage(content=content,tool_call_id='stored-tool-message',id=mid))
        else: messages.append(cls(content=content,id=mid))
    user_id=str(uuid.uuid4())
    messages.append(HumanMessage(content=display_content,id=user_id))
    graph_input=store.state_for(session_id) or {'session_id':session_id}
    graph_input.update({
      'session_id':session_id,'messages':messages,'last_user_message':message_text,'screenshot_path':screenshot_path,
      'response':'','sources':[],'target_frame_id':None,'resume_prefix':None,'resume_announcement':False,'resume_represent_step':False,
      'parsed_command_output':None,'command_verdict':None,'command_analysis':None,'retry_exhausted':False,
      'vehicle_no_valid':False,'api_ok':None,'api_error':None,'rag_confidence':None,'ticket_info':graph_input.get('ticket_info'),
      'intent':None,'intent_confidence':None,'query_kind':None,'query_confidence':None,
      'dashboard_evidence':graph_input.get('dashboard_evidence'), 'pending_intents':[],
    })
    snap=graph_input.get('vehicle_snapshot') or {}
    config={'configurable':{'thread_id':session_id},'metadata':{'session_id':session_id,'vehicle_no':graph_input.get('vehicle_no'),
        'device_type':snap.get('device_type'),'workflow':graph_input.get('active_workflow','none')},'tags':['trackobit-support','chat-turn']}
    if on_token is not None:
        # Configurable values are passed directly to graph nodes and remain per request.
        config['configurable']['_trackobit_stream_token_callback'] = on_token
    try:
        # Stream node updates so the UI can show real graph progress. The final
        # reducer-merged state is restored from the LangGraph checkpointer.
        logger.info(f"[API] Starting LangGraph execution stream for session={session_id}...", extra={'session_id': session_id})
        for update in graph.stream(graph_input, config=config, stream_mode='updates'):
            for node_name in update:
                logger.info(f"[API] [GRAPH UPDATE] Node '{node_name}' finished executing", extra={'session_id': session_id})
                if on_progress:
                    try:
                        on_progress(node_name)
                    except Exception:
                        logger.debug('Progress callback failed', extra={'session_id': session_id})
        checkpoint = graph.get_state(config)
        result = dict(checkpoint.values) if checkpoint and checkpoint.values else {}
        if not result:
            raise RuntimeError('LangGraph completed without a final state')
        store.save_graph_result(session_id,result)
    except Exception as exc:
        logger.exception('Graph invocation failed',extra={'session_id':session_id})
        # Global failure path: retain the turn and try a handoff ticket without leaking stack traces.
        error_ticket = None
        try:
            if not graph_input.get('ticket_info'):
                ticket = ticket_client.create(
                    summary=f"Automated workflow failed while handling: {message_text[:500]}",
                    reason='unexpected_graph_error',
                    metadata={'session_id': session_id, 'vehicle_no': graph_input.get('vehicle_no'),
                              'assigned_to': settings.assign_to_support_user},
                )
                error_ticket = ticket.model_dump(mode='json')
        except Exception as ticket_exc:
            logger.error('Fallback ticket creation failed: %s', type(ticket_exc).__name__, extra={'session_id': session_id})
        if error_ticket and error_ticket.get('ticket_id'):
            response = f"The automated workflow hit an unexpected issue, so I’m handing this to support. Ticket **{error_ticket['ticket_id']}** was created. Your conversation is saved."
        else:
            response = f"The automated workflow hit an unexpected issue. Your conversation is saved under session `{session_id}`, but I couldn’t confirm an automatic support ticket. Please share this session ID with the support team."
        fallback={'session_id':session_id,'messages':messages+[AIMessage(content=response,id=str(uuid.uuid4()))],
                  'errors':(graph_input.get('errors') or [])+[f'graph_error:{type(exc).__name__}'],
                  'response':response,'active_workflow':'handoff','handoff_reason':'unexpected_graph_error',
                  'ticket_info':error_ticket}
        try: store.save_graph_result(session_id,fallback)
        except Exception as save_exc: logger.error('Could not persist fallback result: %s', type(save_exc).__name__, extra={'session_id': session_id})
        result=fallback
    current=store.get_session(session_id) or record
    state=current.get('state') or {}
    final_resp_preview = ((result.get('response') or '')[:100]).replace('\n', ' ')
    logger.info(
        f"[API] <=== TURN COMPLETE session={session_id} | status='{current.get('status','open')}' | workflow='{state.get('active_workflow','none')}' | awaiting='{state.get('awaiting','none')}' | response='{final_resp_preview}'",
        extra={'session_id': session_id}
    )
    return MessageResponse(session_id=session_id,response=result.get('response') or 'Please tell me a little more about the issue.',
        messages=current.get('messages') or [],status=current.get('status','open'),awaiting=state.get('awaiting','none'),
        active_workflow=state.get('active_workflow','none'),vehicle_no=state.get('vehicle_no'),sources=result.get('sources') or [],ticket_info=state.get('ticket_info'))


@app.post('/sessions/{session_id}/messages', response_model=MessageResponse)
def send_message(session_id: str, req: MessageRequest):
    """Standard request/response endpoint retained for API clients and tests."""
    return _process_message(session_id, req)


@app.post('/sessions/{session_id}/messages/stream')
def send_message_stream(session_id: str, req: MessageRequest):
    """Send live graph-progress events, streamed answer chunks, and a final session snapshot."""
    record = store.get_session(session_id)
    if not record or record.get('session_id') != session_id:
        raise HTTPException(status_code=404, detail='Session not found')

    def event_generator():
        events: queue.Queue = queue.Queue()
        finished = object()

        def push_progress(node_name: str) -> None:
            events.put(('progress', {'node': node_name, 'label': progress_label(node_name)}))

        def push_token(text: str | None) -> None:
            if text is None:
                events.put(('answer_reset', {}))
            else:
                events.put(('model_token', {'text': text}))

        def run_turn() -> None:
            try:
                result = _process_message(session_id, req, on_progress=push_progress, on_token=push_token)
                events.put(('result', result.model_dump(mode='json')))
            except HTTPException as exc:
                events.put(('error', {'status_code': exc.status_code, 'detail': exc.detail}))
            except Exception:
                logger.exception('Streaming chat turn failed', extra={'session_id': session_id})
                events.put(('error', {'status_code': 500, 'detail': 'The support request could not be completed. Please retry.'}))
            finally:
                events.put(('finished', finished))

        yield format_sse_event('progress', {'node': 'accepted', 'label': 'Message received. Starting the support workflow…'})
        worker = threading.Thread(target=run_turn, name=f'support-turn-{session_id[:8]}', daemon=True)
        worker.start()
        live_model_answer = ''
        while True:
            try:
                item_type, payload = events.get(timeout=15)
            except queue.Empty:
                # Keep intermediaries from treating a long model/API step as idle.
                yield ': keep-alive\n\n'
                continue
            if item_type == 'finished':
                break
            if item_type == 'progress':
                yield format_sse_event('progress', payload)
            elif item_type == 'error':
                yield format_sse_event('error', payload)
            elif item_type == 'model_token':
                live_model_answer += payload.get('text', '')
                yield format_sse_event('answer_chunk', {'text': payload.get('text', '')})
            elif item_type == 'answer_reset':
                live_model_answer = ''
                yield format_sse_event('answer_reset', {})
            elif item_type == 'result':
                # RAG text is streamed from the model itself. Send any remaining suffix
                # (for example source citations); template-based replies use display chunks.
                final_text = payload.get('response', '')
                if live_model_answer and final_text.startswith(live_model_answer):
                    remainder = final_text[len(live_model_answer):]
                else:
                    if live_model_answer:
                        yield format_sse_event('answer_reset', {})
                    remainder = final_text
                for chunk in chunk_text(remainder):
                    yield format_sse_event('answer_chunk', {'text': chunk})
                yield format_sse_event('complete', payload)

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no', 'Connection': 'keep-alive'},
    )


@app.post('/sessions/{session_id}/close')
def close_session(session_id: str):
    record=store.get_session(session_id)
    if not record or record.get('session_id') != session_id: raise HTTPException(status_code=404,detail='Session not found')
    record['status']='closed'; store._write(record)
    return {'session_id':session_id,'status':'closed'}
