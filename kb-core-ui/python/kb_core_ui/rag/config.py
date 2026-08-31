"""Server-only GraphRAG configuration and readiness checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlparse

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off", ""})
_FALKOR_SCHEMES = frozenset({"falkor", "falkors", "redis", "rediss"})


def _bool(value: str, name: str, errors: list[str]) -> bool:
    normalized = value.strip().lower()
    if normalized in _TRUE:
        return True
    if normalized in _FALSE:
        return False
    errors.append(f"{name} must be one of true/false, 1/0, yes/no, or on/off")
    return False


def _positive_int(value: str, name: str, default: int, errors: list[str]) -> int:
    try:
        parsed = int(value)
    except ValueError:
        errors.append(f"{name} must be an integer")
        return default
    if parsed <= 0:
        errors.append(f"{name} must be greater than zero")
        return default
    return parsed


@dataclass(frozen=True)
class RagConfig:
    enabled: bool = False
    falkordb_url: str = ""
    username: str = ""
    password: str = ""
    ssl: bool = False
    llm_provider: str = ""
    llm_model: str = ""
    embedding_model: str = ""
    max_context: int = 16_000
    query_timeout_seconds: int = 15
    max_hybrid_k: int = 10
    max_graph_traversal_seeds: int = 3
    max_graph_row_limit: int = 25
    max_answer_tokens: int = 800
    max_provider_retries: int = 2
    errors: tuple[str, ...] = ()

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> "RagConfig":
        errors: list[str] = []
        enabled = _bool(environ.get("RAG_ENABLE", "false"), "RAG_ENABLE", errors)
        ssl = _bool(environ.get("FALKORDB_SSL", "false"), "FALKORDB_SSL", errors)
        max_context = _positive_int(
            environ.get("RAG_MAX_CONTEXT", "16000"), "RAG_MAX_CONTEXT", 16_000, errors
        )
        timeout = _positive_int(
            environ.get("RAG_QUERY_TIMEOUT_SECONDS", "15"),
            "RAG_QUERY_TIMEOUT_SECONDS",
            15,
            errors,
        )
        max_hybrid_k = _positive_int(
            environ.get("RAG_MAX_HYBRID_K", "10"), "RAG_MAX_HYBRID_K", 10, errors
        )
        max_graph_traversal_seeds = _positive_int(
            environ.get("RAG_MAX_GRAPH_TRAVERSAL_SEEDS", "3"),
            "RAG_MAX_GRAPH_TRAVERSAL_SEEDS",
            3,
            errors,
        )
        max_graph_row_limit = _positive_int(
            environ.get("RAG_MAX_GRAPH_ROW_LIMIT", "25"), "RAG_MAX_GRAPH_ROW_LIMIT", 25, errors
        )
        max_answer_tokens = _positive_int(
            environ.get("RAG_MAX_ANSWER_TOKENS", "800"), "RAG_MAX_ANSWER_TOKENS", 800, errors
        )
        max_provider_retries = _positive_int(
            environ.get("RAG_MAX_PROVIDER_RETRIES", "2"), "RAG_MAX_PROVIDER_RETRIES", 2, errors
        )
        return cls(
            enabled=enabled,
            falkordb_url=environ.get("FALKORDB_URL", "").strip(),
            username=environ.get("FALKORDB_USERNAME", "").strip(),
            password=environ.get("FALKORDB_PASSWORD", ""),
            ssl=ssl,
            llm_provider=environ.get("RAG_LLM_PROVIDER", "").strip(),
            llm_model=environ.get("RAG_LLM_MODEL", "").strip(),
            embedding_model=environ.get("RAG_EMBEDDING_MODEL", "").strip(),
            max_context=max_context,
            query_timeout_seconds=timeout,
            max_hybrid_k=max_hybrid_k,
            max_graph_traversal_seeds=max_graph_traversal_seeds,
            max_graph_row_limit=max_graph_row_limit,
            max_answer_tokens=max_answer_tokens,
            max_provider_retries=max_provider_retries,
            errors=tuple(errors),
        )

    def readiness_errors(self) -> tuple[str, ...]:
        errors = list(self.errors)
        if not self.enabled:
            errors.append("GraphRAG is disabled; set RAG_ENABLE=true")
            return tuple(errors)
        if not self.falkordb_url:
            errors.append("FALKORDB_URL is required when RAG_ENABLE=true")
        else:
            parsed = urlparse(self.falkordb_url)
            if parsed.scheme not in _FALKOR_SCHEMES or not parsed.hostname:
                errors.append(
                    "FALKORDB_URL must use falkor, falkors, redis, or rediss and include a host"
                )
        if not self.llm_provider:
            errors.append("RAG_LLM_PROVIDER is required when RAG_ENABLE=true")
        if not self.llm_model:
            errors.append("RAG_LLM_MODEL is required when RAG_ENABLE=true")
        if not self.embedding_model:
            errors.append("RAG_EMBEDDING_MODEL is required when RAG_ENABLE=true")
        return tuple(errors)

    @property
    def ready(self) -> bool:
        return not self.readiness_errors()

    def public_status(self) -> dict[str, object]:
        """Return health-safe config summary without credentials or secrets."""

        parsed = urlparse(self.falkordb_url)
        return {
            "enabled": self.enabled,
            "ready": self.ready,
            "falkordbHost": parsed.hostname or "",
            "ssl": self.ssl or parsed.scheme in {"falkors", "rediss"},
            "llmProvider": self.llm_provider,
            "llmModel": self.llm_model,
            "embeddingModel": self.embedding_model,
            "maxContext": self.max_context,
            "queryTimeoutSeconds": self.query_timeout_seconds,
            "maxHybridK": self.max_hybrid_k,
            "maxGraphTraversalSeeds": self.max_graph_traversal_seeds,
            "maxGraphRowLimit": self.max_graph_row_limit,
            "maxAnswerTokens": self.max_answer_tokens,
            "maxProviderRetries": self.max_provider_retries,
            "errors": list(self.readiness_errors()),
        }
