# Dictare — Developer Guide for AI Assistants

## What Is Dictare

Voice layer for AI coding agents. Implements the OpenVIP protocol.
Agents (Claude Code, Cursor, Aider) connect via SSE and receive voice transcriptions.

**What it is NOT**: a voice-to-text tool, a subscription proxy, an autonomous agent loop,
or a multi-agent orchestrator. It is a voice input layer, nothing more.

## Architecture

- `src/dictare/core/` — engine, STT, pipeline, HTTP server (FastAPI + OpenVIP)
- `src/dictare/pipeline/` — filters and executors (composable, DI via `PipelineLoader`)
- `src/dictare/tts/` — TTS engines (Kokoro, Piper, espeak, macOS `say`)
- `src/dictare/audio/` — capture, VAD, beep feedback, device monitoring
- `src/dictare/agent/` — agent client (uses openvip SDK)
- `src/dictare/daemon/` — launchd (macOS) / systemd (Linux) service management
- `src/dictare/tray/` — system tray app (pystray, cross-platform)
- `src/dictare/cli/` — typer CLI entry points

## Development Workflow

```bash
# Run tests
uv run --python 3.11 pytest tests/ -x --tb=short

# Lint
uv run --python 3.11 ruff check .

# Type check
uv run --python 3.11 mypy src/
```

**Python 3.11 only** — always use `uv run --python 3.11`.

## Branch Workflow

**Always work on a branch, never commit directly to main.**
Create a branch at the start of every task (`fix/`, `feat/`, `refactor/`, etc.).
Only exception: the user explicitly says to work on main.

## Commit Conventions

Prefixes: `feat:` / `fix:` / `refactor:` / `docs:` / `test:` / `chore:`

Versioning: SemVer — MINOR for features, PATCH for bug fixes, MAJOR for breaking changes.

After every change: run tests → lint → typecheck → bump version in
`src/dictare/__init__.py` → update `CHANGELOG.md` → commit.

**Never push or tag without explicit user approval.**

## Release Procedure

Release is **fully automated** by the CI workflow `0 - release: publish`.
**Do NOT create tags locally.** The workflow creates the tag, GitHub Release,
publishes to PyPI, and updates the Homebrew tap — all in one step.

To release:
1. Bump version in `src/dictare/__init__.py` + update `CHANGELOG.md`
2. Merge to main via PR
3. Trigger the workflow: `gh workflow run publish-pypi.yml -R dragfly/dictare --ref main`
4. Done — the workflow handles everything else

**Never** run `git tag` locally for releases. The workflow does it.

## Language Policy

All code, comments, docstrings, commit messages, and documentation must be in **English**.

## OpenVIP SDK

Client-side code uses `from openvip import Client` (PyPI package `openvip`).
The SDK is a required dependency — never bypass it with raw HTTP calls.

## Cross-Platform

UX must be identical on macOS and Linux. No platform-specific UI code.
Settings and any GUI use the browser-based web UI served by the engine.
