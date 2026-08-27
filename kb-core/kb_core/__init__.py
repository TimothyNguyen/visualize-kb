"""kb-core - extract · build · cluster · analyze · report."""


def __getattr__(name):
    # Lazy imports so `kb_core install` works before heavy deps are in place.
    _map = {
        "extract": ("kb_core.extract", "extract"),
        "collect_files": ("kb_core.extract", "collect_files"),
        "build_from_json": ("kb_core.build", "build_from_json"),
        "cluster": ("kb_core.cluster", "cluster"),
        "score_all": ("kb_core.cluster", "score_all"),
        "cohesion_score": ("kb_core.cluster", "cohesion_score"),
        "god_nodes": ("kb_core.analyze", "god_nodes"),
        "surprising_connections": ("kb_core.analyze", "surprising_connections"),
        "suggest_questions": ("kb_core.analyze", "suggest_questions"),
        "generate": ("kb_core.report", "generate"),
        "to_json": ("kb_core.export", "to_json"),
        "to_html": ("kb_core.export", "to_html"),
        "to_svg": ("kb_core.export", "to_svg"),
        "to_canvas": ("kb_core.export", "to_canvas"),
        "to_wiki": ("kb_core.wiki", "to_wiki"),
        "reflect": ("kb_core.reflect", "reflect"),
        "save_query_result": ("kb_core.ingest", "save_query_result"),
    }
    if name in _map:
        import importlib
        mod_name, attr = _map[name]
        mod = importlib.import_module(mod_name)
        return getattr(mod, attr)
    raise AttributeError(f"module 'kb-core' has no attribute {name!r}")
