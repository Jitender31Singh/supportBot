"""Documented placeholder for a shared PostgreSQL-backed session store.

Implement this adapter against the SessionStore protocol when deploying multiple workers.
The initial local application deliberately uses JsonSessionStore so no database is required.
"""
from typing import Any


class PostgresSessionStoreStub:
    def __init__(self, dsn: str) -> None:
        if not dsn:
            raise ValueError("A PostgreSQL DSN is required")
        self.dsn = dsn

    def _not_implemented(self) -> None:
        raise NotImplementedError(
            "PostgresSessionStoreStub is documentation scaffolding. Implement the SessionStore "
            "methods and configure a durable LangGraph checkpointer before production use."
        )

    def create_session(self) -> dict[str, Any]: self._not_implemented()
    def list_sessions(self, user_id: str | None = None) -> list[dict[str, Any]]: self._not_implemented()
    def get_session(self, session_id: str) -> dict[str, Any] | None: self._not_implemented()
    def save_graph_result(self, session_id: str, state: dict[str, Any]) -> None: self._not_implemented()
    def state_for(self, session_id: str) -> dict[str, Any] | None: self._not_implemented()
    def append_message(self, session_id: str, message: dict[str, Any]) -> None: self._not_implemented()
    def get_summary(self, session_id: str) -> str: self._not_implemented()
