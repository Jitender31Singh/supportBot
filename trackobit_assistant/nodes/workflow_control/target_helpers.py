def choose_target(state):
    frames=[f for f in (state.get('workflow_stack') or []) if f.get('status') in {'paused','stale'}]
    text=(state.get('last_user_message') or '').strip()
    try: idx=int(text)-1
    except ValueError: idx=-1
    if 0 <= idx < len(frames): return frames[idx].get('frame_id')
    low=text.casefold()
    matches=[f for f in frames if f.get('frame_id') in text or f.get('type','').casefold() in low or (f.get('paused_at_step') or '').casefold() in low]
    if len(matches)==1: return matches[0].get('frame_id')
    if len(frames)==1: return frames[0].get('frame_id')
    return None
