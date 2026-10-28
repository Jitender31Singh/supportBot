import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document
from langchain_pinecone import PineconeVectorStore
from langchain_openai import OpenAIEmbeddings

from trackobit_assistant.config.settings import get_settings

logger = logging.getLogger(__name__)


class PineconeBugStore:
    """Manages software bugs, incidents, and outages in Pinecone via LangChain.
    
    Supports dynamic vector search on customer symptoms and live CRUD operations
    (add, update, delete, search, list) for customer support executives.
    """

    def __init__(
        self,
        index_name: Optional[str] = None,
        api_key: Optional[str] = None,
        embeddings: Any = None,
        cache_file: Optional[Path] = None,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.pinecone_api_key
        raw_index_name = index_name or settings.pinecone_index_name or "manual-bugs"
        # Pinecone index names do not allow underscores
        self.index_name = raw_index_name.replace("_", "-")

        self.cache_file = cache_file or (settings.data_dir / "known_bugs.json")
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

        if embeddings is not None:
            self.embeddings = embeddings
        elif settings.openai_api_key:
            self.embeddings = OpenAIEmbeddings(
                model="text-embedding-3-small",
                api_key=settings.openai_api_key,
            )
        else:
            self.embeddings = None

        self._vector_store: Optional[PineconeVectorStore] = None

    @property
    def vector_store(self) -> PineconeVectorStore:
        if self._vector_store is None:
            if not self.embeddings:
                raise ValueError("Embeddings must be configured to use PineconeBugStore.")
            self._vector_store = PineconeVectorStore(
                index_name=self.index_name,
                embedding=self.embeddings,
                pinecone_api_key=self.api_key,
            )
        return self._vector_store

    def _read_cache(self) -> Dict[str, Dict[str, Any]]:
        if not self.cache_file.exists():
            return {}
        try:
            return json.loads(self.cache_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"Failed to read bugs cache ({e}); starting empty.")
            return {}

    def _write_cache(self, data: Dict[str, Dict[str, Any]]) -> None:
        try:
            self.cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to write bugs cache: {e}")

    def list_bugs(self, status: Optional[str] = None, module: Optional[str] = None) -> List[Dict[str, Any]]:
        """List known bugs. Optionally filters by status and module."""
        bugs_dict = self._read_cache()
        bugs = list(bugs_dict.values())
        if status:
            bugs = [b for b in bugs if b.get("status") == status]
        if module:
            clean_mod = module.strip().lower()
            bugs = [b for b in bugs if b.get("module", "general").strip().lower() in (clean_mod, "general", "any")]
        return bugs

    def get_bug(self, bug_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific bug by ID from cache."""
        clean_id = str(bug_id).strip()
        return self._read_cache().get(clean_id)

    def add_bug(
        self,
        bug_id: str,
        title: str,
        symptoms: str,
        workaround: str = "",
        eta: str = "",
        severity: str = "Medium",
        status: str = "active",
        module: str = "general",
    ) -> str:
        """Add a new known bug or incident to Pinecone and local cache."""
        clean_id = str(bug_id).strip()
        clean_mod = (module or "general").strip().lower()
        meta = {
            "bug_id": clean_id,
            "title": title.strip(),
            "symptoms": symptoms.strip(),
            "workaround": workaround.strip(),
            "eta": eta.strip(),
            "severity": severity.strip(),
            "status": status.strip(),
            "module": clean_mod,
        }
        doc = Document(
            page_content=f"{title.strip()}: {symptoms.strip()}",
            metadata=meta,
        )
        self.vector_store.add_documents(documents=[doc], ids=[clean_id])
        
        # Update local manifest
        cache = self._read_cache()
        cache[clean_id] = meta
        self._write_cache(cache)

        logger.info(f"Added bug {clean_id} (module={clean_mod}) to Pinecone index {self.index_name}")
        return clean_id

    def update_bug(
        self,
        bug_id: str,
        title: Optional[str] = None,
        symptoms: Optional[str] = None,
        workaround: Optional[str] = None,
        eta: Optional[str] = None,
        severity: Optional[str] = None,
        status: str = "active",
        module: Optional[str] = None,
    ) -> bool:
        """Update an existing bug in Pinecone and cache."""
        clean_id = str(bug_id).strip()
        existing = self.get_bug(clean_id) or {}

        clean_mod = (module if module is not None else existing.get("module", "general")) or "general"
        meta = {
            "bug_id": clean_id,
            "title": (title if title is not None else existing.get("title", "")).strip(),
            "symptoms": (symptoms if symptoms is not None else existing.get("symptoms", "")).strip(),
            "workaround": (workaround if workaround is not None else existing.get("workaround", "")).strip(),
            "eta": (eta if eta is not None else existing.get("eta", "")).strip(),
            "severity": (severity if severity is not None else existing.get("severity", "Medium")).strip(),
            "status": status.strip(),
            "module": str(clean_mod).strip().lower(),
        }

        content = f"{meta['title']}: {meta['symptoms']}".strip()
        if not content:
            content = f"Bug {clean_id}"

        doc = Document(
            page_content=content,
            metadata=meta,
        )
        self.vector_store.add_documents(documents=[doc], ids=[clean_id])

        # Update local manifest
        cache = self._read_cache()
        cache[clean_id] = meta
        self._write_cache(cache)

        logger.info(f"Updated bug {clean_id} (module={meta['module']}) in Pinecone index {self.index_name}")
        return True

    def delete_bug(self, bug_id: str) -> bool:
        """Permanently delete a bug from Pinecone by ID and remove from cache."""
        clean_id = str(bug_id).strip()
        self.vector_store.delete(ids=[clean_id])

        # Remove from local manifest
        cache = self._read_cache()
        if clean_id in cache:
            del cache[clean_id]
            self._write_cache(cache)

        logger.info(f"Deleted bug {clean_id} from Pinecone index {self.index_name}")
        return True

    def search_active_bug(
        self,
        user_complaint: str,
        min_similarity: float = 0.65,
        candidate_similarity: float = 0.40,
        top_k: int = 1,
        llm: Optional[Any] = None,
        module: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Search for an active known bug that matches the customer's complaint.
        
        Uses a two-stage approach:
        1. High-confidence vector similarity (score >= min_similarity) returns immediately.
        2. Moderate vector similarity (candidate_similarity <= score < min_similarity) uses an LLM
           semantic verifier to confirm whether the customer complaint matches the known bug.

        If `module` is specified (e.g. 'reports'), filters out bugs registered under other modules.
        """
        if not user_complaint or not user_complaint.strip():
            return None

        clean_target_module = (module or "").strip().lower()

        try:
            # Retrieve enough candidates to find module-specific matches
            fetch_k = max(top_k * 3, 5)
            results = self.vector_store.similarity_search_with_score(
                query=user_complaint,
                k=fetch_k,
                filter={"status": "active"},
            )
        except Exception as e:
            logger.error(f"Error searching Pinecone for active bugs: {e}")
            return None

        if not results:
            return None

        # Filter by module if specified
        filtered_results = []
        for matched_doc, score in results:
            meta = matched_doc.metadata or {}
            doc_module = str(meta.get("module") or "general").strip().lower()
            if clean_target_module and doc_module not in ("general", "any", "", clean_target_module):
                logger.info(
                    f"[PINECONE_BUG_STORE] Skipping candidate bug '{meta.get('bug_id')}' "
                    f"due to module mismatch: target='{clean_target_module}', bug='{doc_module}'"
                )
                continue
            filtered_results.append((matched_doc, score))

        if not filtered_results:
            return None

        matched_doc, score = filtered_results[0]
        meta = matched_doc.metadata or {}
        bug_data = {
            "bug_id": meta.get("bug_id", matched_doc.id if hasattr(matched_doc, "id") else ""),
            "title": meta.get("title", ""),
            "symptoms": meta.get("symptoms", matched_doc.page_content),
            "workaround": meta.get("workaround", ""),
            "eta": meta.get("eta", ""),
            "severity": meta.get("severity", "Medium"),
            "status": meta.get("status", "active"),
            "module": meta.get("module", "general"),
            "similarity_score": round(float(score), 4),
        }

        # Stage 1: Direct high-confidence match
        if score >= min_similarity:
            return bug_data

        # Stage 2: Semantic verification with LLM for paraphrased/unit-mismatched complaints
        if score >= candidate_similarity and llm is not None:
            try:
                from langchain_core.messages import SystemMessage
                prompt = (
                    f"Known Bug / Incident: {bug_data['title']} (Module: {bug_data['module']}, symptoms/details: {bug_data['symptoms']})\n"
                    f"Customer Complaint: {user_complaint}\n\n"
                    "Does this customer complaint describe, relate to, or result from this known bug? "
                    "Reply strictly starting with YES or NO, followed by a one-sentence reason."
                )
                resp = llm.invoke([SystemMessage(content=prompt)])
                content = (resp.content if hasattr(resp, "content") else str(resp)).strip()
                if content.upper().startswith("YES"):
                    logger.info(f"LLM verified match for bug {bug_data['bug_id']}: {content}")
                    bug_data["llm_verified"] = True
                    return bug_data
            except Exception as exc:
                logger.warning(f"LLM verification failed: {exc}")

        return None
