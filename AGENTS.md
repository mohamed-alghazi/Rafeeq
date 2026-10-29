# Rafeeq development
Use the existing checkout; do not create a Git worktree unless explicitly requested.
Run `uv sync --frozen` and `uv run pytest`. Start `uv run uvicorn rafeeq.api:app --host 127.0.0.1 --port 8000`.
Use synthetic data only. Never commit .env, keys, runtime databases or transcripts.
Keep model evaluation results distinct from scripted harness tests. Never invent scores.
The model must not authorize writes. Approval belongs to the authenticated API caller and is tied to immutable action arguments.
