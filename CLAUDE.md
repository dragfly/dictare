# Voxtype — Voice-first control for AI coding agents

## STRATEGIC DIRECTION (NON DEVIARE MAI)

### Identità
- **Voxtype è la REFERENCE IMPLEMENTATION del protocollo OpenVIP**
- Voxtype è un VOICE LAYER — controlla AI coding agents (Claude Code, Cursor, Aider) via voce
- USP: unico tool open source, locale, voice-to-AGENT (non voice-to-text)
- Competitors (Wispr Flow, Serenade, Willow Voice) sono tutti voice-to-TEXT

### Eat Your Own Dogfood — REGOLA FONDAMENTALE
- Voxtype DEVE usare l'SDK `openvip` (`from openvip import Client`) per TUTTO il codice client-side
- L'SDK vive in `/home/user/repos/nottoplay/openvip-sdks/python/`
- Se voxtype non usa il suo SDK, nessuno lo userà. L'SDK NON è opzionale, MAI.
- Il codice client (agent/mux.py SSE, agent/sse.py, cli/speak.py, tray/app.py) DEVE usare l'SDK

### Cross-platform UX
- **UX must be identical on macOS and Linux** — no platform-specific UI code
- Use browser-based UI (served from existing FastAPI) for any GUI needs
- Tray menu via pystray (cross-platform), settings via web browser

### Cosa NON costruire
- ❌ Subscription-to-API proxy (claude-max-api-proxy lo fa)
- ❌ Autonomous loop engine (Ralph Wiggum è ufficiale Anthropic)
- ❌ Multi-agent orchestrator (Gas Town, Claude Squad)
- ❌ Web UI per chat (scope creep)
- Voxtype = voice layer + service. Il resto è ecosystem.

### Language Policy
- **Base language: English** — all code, comments, docstrings, docs, commit messages in English
- **Multilingual data is OK** — trigger words, translations, i18n strings can include Italian and other languages, but ONLY if multiple languages are present (e.g., en + it + es + de + fr)
- **Never Italian alone** — Italian-only text is an information leak that reveals the developer's nationality. Either English-only or multilingual (3+ languages).

### Pubblicazione
- openvip SDK e voxtype vanno su PyPI INSIEME — pubblicazione simultanea
- Versioning: SemVer, partendo da 0.1.0 (storia interna 3.x non è pubblica)
- openvip è dependency obbligatoria in pyproject.toml

---

## ARCHITETTURA

### Pipeline
- `pipeline/{base.py, filters/, executors/, loader.py}` — filters enrich, executors act
- Extension fields: structured objects (`x_input`, `x_agent_switch`)
- `PipelineLoader`: inspect.signature() DI — risolve params da services → config attrs → defaults
- Public API: `from voxtype.pipeline import Pipeline, PipelineLoader, register_step`

### Servizio
- Engine gira come system service (launchd macOS / systemd Linux) — modello Ollama
- `voxtype service install` → engine parte al login → tray icon → ready
- `voxtype agent claude` → single command, auto-connect all'engine

---

## COME LAVORARE

### ⛔ Prima di implementare: CHIEDI
1. **Investiga** — leggi il codice, trova la causa
2. **Riassumi il problema** in 3-4 righe
3. **Proponi opzioni** (1-2 righe max per opzione)
4. **Aspetta** che l'utente scelga ("fixalo", "fallo", "vai")
5. **MAI cambiare comportamento architetturale senza approvazione** — se qualcosa sembra "inutile" (es. mic muting durante play), chiedere PERCHÉ esiste prima di rimuoverlo. Spesso c'è una ragione non ovvia (es. utente può configurare TTS al posto del beep).

### Principi Python
- **Senior Python Architect**: codice idiomatico, librerie standard, type hints
- **No reinventare la ruota** — se esiste una soluzione standard, usala
- **Analizza prima** — verifica come il codebase fa cose simili

### Test
- Test per OGNI fix/feature — non opzionale
- MAI `time.sleep()` — usa `_wait_until()` o chiama handler direttamente
- Mock over real time. Test veloci < 1s

### Dopo ogni cambiamento
1. `uv run python -m pytest tests/ -x --tb=short`
2. `uv run ruff check .`
3. `uv run mypy src/`
4. Aggiorna CHANGELOG.md + bump versione in `src/voxtype/__init__.py`
5. ⛔ **Commit + tag + push PRIMA di fare qualsiasi altra cosa**

⚠️ NON iniziare nuovi task finché il commit non è pushato.

### Commit
- Prefissi: `feat:` / `fix:` / `refactor:` / `docs:` / `test:` / `chore:`
- SemVer: MINOR per feature, PATCH per bugfix, MAJOR per breaking changes
- Python 3.11 only. Usa `uv run --python 3.11` per tutto.

## Istruzioni per Compaction
Quando compatti il contesto, PRESERVA SEMPRE:
- Direzione strategica (voice layer, OpenVIP reference impl, dogfooding SDK)
- Lista "cosa NON costruire"
- Task corrente e il suo contesto architetturale
