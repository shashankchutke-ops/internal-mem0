import json
import logging
import threading
from copy import deepcopy
from typing import Any, Callable, Dict

from mem0 import Memory

_state_lock = threading.RLock()
_current_config: Dict[str, Any] = {}
_memory_instance: Memory | None = None
_session_factory: Callable | None = None
_PROVIDER_CONFIG_SECTIONS = {"llm", "embedder"}
_PGVECTOR_DEFAULT_EMBEDDING_DIMS = 1536


def set_session_factory(factory: Callable) -> None:
    global _session_factory
    _session_factory = factory


def _load_overrides() -> Dict[str, Any]:
    try:
        if _session_factory is None:
            return {}
        from models import Settings

        session = _session_factory()
        try:
            row = session.get(Settings, "config_overrides")
            if row is None:
                return {}
            return json.loads(row.value)
        finally:
            session.close()
    except Exception:
        return {}


def _save_overrides(overrides: Dict[str, Any]) -> None:
    try:
        if _session_factory is None:
            return
        from models import Settings
        from sqlalchemy.dialects.postgresql import insert

        session = _session_factory()
        try:
            serialized = json.dumps(overrides)
            stmt = (
                insert(Settings)
                .values(key="config_overrides", value=serialized)
                .on_conflict_do_update(
                    index_elements=[Settings.key],
                    set_={"value": serialized},
                )
            )
            session.execute(stmt)
            session.commit()
        finally:
            session.close()
    except Exception:
        logging.warning("Failed to persist config overrides to database", exc_info=True)


def _merge_config(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)

    for key, value in updates.items():
        current_value = merged.get(key)
        if isinstance(value, dict) and isinstance(current_value, dict):
            if (
                key in _PROVIDER_CONFIG_SECTIONS
                and value.get("provider")
                and current_value.get("provider")
                and value["provider"] != current_value["provider"]
            ):
                # A credential for one provider must not silently be reused by another.
                # If the update includes a new key, the nested merge below replaces it.
                current_value = deepcopy(current_value)
                provider_config = current_value.get("config")
                if isinstance(provider_config, dict):
                    provider_config.pop("api_key", None)
            merged[key] = _merge_config(current_value, value)
        else:
            merged[key] = value

    return merged


def _normalize_embedding_dimensions(config: Dict[str, Any]) -> Dict[str, Any]:
    """Keep bundled embedders aligned with the pgvector column dimensions.

    The pgvector schema is created from ``embedding_model_dims``.  The Gemini
    provider defaults to 768 dimensions, while this server's existing schema
    defaults to 1536.  Supplying the storage dimension to the embedder avoids
    creating a runtime configuration that can read successfully but fails on
    every insert.
    """
    normalized = deepcopy(config)
    vector_store = normalized.get("vector_store")
    if not isinstance(vector_store, dict) or vector_store.get("provider") != "pgvector":
        return normalized

    vector_config = vector_store.get("config")
    if not isinstance(vector_config, dict):
        vector_config = {}
        vector_store["config"] = vector_config
    storage_dims = vector_config.setdefault("embedding_model_dims", _PGVECTOR_DEFAULT_EMBEDDING_DIMS)

    embedder = normalized.get("embedder")
    if not isinstance(embedder, dict):
        return normalized
    embedder_config = embedder.get("config")
    if not isinstance(embedder_config, dict):
        embedder_config = {}
        embedder["config"] = embedder_config
    embedder_config.setdefault("embedding_dims", storage_dims)
    return normalized


def initialize_state(default_config: Dict[str, Any]) -> None:
    global _current_config, _memory_instance
    with _state_lock:
        _current_config = deepcopy(default_config)
        overrides = _load_overrides()
        if overrides:
            _current_config = _merge_config(_current_config, overrides)
        _current_config = _normalize_embedding_dimensions(_current_config)
        _memory_instance = Memory.from_config(_current_config)


def update_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    global _current_config, _memory_instance
    with _state_lock:
        next_config = _normalize_embedding_dimensions(_merge_config(_current_config, updates))
        _current_config = next_config
        _memory_instance = Memory.from_config(next_config)
        overrides = _load_overrides()
        overrides = _merge_config(overrides, updates)
        _save_overrides(overrides)
        return deepcopy(_current_config)


def get_current_config() -> Dict[str, Any]:
    with _state_lock:
        return deepcopy(_current_config)


def get_memory_instance() -> Memory:
    with _state_lock:
        if _memory_instance is None:
            raise RuntimeError("Mem0 runtime has not been initialized.")
        return _memory_instance
