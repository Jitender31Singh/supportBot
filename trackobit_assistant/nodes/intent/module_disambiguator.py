import logging
from typing import Any, Dict

from trackobit_assistant.graph.state import AssistantState

logger = logging.getLogger("trackobit_assistant.nodes.module_disambiguator")


def make_node(runtime: Any):
    def node(state: AssistantState) -> Dict[str, Any]:
        session_id = state.get("session_id", "-")
        user_msg = (state.get("last_user_message") or "").strip()
        awaiting = state.get("awaiting")
        taxonomy = getattr(runtime, "module_taxonomy", None)

        if taxonomy is None:
            logger.info("[MODULE_DISAMBIGUATOR] No module taxonomy service configured; passing through.", extra={"session_id": session_id})
            return {"current_step": "module_disambiguator"}

        # ----------------------------------------------------------------------
        # Case A: User is responding to a previous module choice prompt
        # ----------------------------------------------------------------------
        if awaiting == "module_choice":
            candidates = state.get("candidate_modules") or []
            resolved_module = taxonomy.resolve_user_choice(user_msg, candidates)

            if resolved_module:
                meta = taxonomy.get_module(resolved_module) or {}
                module_name = meta.get("name") or resolved_module
                logger.info(
                    f"[MODULE_DISAMBIGUATOR] Successfully resolved user choice '{user_msg}' to module '{resolved_module}' ({module_name})",
                    extra={"session_id": session_id}
                )

                updates: Dict[str, Any] = {
                    "selected_module": resolved_module,
                    "candidate_modules": [],
                    "awaiting": "none",
                    "current_step": "module_disambiguator",
                }

                # Restore original complaint if stored so downstream nodes process the original issue with the resolved module
                orig_query = state.get("pending_module_query")
                if orig_query:
                    updates["last_user_message"] = orig_query
                    updates["pending_module_query"] = None

                return updates

            # Could not resolve user choice: track retries
            retry_counters = dict(state.get("retry_counters") or {})
            count = retry_counters.get("module_choice", 0) + 1
            retry_counters["module_choice"] = count

            if count >= 2:
                logger.warning(
                    f"[MODULE_DISAMBIGUATOR] Module choice retry exhausted ({count}/2); defaulting to general and proceeding.",
                    extra={"session_id": session_id}
                )
                updates = {
                    "selected_module": None,
                    "candidate_modules": [],
                    "awaiting": "none",
                    "retry_counters": retry_counters,
                    "current_step": "module_disambiguator",
                }
                orig_query = state.get("pending_module_query")
                if orig_query:
                    updates["last_user_message"] = orig_query
                    updates["pending_module_query"] = None
                return updates

            # Re-prompt
            prompt_msg = (
                "I couldn't identify that selection. "
                + taxonomy.build_disambiguation_message(candidates)
            )
            return {
                "response": prompt_msg,
                "awaiting": "module_choice",
                "retry_counters": retry_counters,
                "current_step": "module_disambiguator",
            }

        # ----------------------------------------------------------------------
        # Case B: New query classification across modules
        # ----------------------------------------------------------------------
        classification = taxonomy.classify_module(user_msg, llm=runtime.llm)

        if classification.is_ambiguous and len(classification.candidate_modules) > 1:
            disambig_msg = taxonomy.build_disambiguation_message(classification.candidate_modules)
            logger.info(
                f"[MODULE_DISAMBIGUATOR] Query '{user_msg}' is ambiguous across {classification.candidate_modules}. Asking for clarification.",
                extra={"session_id": session_id}
            )
            return {
                "awaiting": "module_choice",
                "candidate_modules": classification.candidate_modules,
                "pending_module_query": user_msg,
                "response": disambig_msg,
                "current_step": "module_disambiguator",
            }

        if classification.detected_module:
            logger.info(
                f"[MODULE_DISAMBIGUATOR] Detected specific module '{classification.detected_module}' for query '{user_msg}'",
                extra={"session_id": session_id}
            )
            return {
                "selected_module": classification.detected_module,
                "current_step": "module_disambiguator",
            }

        return {
            "current_step": "module_disambiguator",
        }
    return node
