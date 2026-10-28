import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from langchain_core.messages import SystemMessage

from trackobit_assistant.schemas.models import ModuleClassification

logger = logging.getLogger(__name__)


class ModuleTaxonomyService:
    """Service for identifying, disambiguating, and routing user queries across TrackoBit modules."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path("config/application_modules.yaml")
        self.modules: Dict[str, Dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        if not self.config_path.exists():
            logger.warning(f"Module taxonomy config not found at {self.config_path}")
            self.modules = {}
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self.modules = data.get("modules", {})
            logger.info(f"Loaded {len(self.modules)} application modules from {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to load application modules from {self.config_path}: {e}")
            self.modules = {}

    def get_modules(self) -> Dict[str, Dict[str, Any]]:
        return self.modules

    def get_module(self, module_id: str) -> Optional[Dict[str, Any]]:
        return self.modules.get(str(module_id).strip().lower())

    def classify_module(self, text: str, llm: Any = None) -> ModuleClassification:
        """Classify a user query against TrackoBit modules using LLM structured output, falling back to heuristics."""
        clean_text = (text or "").strip()
        if not clean_text:
            return ModuleClassification(detected_module=None, is_ambiguous=False, candidate_modules=[])

        # 1. Try LLM structured classification if available
        if llm is not None and self.modules:
            try:
                module_descriptions = []
                for mod_id, m in self.modules.items():
                    name = m.get("name", mod_id)
                    desc = m.get("description", "")
                    concepts = ", ".join(m.get("common_concepts", []))
                    explicit = ", ".join(m.get("explicit_keywords", []))
                    module_descriptions.append(
                        f"- **{mod_id}** ({name}): {desc}. Specific sections: [{explicit}]. Shared terms: [{concepts}]"
                    )
                catalog_text = "\n".join(module_descriptions)

                system_prompt = (
                    "You are the TrackoBit Platform Module Classifier.\n"
                    "Your role is to identify which application module the user is talking about, or flag if the query is ambiguous.\n\n"
                    "Here are the platform's official modules:\n"
                    f"{catalog_text}\n\n"
                    "Classification Rules:\n"
                    "1. If the user's message clearly indicates a specific module (e.g. 'distance report', 'travel log export', 'on live map', 'trip playback player', 'service schedule'), "
                    "set detected_module to that module ID, and set is_ambiguous=False.\n"
                    "2. If the user asks about an overlapping metric (such as 'distance', 'speed', 'mileage', 'odometer', or 'buffering') WITHOUT specifying where they are seeing it, "
                    "it is ambiguous! Set detected_module=None, is_ambiguous=True, and list candidate_modules in candidate_modules.\n"
                    "3. If the user message is a general inquiry, greeting, or hardware/device issue that doesn't belong to a software module, set detected_module=None, is_ambiguous=False."
                )

                prompt_content = f"{system_prompt}\n\nUser message: {clean_text}"
                result = llm.with_structured_output(ModuleClassification).invoke([SystemMessage(content=prompt_content)])
                logger.info(
                    f"[MODULE_TAXONOMY] LLM classified module: detected='{result.detected_module}', "
                    f"is_ambiguous={result.is_ambiguous}, candidates={result.candidate_modules}"
                )
                return result
            except Exception as e:
                logger.warning(f"[MODULE_TAXONOMY] LLM classification failed ({e}); falling back to heuristic")

        # 2. Heuristic fallback
        return self._heuristic_classify(clean_text)

    def _heuristic_classify(self, text: str) -> ModuleClassification:
        low = text.casefold()

        # 1. Check explicit module mentions and keywords
        for mod_id, meta in self.modules.items():
            name_low = meta.get("name", "").casefold()
            id_low = mod_id.casefold()
            explicit_keys = [k.casefold() for k in meta.get("explicit_keywords", [])]
            base_id = id_low.rstrip('s')

            if (
                id_low in low
                or (len(base_id) >= 4 and re.search(rf"\b{base_id}s?\b", low))
                or name_low in low
                or any(k in low for k in explicit_keys)
            ):
                return ModuleClassification(detected_module=mod_id, is_ambiguous=False, candidate_modules=[mod_id])

        # 2. Check overlapping concepts
        candidates = []
        for mod_id, meta in self.modules.items():
            concepts = [c.casefold() for c in meta.get("common_concepts", [])]
            if any(c in low for c in concepts):
                candidates.append(mod_id)

        if len(candidates) > 1:
            return ModuleClassification(
                detected_module=None,
                is_ambiguous=True,
                candidate_modules=candidates,
                reasoning=f"Query matched shared concepts across {len(candidates)} modules."
            )
        elif len(candidates) == 1:
            return ModuleClassification(
                detected_module=candidates[0],
                is_ambiguous=False,
                candidate_modules=candidates
            )

        return ModuleClassification(detected_module=None, is_ambiguous=False, candidate_modules=[])

    def build_disambiguation_message(self, candidate_ids: List[str]) -> str:
        """Construct a polite, numbered clarification prompt for the user."""
        options = []
        for i, mod_id in enumerate(candidate_ids):
            meta = self.modules.get(mod_id, {})
            label = meta.get("clarification_label") or meta.get("name") or mod_id.replace("_", " ").title()
            options.append(f"{i + 1}. **{label}**")

        options_text = "\n".join(options)
        return (
            f"To help you with this issue, could you specify which section of TrackoBit you are seeing this in?\n\n"
            f"{options_text}\n\n"
            f"Please reply with the number or section name."
        )

    def resolve_user_choice(self, user_reply: str, candidate_ids: List[str]) -> Optional[str]:
        """Resolve a user's reply ('1', 'reports', 'live dashboard') to a specific module ID."""
        clean = (user_reply or "").strip().casefold()
        if not clean or not candidate_ids:
            return None

        # Check number choice ("1", "2", etc.)
        for i, mod_id in enumerate(candidate_ids):
            num_str = str(i + 1)
            if re.search(rf"\b{num_str}\b", clean):
                return mod_id

        # Check module id or keywords
        for mod_id in candidate_ids:
            meta = self.modules.get(mod_id, {})
            explicit_keys = [k.casefold() for k in meta.get("explicit_keywords", [])]
            if any(k in clean for k in explicit_keys):
                return mod_id

            name_parts = meta.get("name", "").casefold().split()
            id_parts = mod_id.casefold().split("_")
            if any(part in clean for part in (name_parts + id_parts) if len(part) > 3):
                return mod_id

        return None
