# Chunk V1-2 Approach: Embedding Adapter

## Data Scale
No new database tables. The `atlas_intelligence.embedding` Vector(1536) column already exists.
No row counts needed — this chunk is a pure service layer with no DB writes.

## Chosen Approach

### Architecture
- `backend/services/embedding.py` — async adapter with OpenAI primary + nomic fallback
- Raw `httpx.AsyncClient` calls to both providers (no openai Python package)
- nomic-embed-text natively produces 768-dim; zero-pad to 1536 for compatibility
- `structlog` throughout, no print()

### Why zero-pad for nomic?
Cosine similarity in pgvector normalises on the non-zero portion, so the first 768 dims still carry full semantic signal. The zeros don't introduce false similarity — they contribute nothing. This is the simplest reliable approach that satisfies the "always 1536" invariant.

### OpenAI API (raw httpx)
- POST `https://api.openai.com/v1/embeddings`
- Bearer token from `settings.openai_api_key`
- On HTTP 5xx or httpx transport error → log warning + fall back to nomic
- On 4xx → raise EmbeddingError (bad key/quota — nomic fallback won't help for auth errors, but we still try)

### Nomic / Ollama API
- POST `{nomic_api_url}/api/embeddings`
- model: `nomic-embed-text`
- If both fail → raise EmbeddingError

### Config additions to `backend/config.py`
```python
openai_api_key: str = ""
nomic_api_url: str = "http://localhost:11434"
embedding_model: str = "text-embedding-3-small"
embedding_dimensions: int = 1536
```

## Wiki Patterns Checked
- `staging/local-llm-fallback.md` — Ollama as primary/fallback; exact pattern this chunk follows
- `bug-patterns/external-api-format-drift.md` — external APIs change without notice; need fallbacks

## Existing Code Reused
- `backend/config.py` → `get_settings()` — add 4 new fields
- `structlog` already installed (25.5.0)
- `httpx` already installed (0.28.1)

## Edge Cases
| Case | Handling |
|------|----------|
| Empty string input | `ValueError` raised before any HTTP call |
| Batch contains empty string | `ValueError` raised before any HTTP call |
| OpenAI 5xx | Caught, warning logged, nomic fallback attempted |
| OpenAI 4xx (bad key) | Caught as EmbeddingError, nomic fallback still attempted |
| Missing openai_api_key | Skip OpenAI entirely, go straight to nomic |
| Nomic returns wrong dimensions | Validated + zero-padded to 1536 |
| Both providers fail | `EmbeddingError` raised with clear message |
| Empty batch | Returns `[]` immediately |

## Test Strategy
All tests use `unittest.mock.patch` on `httpx.AsyncClient.post` — no real network calls.
Settings overrides via monkeypatch on the `get_settings` cache.

## Expected Runtime
- Single embed: ~200ms OpenAI, ~100ms nomic (network latency dominated)
- Batch of 50: ~300ms OpenAI (one batch request), ~1.5s nomic (no native batch endpoint, sequential)
- Test suite: <2s (all mocked)

## Files
1. MODIFY: `backend/config.py`
2. CREATE: `backend/services/__init__.py`
3. CREATE: `backend/services/embedding.py`
4. CREATE: `tests/services/__init__.py`
5. CREATE: `tests/services/test_embedding.py`
