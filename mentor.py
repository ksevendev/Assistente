# =============================================================================
# k7-core v3.0 | commands/mentor.py
# Módulo de Comandos de Mentoria — integra voz ao IntelligenceEngine
#
# Gatilhos de voz → IntelligenceEngine.chat() → resposta com personalidade
# =============================================================================

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger("k7.cmd.mentor")

DESCRIPTION = "v3.0: Mentoria de projetos, análise RAG, autonomia supervisionada"


def _intel():
    """Import lazy do IntelligenceEngine (evita inicialização no boot)."""
    try:
        from intelligence import IntelligenceEngine
        import config
        return IntelligenceEngine.get(config.NODE_TYPE)
    except ImportError as e:
        logger.error(f"[MENTOR] intelligence.py não disponível: {e}")
        return None


# ─── Handlers de voz ──────────────────────────────────────────────────────────

def cmd_chat(text: str, speak: Callable) -> None:
    """Conversa sobre projetos usando RAG + LLM."""
    engine = _intel()
    if not engine:
        speak("O módulo de inteligência não está disponível. Verifique a instalação.")
        return
    speak("Consultando minha base de conhecimento...")
    result = engine.chat(text, for_voice=True)
    answer = result.get("answer") or "Não encontrei informação suficiente nos projetos."
    speak(answer)
    if result.get("actions"):
        n = len(result["actions"])
        speak(f"Tenho {n} ação pendente aguardando sua aprovação no dashboard.")


def cmd_analisa_projeto(text: str, speak: Callable) -> None:
    """Pede análise de um projeto específico."""
    import re
    projetos = ["k7 barber", "ksigner", "synap", "keryon", "k7-core", "k7core"]
    lower    = text.lower()
    projeto  = next((p for p in projetos if p in lower), None)
    engine   = _intel()
    if not engine:
        speak("Módulo de inteligência indisponível."); return
    if not projeto:
        speak("Qual projeto você quer que eu analise? K7 Barber, KSigner, SYNAP, Keryon ou k7-core?")
        return
    speak(f"Analisando o projeto {projeto}...")
    result = engine.chat(
        f"Analise o projeto {projeto}: pontos fortes, pontos de melhoria e sugestões técnicas.",
        for_voice=True, project_filter=projeto
    )
    speak(result.get("answer") or "Não tenho informação suficiente sobre esse projeto.")


def cmd_status_inteligencia(text: str, speak: Callable) -> None:
    """Informa o status do motor de inteligência."""
    engine = _intel()
    if not engine:
        speak("O motor de inteligência não está carregado."); return
    st = engine.get_status()
    speak(
        f"Motor de inteligência ativo. "
        f"Usando {st['llm']}. "
        f"{st['kb_chunks']} trechos de código indexados de {st['kb_projects']} projetos. "
        f"{st['pending_actions']} ações aguardando aprovação."
    )


def cmd_pendentes(text: str, speak: Callable) -> None:
    """Lista ações pendentes de aprovação."""
    engine = _intel()
    if not engine or not engine._autonomy:
        speak("Sistema de autonomia não disponível."); return
    engine._ensure_ready()
    pendentes = engine._autonomy.get_pending()
    if not pendentes:
        speak("Nenhuma ação pendente no momento. Tudo certo.")
        return
    speak(f"Tenho {len(pendentes)} ação pendente.")
    for i, a in enumerate(pendentes[:3], 1):
        speak(f"Ação {i}: {a['description'][:100]}")
    speak("Acesse o dashboard para aprovar ou rejeitar.")


def cmd_aprovar_acao(text: str, speak: Callable) -> None:
    """Aprova a última ação pendente por voz."""
    engine = _intel()
    if not engine or not engine._autonomy:
        speak("Sistema de autonomia não disponível."); return
    engine._ensure_ready()
    pendentes = engine._autonomy.get_pending()
    if not pendentes:
        speak("Não há ações pendentes para aprovar."); return
    action = pendentes[0]
    speak(f"Aprovando: {action['description'][:80]}. Executando...")
    result = engine._autonomy.approve_and_execute(action["id"], approved_by="voice")
    if result.get("ok"):
        speak("Ação executada com sucesso.")
    else:
        speak(f"Falha na execução: {result.get('error', 'erro desconhecido')}")


def cmd_indexar(text: str, speak: Callable) -> None:
    """Aciona reindexação dos projetos."""
    import threading
    speak("Iniciando indexação dos projetos em background. Isso pode levar alguns minutos.")

    def _run():
        try:
            from knowledge_base import KnowledgeBase
            kb = KnowledgeBase.get()
            results = kb.index_all(force=False)
            total_chunks = sum(r.get("chunks", 0) for r in results.values())
            logger.info(f"[MENTOR] Indexação concluída: {total_chunks} chunks novos.")
        except Exception as e:
            logger.error(f"[MENTOR] Erro na indexação: {e}")

    threading.Thread(target=_run, daemon=True).start()


COMMANDS: dict = {
    # Conversa / RAG
    "me fala sobre":         cmd_chat,
    "explica":               cmd_chat,
    "como funciona":         cmd_chat,
    "o que é":               cmd_chat,
    "me ajuda com":          cmd_chat,
    "analisa o código":      cmd_chat,
    "o que você acha de":    cmd_chat,
    "como eu faço":          cmd_chat,
    "qual a diferença":      cmd_chat,
    "me dá uma ideia":       cmd_chat,
    "sugere":                cmd_chat,

    # Projetos específicos
    "analisa o projeto":     cmd_analisa_projeto,
    "analisa projeto":       cmd_analisa_projeto,
    "fala do projeto":       cmd_analisa_projeto,

    # Status e controle
    "status da inteligência": cmd_status_inteligencia,
    "status inteligência":    cmd_status_inteligencia,
    "ações pendentes":        cmd_pendentes,
    "o que está pendente":    cmd_pendentes,
    "aprovar ação":           cmd_aprovar_acao,
    "pode executar":          cmd_aprovar_acao,
    "indexar projetos":       cmd_indexar,
    "reindexar":              cmd_indexar,
}
