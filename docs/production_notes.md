# Production notes

- In production, replace `MemorySaver` with a persistent LangGraph checkpointer suitable for your deployment. The JSON session adapter and graph checkpointer are intentionally separate concepts: the session adapter persists application state and transcript; the checkpointer stores graph state snapshots.
- Add `user_id`/tenant ownership into session metadata before enabling session listing to end users. The current local UI is an unauthenticated single-developer prototype.
- Treat vehicle payloads, screenshot output, retrieved KB text and user messages as untrusted. Never let them directly select arbitrary tool calls or shell commands.
- Do not place API keys or raw customer identifiers in source control. `.env` is gitignored.
