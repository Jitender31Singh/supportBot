"""Extract command output from screenshots or pasted text using a registry-derived schema."""
from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any
from pydantic import Field, create_model
from langchain_core.messages import HumanMessage, SystemMessage


def _type_for_registry(spec: dict[str, Any]):
    return {
        'string': str, 'integer': int, 'number': float, 'boolean': bool,
        'object': dict[str, Any], 'array': list[Any],
    }.get(str(spec.get('type', 'string')).casefold(), str)


def _model_for_command(command: dict[str, Any]):
    """Build a structured vision-output model from the selected CommandSpec schema."""
    fields: dict[str, tuple[Any, Any]] = {
        'readable': (bool, True),
        'detected_command': (str | None, None),
        'raw_text': (str, ''),
        'confidence': (float, Field(default=0.6, ge=0, le=1)),
    }
    for name, spec in (command.get('output_schema') or {}).items():
        fields[name] = (_type_for_registry(spec) | None, None)
    safe_name = re.sub(r'\W+', '_', str(command.get('id') or 'command')).strip('_') or 'command'
    return create_model(f'ScreenshotAnalysis_{safe_name}', **fields)


def _parse_text(text: str, output_schema: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parse common device-output labels for local mode; vision LLM handles complex formats."""
    out: dict[str, Any] = {'raw_text': text}
    patterns: dict[str, tuple[str, Any]] = {
        'gsm_signal': (r'(?i)(?:gsm(?:\s*signal)?|signal)\s*[:= -]\s*(\d+)', int),
        'satellites': (r'(?i)(?:satellites|satellite|sats)\s*[:= -]\s*(\d+)', int),
        'battery_voltage': (r'(?i)(?:battery(?:\s*voltage)?|voltage|vbat)\s*[:= -]\s*(\d+(?:\.\d+)?)\s*v?', float),
        'port': (r'(?i)\bport\s*[:= -]\s*(\d+)', int),
        'apn': (r'(?i)\bapn\s*[:= -]\s*([A-Za-z0-9_.-]+)', str),
        'server': (r'(?i)\bserver\s*[:= -]\s*([A-Za-z0-9_.-]+)', str),
    }
    wanted = set(output_schema or {})
    for key, (pattern, convert) in patterns.items():
        if wanted and key not in wanted:
            continue
        match = re.search(pattern, text)
        if match:
            out[key] = convert(match.group(1))
    gps = re.search(r'(?i)(?:gps(?:\s*fix)?|gps status)\s*[:= -]\s*(fixed|fix|yes|no|valid|invalid|0|1)', text)
    if gps and (not wanted or 'gps_fix' in wanted):
        out['gps_fix'] = gps.group(1).casefold()
    gprs = re.search(r'(?i)(?:gprs|server connection|connected)\s*[:= -]\s*(connected|disconnected|yes|no|true|false|0|1)', text)
    if gprs and (not wanted or 'gprs_connected' in wanted):
        out['gprs_connected'] = gprs.group(1).casefold() in {'connected', 'yes', 'true', '1'}
    if re.search(r'(?i)\bSTATUS\s*#', text):
        out['detected_command'] = 'STATUS#'
    elif re.search(r'(?i)\bPARAM\s*#', text):
        out['detected_command'] = 'PARAM#'
    return out


import logging

logger = logging.getLogger('trackobit_assistant.nodes.process_screenshot')

def make_node(runtime):
    def node(state):
        session_id = state.get('session_id', '-')
        cmd = state.get('current_command') or {}
        path = state.get('screenshot_path')
        raw_text = state.get('last_user_message', '')
        schema = cmd.get('output_schema') or {}
        parsed = None

        logger.info(f"[PROCESS_SCREENSHOT] Processing screenshot for command '{cmd.get('command')}'; screenshot_path={path}", extra={'session_id': session_id})

        if path and runtime.vision_llm is not None:
            try:
                suffix = Path(path).suffix.casefold()
                media = 'image/png' if suffix == '.png' else ('image/webp' if suffix == '.webp' else 'image/jpeg')
                b64 = base64.b64encode(Path(path).read_bytes()).decode('ascii')
                prompt = (
                    f"Read this screenshot of device command {cmd.get('command')}. "
                    f"Extract only visible facts into these fields: {list(schema)}. "
                    "Do not infer missing fields. If the output belongs to another command, set detected_command. "
                    "Set readable=false if text is not legible."
                )
                message = HumanMessage(content=[
                    {'type': 'text', 'text': prompt},
                    {'type': 'image_url', 'image_url': {'url': f'data:{media};base64,{b64}'}},
                ])
                parsed = runtime.vision_llm.with_structured_output(_model_for_command(cmd)).invoke([
                    SystemMessage(content='You are a careful diagnostic screenshot reader. Extract visible facts only.'), message
                ]).model_dump()
                logger.info(f"[PROCESS_SCREENSHOT] Vision LLM parsed result: {parsed}", extra={'session_id': session_id})
            except Exception as exc:
                logger.warning(f"[PROCESS_SCREENSHOT] Vision LLM failed ({type(exc).__name__}: {exc})", extra={'session_id': session_id})
                parsed = {'readable': False, 'raw_text': '', 'confidence': 0.0, 'error': type(exc).__name__}

        elif raw_text and any(re.search(p, raw_text, re.I) for p in (
            r'\bgsm\b', r'\bgprs\b', r'\bgps\b', r'\bbattery\b', r'\bsatellite\b',
            r'\bstatus\s*#', r'\bparam\s*#', r'\bapn\b', r'\bserver\b', r'\bport\b',
        )):
            parsed = _parse_text(raw_text, schema)
            parsed['readable'] = any(parsed.get(key) is not None for key in schema)
            parsed['confidence'] = 0.75
            logger.info(f"[PROCESS_SCREENSHOT] Regex text parsing result: {parsed}", extra={'session_id': session_id})

        elif path:
            logger.warning("[PROCESS_SCREENSHOT] Vision LLM not available in current configuration", extra={'session_id': session_id})
            return {
                'response': 'I received the screenshot, but screenshot reading is disabled in local demo mode. Enable `LLM_PROVIDER=anthropic` and set `ANTHROPIC_API_KEY`, or paste the command reply text here (for example: `GPS: fixed, GSM: 4, GPRS: connected, Battery: 3.9V`).',
                'awaiting': 'command_screenshot',
                'paused_at_step': f"waiting for readable output from {cmd.get('command', 'the current command')}",
                'current_step': 'process_screenshot',
            }

        if parsed and parsed.get('detected_command'):
            expected = re.sub(r'\s+', '', str(cmd.get('command', '')).upper())
            detected = re.sub(r'\s+', '', str(parsed['detected_command']).upper())
            if expected and detected != expected:
                logger.warning(f"[PROCESS_SCREENSHOT] Wrong command detected: expected '{expected}', got '{detected}'", extra={'session_id': session_id})
                return _retry_screenshot(state, runtime, cmd, wrong_command=True)

        has_schema_value = bool(parsed) and any(parsed.get(key) is not None for key in schema)
        if not parsed or not parsed.get('readable', True) or not has_schema_value:
            logger.warning(f"[PROCESS_SCREENSHOT] Unreadable or empty schema output: parsed={parsed}", extra={'session_id': session_id})
            return _retry_screenshot(state, runtime, cmd, wrong_command=False)

        logger.info(f"[PROCESS_SCREENSHOT] Successfully extracted command output fields: {list(parsed.keys())}", extra={'session_id': session_id})
        return {
            'parsed_command_output': parsed, 'screenshot_retry_count': 0,
            'response': 'I’ve extracted the visible fields from the device reply. I’m checking them against the configured device rules now.',
            'current_step': 'analyze_output',
        }
    return node


def _retry_screenshot(state, runtime, command: dict[str, Any], *, wrong_command: bool) -> dict[str, Any]:
    retries = int(state.get('screenshot_retry_count') or 0) + 1
    command_text = command.get('command', 'the current command')
    if retries >= runtime.settings.max_unreadable_screenshot_retries:
        reason = 'wrong_command_output' if wrong_command else 'unreadable_command_output'
        return {
            'screenshot_retry_count': retries, 'retry_exhausted': True, 'handoff_reason': reason,
            'response': 'I couldn’t verify the expected command output after multiple attempts. I’ll send the case to support rather than make an unsafe assumption.',
            'current_step': 'human_handoff',
        }
    if wrong_command:
        response = f'This appears to be output from a different command. Please send `{command_text}` exactly and attach a screenshot of that reply.'
    else:
        response = f'I can’t read the required fields for `{command_text}` clearly yet. Please send a sharper screenshot showing the entire reply, or paste the output as text.'
    return {
        'screenshot_retry_count': retries, 'response': response, 'awaiting': 'command_screenshot',
        'paused_at_step': f'waiting for a readable screenshot of {command_text}', 'current_step': 'process_screenshot',
    }
