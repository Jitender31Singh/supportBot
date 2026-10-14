-- Suggested PostgreSQL schema for implementing PostgresSessionStore.
-- Store JSON state and the full transcript separately so common session listings stay fast.
CREATE TABLE support_sessions (
    session_id UUID PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'New support chat',
    status TEXT NOT NULL DEFAULT 'open',
    vehicle_no TEXT,
    state JSONB NOT NULL DEFAULT '{}'::jsonb,
    summary TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX support_sessions_updated_at_idx ON support_sessions (updated_at DESC);
CREATE INDEX support_sessions_status_idx ON support_sessions (status);
CREATE TABLE support_messages (
    message_id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES support_sessions(session_id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system', 'tool')),
    content TEXT NOT NULL,
    attachment_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX support_messages_session_created_idx ON support_messages (session_id, created_at);
