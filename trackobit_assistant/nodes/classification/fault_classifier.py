"""Classify a fault deterministically first, using a structured LLM only for ambiguity."""
from __future__ import annotations

import logging
from langchain_core.messages import SystemMessage
from trackobit_assistant.schemas.models import FaultCategory, FaultResult
from trackobit_assistant.services.fault_rules import classify_fault

logger = logging.getLogger(__name__)


def make_node(runtime):
    def node(state):
        snapshot = state.get('vehicle_snapshot')
        # The first user turn can describe the dashboard issue, while the next turn only
        # supplies a vehicle number. Preserve the original symptom evidence for classification.
        symptoms = state.get('symptoms') or {}
        dashboard_evidence = (
            state.get('dashboard_evidence')
            or symptoms.get('user_observation')
            or symptoms.get('summary')
            or state.get('last_user_message')
        )
        result = classify_fault(
            snapshot, dashboard_evidence, runtime.settings.freshness_threshold_minutes
        )

        if runtime.llm is not None and result.category in {
            FaultCategory.UNKNOWN, FaultCategory.NEED_MORE_INFO
        }:
            try:
                prompt = (
                    runtime.prompts.render(
                        'fault_classifier', snapshot=snapshot,
                        dashboard_evidence=dashboard_evidence,
                        deterministic_evidence=result.model_dump(mode='json'),
                    )
                    if runtime.prompts else
                    f"Resolve only ambiguous fault evidence. Snapshot={snapshot}; "
                    f"Dashboard evidence={dashboard_evidence}; deterministic result={result.model_dump(mode='json')}"
                )
                candidate = runtime.llm.with_structured_output(FaultResult).invoke(
                    [SystemMessage(content=prompt)]
                )
                # The LLM is not allowed to overturn a deterministic high-confidence rule.
                if candidate.confidence >= runtime.settings.query_confidence_threshold:
                    result = candidate
            except Exception as exc:
                logger.warning("Fault-classifier LLM failed; retaining deterministic result (%s)", type(exc).__name__)

        return {
            'fault_category': result.category.value,
            'fault_confidence': result.confidence,
            'fault_evidence': result.evidence,
            'fault_needs_user_input': result.needs_user_input,
            'max_troubleshoot_rounds': runtime.settings.max_troubleshoot_rounds,
            'dashboard_evidence': dashboard_evidence,
            'response': '',
            'current_step': 'fault_classifier',
        }
    return node
