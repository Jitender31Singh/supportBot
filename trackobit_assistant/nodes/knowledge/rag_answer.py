from langchain_core.messages import HumanMessage, SystemMessage


def _content_text(content):
    """Normalize either a string or a list of text content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(block.get("text", "")) for block in content if isinstance(block, dict) and block.get("type") == "text")
    return str(content)


import logging

logger = logging.getLogger('trackobit_assistant.nodes.rag_answer')

def make_node(runtime):
    def node(state, config=None):
        session_id = state.get('session_id', '-')
        query = state.get('last_user_message', '')

        # Check if the query matches an active known bug in Pinecone
        bug_store = getattr(runtime, 'bug_store', None)
        if bug_store is not None:
            try:
                matched_bug = bug_store.search_active_bug(query, llm=runtime.llm)
            except Exception as e:
                logger.warning(f"[RAG_ANSWER] Pinecone bug search error: {e}")
                matched_bug = None

            if matched_bug:
                title = matched_bug.get('title')
                bug_id = matched_bug.get('bug_id')
                workaround = matched_bug.get('workaround') or 'Our engineering team is actively working on a fix.'
                eta = matched_bug.get('eta') or 'in progress'
                logger.info(f"[RAG_ANSWER] Query matched active known bug {bug_id} ({title})")
                resp = (
                    f"⚠️ We have identified this as an active known issue: **{title}** (Reference: `{bug_id}`).\n\n"
                    f"• **Status**: Active (Fix ETA: {eta})\n"
                    f"• **Workaround**: {workaround}\n\n"
                    f"Our engineering team is actively resolving this issue."
                )
                return {
                    'response': resp,
                    'sources': [f'Known Outages: {bug_id}'],
                    'rag_confidence': 0.95,
                    'rag_confidence_threshold': runtime.settings.rag_confidence_threshold,
                    'active_workflow': 'none',
                    'awaiting': 'none',
                    'resolved': True,
                    'fault_category': 'known_software_outage',
                    'known_bug': matched_bug,
                }

        logger.info(f"[RAG_ANSWER] Searching knowledge base for query: '{query}'", extra={'session_id': session_id})
        docs=runtime.knowledge_base.search(query,k=4)
        sources=list(dict.fromkeys(d.get('source','unknown') for d in docs))
        if not docs:
            logger.warning(f"[RAG_ANSWER] No matching documents found for query: '{query}'", extra={'session_id': session_id})
            return {'response':"I couldn’t find an approved answer for that in the current support knowledge base, so I don’t want to guess. Please share a little more context or I can pass this to the support team.",
                    'sources':[],'rag_confidence':0.0,'rag_confidence_threshold':runtime.settings.rag_confidence_threshold,'active_workflow':'none','awaiting':'none'}
        logger.info(f"[RAG_ANSWER] Found {len(docs)} documents. Sources: {sources}", extra={'session_id': session_id})
        context='\n\n'.join(f"SOURCE: {d['source']}\n{d['content']}" for d in docs)
        if runtime.llm is not None:
            prompt=(runtime.prompts.render('rag_answer',question=query,context=context) if runtime.prompts else f'Answer only from context. If insufficient, say so.\nQuestion:{query}\nContext:{context}')
            messages=[SystemMessage(content=prompt),HumanMessage(content=query)]
            configurable = (config or {}).get('configurable', {})
            token_callback = configurable.get('_trackobit_stream_token_callback')
            if token_callback is not None:
                # Provider tokens are sent to the UI as they arrive. If streaming fails
                # after partial output, reset the UI before falling back to grounded text.
                pieces=[]
                try:
                    for chunk in runtime.llm.stream(messages):
                        text=_content_text(getattr(chunk, 'content', ''))
                        if text:
                            pieces.append(text)
                            token_callback(text)
                    response=''.join(pieces)
                    if not response.strip():
                        token_callback(None)
                        response=f"Here’s what the support knowledge base says:\n\n{docs[0]['content']}"
                        confidence=.55
                    else:
                        confidence=.82
                    logger.info(f"[RAG_ANSWER] Streamed LLM answer completed (confidence={confidence:.2f})", extra={'session_id': session_id})
                except Exception as exc:
                    token_callback(None)
                    logger.warning(f"[RAG_ANSWER] LLM streaming failed ({type(exc).__name__}: {exc}); falling back to document content", extra={'session_id': session_id})
                    response=f"Here’s what the support knowledge base says:\n\n{docs[0]['content']}"
                    confidence=.55
            else:
                try:
                    answer=runtime.llm.invoke(messages)
                    response=_content_text(answer.content)
                    confidence=.82
                    logger.info(f"[RAG_ANSWER] LLM generated answer (confidence={confidence:.2f})", extra={'session_id': session_id})
                except Exception as exc:
                    logger.warning(f"[RAG_ANSWER] LLM invoke failed ({type(exc).__name__}: {exc}); falling back to document content", extra={'session_id': session_id})
                    response=f"Here’s what the support knowledge base says:\n\n{docs[0]['content']}"
                    confidence=.55
        else:
            response=f"Here’s the closest match in the local support knowledge base:\n\n{docs[0]['content']}"
            confidence=float(docs[0].get('score',.4))
            logger.info(f"[RAG_ANSWER] Demo mode: returning top document (confidence={confidence:.2f})", extra={'session_id': session_id})
        if sources: response+='\n\nSources: '+', '.join(sources)
        return {'response':response,'sources':sources,'rag_confidence':confidence,'rag_confidence_threshold':runtime.settings.rag_confidence_threshold,'active_workflow':'none','awaiting':'none'}
    return node
