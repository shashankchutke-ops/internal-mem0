from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlparse

import httpx


class Mem0ApiError(RuntimeError):
    """An authenticated request to the Mem0 REST API failed."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Mem0 API request failed ({status_code}): {detail}")


@dataclass(frozen=True)
class Settings:
    """Runtime settings supplied to one local agent process."""

    base_url: str
    api_key: str
    user_id: str
    agent_id: str

    def __post_init__(self) -> None:
        base_url = self.base_url.strip().rstrip("/")
        api_key = self.api_key.strip()
        user_id = self.user_id.strip()
        agent_id = self.agent_id.strip()

        if not base_url:
            raise ValueError("MEM0_API_URL must not be empty")
        if not api_key:
            raise ValueError("MEM0_API_KEY must not be empty")
        if not user_id:
            raise ValueError("MEM0_USER_ID must not be empty")
        if not agent_id:
            raise ValueError("MEM0_AGENT_ID must not be empty")

        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("MEM0_API_URL must be a complete http(s) URL")
        if parsed.scheme == "http" and (parsed.hostname or "").lower() not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("MEM0_API_URL must use https for non-local endpoints")

        object.__setattr__(self, "base_url", base_url)
        object.__setattr__(self, "api_key", api_key)
        object.__setattr__(self, "user_id", user_id)
        object.__setattr__(self, "agent_id", agent_id)

    @classmethod
    def from_env(cls) -> Settings:
        """Load settings without ever logging their values."""

        required = {
            "MEM0_API_KEY": os.environ.get("MEM0_API_KEY", ""),
            "MEM0_USER_ID": os.environ.get("MEM0_USER_ID", ""),
            "MEM0_AGENT_ID": os.environ.get("MEM0_AGENT_ID", ""),
        }
        missing = [name for name, value in required.items() if not value.strip()]
        if missing:
            raise ValueError(f"Missing required environment variable(s): {', '.join(missing)}")

        return cls(
            base_url=os.environ.get("MEM0_API_URL", "https://mem0.shashawk.com"),
            api_key=required["MEM0_API_KEY"],
            user_id=required["MEM0_USER_ID"],
            agent_id=required["MEM0_AGENT_ID"],
        )


class Mem0RestClient:
    """Small async REST client with one bounded, reusable HTTP connection pool."""

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        async with self._client_lock:
            if self._client is None:
                self._client = httpx.AsyncClient(
                    base_url=self.settings.base_url,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "X-API-Key": self.settings.api_key,
                    },
                    timeout=httpx.Timeout(120.0, connect=5.0, write=10.0, pool=5.0),
                    limits=httpx.Limits(
                        max_connections=20,
                        max_keepalive_connections=10,
                        keepalive_expiry=30.0,
                    ),
                    transport=self._transport,
                )
            return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await (await self._get_client()).request(method, path, **kwargs)
        if response.is_error:
            try:
                body = response.json()
            except ValueError:
                body = response.text.strip()
            if isinstance(body, dict):
                detail = str(body.get("detail") or body.get("message") or "request failed")
            else:
                detail = str(body or "request failed")
            raise Mem0ApiError(response.status_code, detail[:500])

        if response.status_code == 204:
            return {"status": "ok"}
        try:
            return response.json()
        except ValueError as exc:
            raise Mem0ApiError(response.status_code, "Mem0 returned invalid JSON") from exc

    @staticmethod
    def _required(value: str | None, name: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError(f"{name} must not be empty")
        return normalized

    @staticmethod
    def _path_segment(value: str, name: str) -> str:
        return quote(Mem0RestClient._required(value, name), safe="")

    def _user_id(self, user_id: str | None) -> str:
        return self._required(user_id or self.settings.user_id, "user_id")

    async def add_memory(
        self,
        content: str,
        *,
        role: str = "user",
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        infer: bool = True,
        run_id: str | None = None,
        expiration_date: str | None = None,
        memory_type: str | None = None,
        prompt: str | None = None,
    ) -> Any:
        payload: dict[str, Any] = {
            "messages": [
                {
                    "role": self._required(role, "role"),
                    "content": self._required(content, "content"),
                }
            ],
            "user_id": self._user_id(user_id),
            "agent_id": self.settings.agent_id,
            "infer": infer,
        }
        optional = {
            "metadata": metadata,
            "run_id": run_id,
            "expiration_date": expiration_date,
            "memory_type": memory_type,
            "prompt": prompt,
        }
        payload.update({key: value for key, value in optional.items() if value is not None})
        return await self._request("POST", "/memories", json=payload)

    async def search(
        self,
        query: str,
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        top_k: int | None = 10,
        threshold: float | None = None,
        explain: bool | None = None,
        show_expired: bool | None = None,
    ) -> Any:
        filters: dict[str, str] = {"user_id": self._user_id(user_id)}
        if agent_id is not None:
            filters["agent_id"] = self._required(agent_id, "agent_id")
        payload: dict[str, Any] = {
            "query": self._required(query, "query"),
            "filters": filters,
        }
        optional = {
            "top_k": top_k,
            "threshold": threshold,
            "explain": explain,
            "show_expired": show_expired,
        }
        payload.update({key: value for key, value in optional.items() if value is not None})
        return await self._request("POST", "/search", json=payload)

    async def list_memories(
        self,
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        top_k: int | None = 100,
        show_expired: bool = False,
    ) -> Any:
        params: dict[str, Any] = {"user_id": self._user_id(user_id), "show_expired": show_expired}
        if agent_id is not None:
            params["agent_id"] = self._required(agent_id, "agent_id")
        if top_k is not None:
            params["top_k"] = top_k
        return await self._request("GET", "/memories", params=params)

    async def get_memory(self, memory_id: str) -> Any:
        path = f"/memories/{self._path_segment(memory_id, 'memory_id')}"
        return await self._request("GET", path)

    async def memory_history(self, memory_id: str) -> Any:
        path = f"/memories/{self._path_segment(memory_id, 'memory_id')}/history"
        return await self._request("GET", path)

    async def update_memory(
        self,
        memory_id: str,
        *,
        text: str | None = None,
        metadata: dict[str, Any] | None = None,
        expiration_date: str | None = None,
    ) -> Any:
        payload: dict[str, Any] = {}
        if text is not None:
            payload["text"] = text
        if metadata is not None:
            payload["metadata"] = metadata
        if expiration_date is not None:
            payload["expiration_date"] = expiration_date
        if not payload:
            raise ValueError("At least one update field is required")
        path = f"/memories/{self._path_segment(memory_id, 'memory_id')}"
        return await self._request("PUT", path, json=payload)

    async def delete_memory(self, memory_id: str) -> Any:
        path = f"/memories/{self._path_segment(memory_id, 'memory_id')}"
        return await self._request("DELETE", path)
