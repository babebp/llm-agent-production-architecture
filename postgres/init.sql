-- Second database on the shared instance: agent session checkpoints (ADR-0007).
-- Runs only on first volume init; for an already-initialized volume:
--   docker compose exec postgres createdb -U litellm agent_state
CREATE DATABASE agent_state;
