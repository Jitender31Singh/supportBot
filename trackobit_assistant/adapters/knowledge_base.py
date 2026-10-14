from pathlib import Path
import re
from typing import Any

class FileKnowledgeBase:
    """Local starter retriever: ranks curated Markdown/text snippets by lexical overlap.

    It deliberately makes no LLM-generated claims without matching local content. The KnowledgeBase
    port can be swapped for a LangChain Chroma/FAISS retriever without changing graph nodes.
    """
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._docs: list[dict[str, Any]] = []
        self.reload()
    def reload(self) -> None:
        docs = []
        for path in list(self.directory.glob('*.md')) + list(self.directory.glob('*.txt')):
            text = path.read_text(encoding='utf-8', errors='replace').strip()
            if text:
                for i, chunk in enumerate(re.split(r'\n(?=#{1,3} )', text)):
                    if chunk.strip(): docs.append({'id': f'{path.name}:{i+1}', 'source': path.name, 'content': chunk.strip()})
        self._docs = docs
    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {t for t in re.findall(r'[a-z0-9]+', text.casefold()) if len(t) > 2}
    def search(self, query: str, k: int = 4) -> list[dict[str, Any]]:
        query_tokens = self._tokens(query)
        ranked = []
        for doc in self._docs:
            tokens = self._tokens(doc['content'])
            overlap = len(query_tokens & tokens)
            score = overlap / max(1, len(query_tokens))
            if score > 0: ranked.append((score, doc))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return [{'id': d['id'], 'source': d['source'], 'content': d['content'], 'score': round(s, 3)} for s, d in ranked[:k]]


class LangChainRetrieverKnowledgeBase:
    """Adapter for a LangChain BaseRetriever backed by Chroma, FAISS or another store.

    Construct it with an already configured retriever; the graph only depends on the KnowledgeBase port.
    """
    def __init__(self, retriever): self.retriever=retriever
    def search(self, query: str, k: int = 4) -> list[dict[str, Any]]:
        docs=self.retriever.invoke(query)
        rows=[]
        for i, doc in enumerate(docs[:k]):
            metadata=getattr(doc,'metadata',{}) or {}
            rows.append({'id':str(metadata.get('id') or metadata.get('source') or i),
                         'source':str(metadata.get('source') or metadata.get('file_path') or 'knowledge base'),
                         'content':str(getattr(doc,'page_content','')),'score':1.0})
        return rows
