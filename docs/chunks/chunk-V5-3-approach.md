# Chunk V5-3 Approach: Embeddings Fallback Tests

## Scope
Create `tests/unit/intelligence/__init__.py` (empty) and
`tests/unit/intelligence/test_embeddings_fallback.py` with 7 focused unit tests.

## No data scale concerns
This chunk creates test files only. No DB queries, no table reads.

## Wiki patterns checked
- `AsyncMock Context Manager Pattern` — exact pattern for mocking httpx.AsyncClient
- `Local LLM Fallback` — confirms nomic/Ollama fallback design is established pattern
- `Embedding Fault Tolerance in Store Path` — confirms EmbeddingError as the fault signal

## Existing code reused
- `tests/services/test_embedding.py` — established mock helpers `_openai_response`,
  `_nomic_response`, `_make_vector`, `_make_settings`, and `fake_post` pattern for
  URL-routing. New file follows identical structure.
- `backend/services/embedding.py` — the service under test. Key constants:
  `DIMENSIONS=1536`, `_NOMIC_NATIVE_DIMS=768`. Fallback chain: OpenAI 5xx → raises
  `EmbeddingError` → `embed()` catches and calls `_nomic_embed()`.

## Approach
Pure unit tests using `unittest.mock.patch` at:
  - `backend.services.embedding.get_settings`
  - `backend.services.embedding.httpx.AsyncClient`

The `fake_post` URL-routing approach (dispatch on "openai" in url) is reused from
existing tests — it is clean and avoids side-effect ordering issues.

For "both-down" tests: raise `httpx.ConnectError` from fake_post for every URL,
which propagates through `_openai_embed` as `EmbeddingError` (caught by `embed`),
then propagates through `_nomic_embed` as `EmbeddingError` (not caught), bubbling out.

## Seven test cases
1. `test_embed_primary_success_returns_1536_vector` — OpenAI 200, 1536-dim passthrough
2. `test_embed_primary_5xx_fallback_to_nomic_returns_1536` — OpenAI 500 → nomic 768 padded to 1536
3. `test_embed_both_providers_down_raises_embedding_error` — ConnectError on all URLs
4. `test_embed_dimensionality_invariant_openai_path` — len(result) == DIMENSIONS
5. `test_embed_dimensionality_invariant_nomic_path` — nomic 768 padded to exactly DIMENSIONS
6. `test_embed_batch_primary_5xx_fallback_nomic` — batch OpenAI 500 → nomic sequential
7. `test_embed_batch_both_down_raises_embedding_error` — batch ConnectError all URLs

## Edge cases
- `_NOMIC_NATIVE_DIMS` is a module-level int, not a function — existing test file
  wraps it in a function accidentally; new file imports it directly as the constant.
- Padding assertions: `result[:_NOMIC_NATIVE_DIMS]` contains original values,
  `result[_NOMIC_NATIVE_DIMS:]` are all 0.0.

## Expected runtime
All mocked, no I/O — < 1 second on any hardware.
