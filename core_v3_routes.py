# =============================================================================
# k7-core v3.0 | core_v3_routes.py
# Rotas Flask adicionais da v3.0 — cole estas rotas dentro de
# _build_master_app() em core.py, antes do `return app`.
#
# Rotas adicionadas:
#   POST /api/chat              → IntelligenceEngine.chat()
#   GET  /api/intelligence/status → status do motor de IA
#   GET  /api/actions/pending   → ações aguardando aprovação
#   POST /api/actions/<id>/approve → aprova e executa uma ação
#   POST /api/actions/<id>/reject  → rejeita uma ação
#   POST /api/knowledge/index   → aciona reindexação
#   GET  /api/knowledge/status  → status da base de conhecimento
#   POST /api/health/ingest     → ingere dados de health para consciência situacional
# =============================================================================

# ─── Como integrar ao core.py ─────────────────────────────────────────────────
# No _build_master_app(), adicione as importações e as rotas abaixo.
# As importações ficam no topo da função; as rotas antes do `return app`.
# ─────────────────────────────────────────────────────────────────────────────

IMPORT_PATCH = """
# v3.0 — imports de inteligência (adicione no topo de _build_master_app)
try:
    from intelligence import IntelligenceEngine
    from knowledge_base import KnowledgeBase
    _INTEL_OK = True
except ImportError:
    _INTEL_OK = False
"""

ROUTES_PATCH = """
# ══════════════════════════════════════════════════════════════════════════
# ROTAS v3.0 — Chat de Mentoria + Base de Conhecimento + Autonomia
# ══════════════════════════════════════════════════════════════════════════

@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    '''
    Chat de mentoria com RAG + LLM.
    Body: { "message": "...", "project": "ksigner" (opcional) }
    '''
    data    = request.get_json(silent=True) or {}
    message = data.get("message", "").strip()
    project = data.get("project")       # opcional: filtrar por projeto

    if not message:
        return jsonify({"ok": False, "error": "Campo 'message' obrigatório."}), 400

    _audit(current_user.username, "chat", detail=message[:80], ip=request.remote_addr)

    if not _INTEL_OK:
        return jsonify({
            "ok":     True,
            "answer": (
                "O módulo de inteligência não está instalado. "
                "Execute: pip install chromadb sentence-transformers"
            ),
            "model":   "none",
            "sources": [],
            "actions": [],
        })

    try:
        engine = IntelligenceEngine.get(config.NODE_TYPE)
        result = engine.chat(message, for_voice=False, project_filter=project)
        return jsonify({
            "ok":      True,
            "answer":  result["answer"],
            "sources": result["sources"],
            "model":   result["model"],
            "latency": result["latency"],
            "actions": result["actions"],
            "session": result["session"],
        })
    except Exception as exc:
        logger.error(f"[API /chat] {exc}", exc_info=True)
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/intelligence/status", methods=["GET"])
@login_required
def api_intelligence_status():
    '''Status completo do motor de inteligência.'''
    if not _INTEL_OK:
        return jsonify({"ok": False, "available": False,
                        "error": "intelligence.py não instalado."})
    engine = IntelligenceEngine.get(config.NODE_TYPE)
    return jsonify({"ok": True, "available": True, **engine.get_status()})


@app.route("/api/knowledge/status", methods=["GET"])
@login_required
def api_knowledge_status():
    '''Status da base de conhecimento (projetos indexados, chunks).'''
    if not _INTEL_OK:
        return jsonify({"ok": False, "available": False})
    kb = KnowledgeBase.get()
    return jsonify({"ok": True, **kb.status()})


@app.route("/api/knowledge/index", methods=["POST"])
@login_required
def api_knowledge_index():
    '''Aciona reindexação em background.'''
    if not _INTEL_OK:
        return jsonify({"ok": False, "error": "intelligence.py não instalado."}), 400

    force = (request.get_json(silent=True) or {}).get("force", False)
    _audit(current_user.username, "knowledge_index", detail=f"force={force}")

    import threading
    def _run():
        try:
            kb = KnowledgeBase.get()
            kb.index_all(force=force)
        except Exception as e:
            logger.error(f"[API knowledge/index] {e}")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "message": "Indexação iniciada em background."})


@app.route("/api/actions/pending", methods=["GET"])
@login_required
def api_actions_pending():
    '''Lista ações aguardando aprovação do usuário.'''
    if not _INTEL_OK:
        return jsonify({"ok": True, "actions": []})
    engine = IntelligenceEngine.get(config.NODE_TYPE)
    engine._ensure_ready()
    if not engine._autonomy:
        return jsonify({"ok": True, "actions": []})
    pending = engine._autonomy.get_pending()
    return jsonify({"ok": True, "actions": pending, "count": len(pending)})


@app.route("/api/actions/<int:action_id>/approve", methods=["POST"])
@login_required
def api_action_approve(action_id: int):
    '''Aprova e executa uma ação pendente.'''
    if not _INTEL_OK:
        return jsonify({"ok": False, "error": "intelligence.py não instalado."}), 400

    _audit(current_user.username, "action_approve",
           detail=f"action_id={action_id}", ip=request.remote_addr)

    engine = IntelligenceEngine.get(config.NODE_TYPE)
    engine._ensure_ready()
    result = engine._autonomy.approve_and_execute(action_id, current_user.username)
    return jsonify(result)


@app.route("/api/actions/<int:action_id>/reject", methods=["POST"])
@login_required
def api_action_reject(action_id: int):
    '''Rejeita uma ação pendente.'''
    if not _INTEL_OK:
        return jsonify({"ok": False, "error": "intelligence.py não instalado."}), 400

    _audit(current_user.username, "action_reject", detail=f"action_id={action_id}")

    try:
        import sqlite3, config as cfg
        db_path = cfg.AUTH_DB_PATH.replace("k7auth.db", "episodic.db")
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "UPDATE pending_actions SET status='rejected' WHERE id=? AND status='pending'",
                (action_id,)
            )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    return jsonify({"ok": True, "action_id": action_id, "status": "rejected"})


@app.route("/api/health/ingest", methods=["POST"])
@login_required
def api_health_ingest():
    '''
    Ingere dados de /health de um nó para a consciência situacional.
    Chamado automaticamente pelo poll do dashboard a cada ciclo.
    Body: { "node": "spark", "data": { ...health_data... } }
    '''
    if not _INTEL_OK:
        return jsonify({"ok": True, "skipped": True})

    body      = request.get_json(silent=True) or {}
    node      = body.get("node", "")
    data      = body.get("data", {})
    if not node or not data:
        return jsonify({"ok": False, "error": "Campos 'node' e 'data' obrigatórios."}), 400

    try:
        engine = IntelligenceEngine.get(config.NODE_TYPE)
        engine._ensure_ready()
        if engine._awareness:
            engine._awareness.ingest_health(node, data)
        return jsonify({"ok": True})
    except Exception as exc:
        logger.error(f"[API health/ingest] {exc}")
        return jsonify({"ok": False, "error": str(exc)}), 500
"""

# Quando executado diretamente, mostra o patch a ser aplicado
if __name__ == "__main__":
    print("=" * 70)
    print("k7-core v3.0 | Patch de rotas para core.py")
    print("=" * 70)
    print("\n[1] Adicione ao topo de _build_master_app():")
    print(IMPORT_PATCH)
    print("\n[2] Adicione antes do 'return app' em _build_master_app():")
    print(ROUTES_PATCH[:500], "...")
    print("\nArquivo completo disponível em: core_v3_routes.py")
