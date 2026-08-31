from kb_core_ui.rag import RagConfig


def test_disabled_rag_keeps_base_app_config_valid() -> None:
    config = RagConfig.from_env({})

    assert config.enabled is False
    assert config.ready is False
    assert config.readiness_errors() == ("GraphRAG is disabled; set RAG_ENABLE=true",)


def test_enabled_rag_reports_all_missing_server_config() -> None:
    config = RagConfig.from_env({"RAG_ENABLE": "true"})

    assert config.ready is False
    assert config.readiness_errors() == (
        "FALKORDB_URL is required when RAG_ENABLE=true",
        "RAG_LLM_PROVIDER is required when RAG_ENABLE=true",
        "RAG_LLM_MODEL is required when RAG_ENABLE=true",
        "RAG_EMBEDDING_MODEL is required when RAG_ENABLE=true",
    )


def test_ready_config_hides_credentials_from_public_status() -> None:
    config = RagConfig.from_env(
        {
            "RAG_ENABLE": "yes",
            "FALKORDB_URL": "falkors://graph.example.test:6379",
            "FALKORDB_USERNAME": "reader",
            "FALKORDB_PASSWORD": "secret",
            "RAG_LLM_PROVIDER": "openai",
            "RAG_LLM_MODEL": "gpt-test",
            "RAG_EMBEDDING_MODEL": "embed-test",
            "RAG_MAX_CONTEXT": "24000",
        }
    )

    assert config.ready is True
    status = config.public_status()
    assert status["falkordbHost"] == "graph.example.test"
    assert status["ssl"] is True
    assert "secret" not in repr(status)
    assert "reader" not in repr(status)


def test_invalid_bool_integer_and_url_are_readiness_errors() -> None:
    config = RagConfig.from_env(
        {
            "RAG_ENABLE": "maybe",
            "FALKORDB_SSL": "perhaps",
            "RAG_MAX_CONTEXT": "0",
            "RAG_QUERY_TIMEOUT_SECONDS": "soon",
        }
    )

    assert "RAG_ENABLE must be one of true/false, 1/0, yes/no, or on/off" in config.errors
    assert "FALKORDB_SSL must be one of true/false, 1/0, yes/no, or on/off" in config.errors
    assert "RAG_MAX_CONTEXT must be greater than zero" in config.errors
    assert "RAG_QUERY_TIMEOUT_SECONDS must be an integer" in config.errors
