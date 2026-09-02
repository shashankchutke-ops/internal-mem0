from server_state import _merge_config, _normalize_embedding_dimensions


def test_provider_change_drops_stale_provider_api_key():
    base = {
        "llm": {
            "provider": "openai",
            "config": {"model": "gpt-5-mini", "api_key": "old-provider-key"},
        }
    }
    updates = {
        "llm": {
            "provider": "gemini",
            "config": {"model": "gemini-3.7-flash"},
        }
    }

    merged = _merge_config(base, updates)

    assert merged["llm"]["provider"] == "gemini"
    assert merged["llm"]["config"]["model"] == "gemini-3.7-flash"
    assert "api_key" not in merged["llm"]["config"]


def test_gemini_embedder_defaults_to_pgvector_dimensions():
    config = {
        "vector_store": {"provider": "pgvector", "config": {}},
        "embedder": {"provider": "gemini", "config": {"model": "gemini-embedding-2"}},
    }

    normalized = _normalize_embedding_dimensions(config)

    assert normalized["vector_store"]["config"]["embedding_model_dims"] == 1536
    assert normalized["embedder"]["config"]["embedding_dims"] == 1536
