"""Classify a fault using state-expectation bucketing first, then deterministic rules, then LLM for ambiguity."""
from __future__ import annotations

import logging
from langchain_core.messages import SystemMessage
from trackobit_assistant.schemas.models import FaultCategory, FaultResult
from trackobit_assistant.services.fault_rules import classify_fault

logger = logging.getLogger(__name__)


def make_node(runtime):
    def node(state):
        snapshot = state.get('vehicle_snapshot')
        symptoms = state.get('symptoms') or {}

        # Prefer the original symptom evidence over later messages
        dashboard_evidence = (
            state.get('dashboard_evidence')
            or symptoms.get('user_observation')
            or symptoms.get('summary')
            or state.get('last_user_message')
        )

        # Pull the state-expectation bucket set by symptom_analyzer
        state_expectation_bucket = symptoms.get('state_expectation_bucket')

        result = classify_fault(
            snapshot,
            dashboard_evidence,
            runtime.settings.freshness_threshold_minutes,
            state_expectation_bucket=state_expectation_bucket,
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
                if candidate.confidence >= runtime.settings.query_confidence_threshold:
                    result = candidate
            except Exception as exc:
                logger.warning("Fault-classifier LLM failed; retaining deterministic result (%s)", type(exc).__name__)

        # For STATE_DISCREPANCY: carry forward the bucket and actual state for fault_diagnosis
        updates: dict = {
            'fault_category': result.category.value,
            'fault_confidence': result.confidence,
            'fault_evidence': result.evidence,
            'fault_needs_user_input': result.needs_user_input,
            'max_troubleshoot_rounds': runtime.settings.max_troubleshoot_rounds,
            'dashboard_evidence': dashboard_evidence,
            'response': '',
            'current_step': 'fault_classifier',
        }

        if result.category == FaultCategory.STATE_DISCREPANCY:
            # Re-compute the normalized actual state for fault_diagnosis to use
            from trackobit_assistant.services.fault_rules import _normalize_actual_state
            actual = _normalize_actual_state(snapshot or {})
            updates['actual_vehicle_state'] = actual
            updates['state_expectation_bucket'] = state_expectation_bucket
            logger.info(
                f"[FAULT_CLASSIFIER] STATE_DISCREPANCY: expected bucket='{state_expectation_bucket}', "
                f"actual='{actual}'",
                extra={'session_id': state.get('session_id', '-')}
            )

        return updates
    return node
