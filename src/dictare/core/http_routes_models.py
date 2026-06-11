"""Models and capabilities routes: STT/TTS model downloads, venv installs.

Registered on the FastAPI app by OpenVIPServer._create_app().
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

if TYPE_CHECKING:
    from dictare.core.http_server import OpenVIPServer

logger = logging.getLogger(__name__)


def register_models_routes(app: FastAPI, server: OpenVIPServer) -> None:
    """Register models, capabilities, and TTS venv endpoints on *app*."""

    @app.get("/api/models")
    async def models_list_api():
        """List all models with cache and configured status."""
        from dictare.cli.models import _get_configured_models, _get_model_registry
        from dictare.config import load_config
        from dictare.utils.hf_download import get_cache_size, is_repo_cached

        config = load_config()
        registry = _get_model_registry()
        configured = _get_configured_models(config)

        result = []
        for model_id, info in registry.items():
            repo = info.get("repo")
            if not repo:
                continue  # skip builtins in legacy /models endpoint
            check_file = info.get("check_file", "config.json")
            cached = await asyncio.to_thread(is_repo_cached, repo, check_file)
            cache_size = await asyncio.to_thread(get_cache_size, repo) if cached else 0

            job = server.download_jobs.get(model_id)
            downloading = job is not None and job.get("status") == "downloading"

            result.append({
                "id": model_id,
                "type": info["type"],
                "description": info["description"],
                "size_gb": info["size_gb"],
                "cached": cached,
                "cache_size_bytes": cache_size,
                "configured": configured.get(model_id, ""),
                "downloading": downloading,
                "download_fraction": job.get("fraction") if downloading else None,
                "downloaded_bytes": job.get("downloaded_bytes", 0) if downloading else 0,
                "total_bytes": job.get("total_bytes", 0) if downloading else 0,
            })

        return {"models": result}

    @app.post("/api/models/{model_id}/pull")
    async def models_pull_api(model_id: str):
        """Start async download of a model."""
        from dictare.cli.models import _get_model_registry
        from dictare.utils.hf_download import is_repo_cached

        registry = _get_model_registry()
        if model_id not in registry:
            raise HTTPException(status_code=404, detail=f"Unknown model: {model_id}")

        info = registry[model_id]
        repo = info["repo"]
        check_file = info.get("check_file", "config.json")

        if await asyncio.to_thread(is_repo_cached, repo, check_file):
            return {"status": "cached"}

        if model_id in server.download_jobs and server.download_jobs[model_id].get("status") == "downloading":
            return {"status": "downloading"}

        loop = asyncio.get_running_loop()
        t = threading.Thread(
            target=server.run_model_download,
            args=(model_id, info, loop),
            daemon=True,
            name=f"model-dl-{model_id}",
        )
        t.start()
        return {"status": "started"}

    @app.get("/api/models/pull-progress")
    async def models_pull_progress(request: Request):
        """SSE stream for model download progress."""
        pq: asyncio.Queue = asyncio.Queue()
        with server.progress_queues_lock:
            server.progress_queues.append(pq)

        # Send snapshot of all in-progress jobs on connect
        for mid, job in server.download_jobs.items():
            await pq.put({"model_id": mid, **job})

        async def event_generator():
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.wait_for(pq.get(), timeout=30.0)
                        yield {"data": json.dumps(event, ensure_ascii=False, default=str)}
                    except TimeoutError:
                        yield {"comment": "keepalive"}
            finally:
                with server.progress_queues_lock:
                    try:
                        server.progress_queues.remove(pq)
                    except ValueError:
                        pass

        return EventSourceResponse(event_generator())

    # ----- TTS Venv Install/Uninstall API (legacy, kept for compat) -----

    @app.post("/api/tts-engines/{engine}/install")
    async def tts_engine_install(engine: str):
        """Install an isolated TTS venv for an engine."""
        from dictare.tts.venv import VENV_ENGINES

        if engine not in VENV_ENGINES:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown venv engine: {engine}. Valid: {', '.join(VENV_ENGINES)}",
            )

        job_id = f"tts-install-{engine}"
        if job_id in server.download_jobs and server.download_jobs[job_id].get("status") == "downloading":
            return {"status": "installing"}

        loop = asyncio.get_running_loop()
        t = threading.Thread(
            target=server.run_tts_install,
            args=(engine, loop),
            daemon=True,
            name=f"tts-install-{engine}",
        )
        t.start()
        return {"status": "started"}

    @app.delete("/api/tts-engines/{engine}/install")
    async def tts_engine_uninstall(engine: str):
        """Remove the isolated TTS venv for an engine."""
        from dictare.tts.venv import VENV_ENGINES, uninstall_venv

        if engine not in VENV_ENGINES:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown venv engine: {engine}. Valid: {', '.join(VENV_ENGINES)}",
            )

        await asyncio.to_thread(uninstall_venv, engine)
        return {"status": "ok"}

    # ----- Capabilities API (unified models + engines) -----

    @app.get("/api/capabilities")
    async def capabilities_list():
        """List all STT/TTS capabilities with install and config status."""
        import shutil
        import sys

        from dictare.cli.models import _get_configured_models, _get_model_registry
        from dictare.config import load_config
        from dictare.tts.venv import is_venv_installed
        from dictare.utils.hardware import is_apple_silicon
        from dictare.utils.hf_download import is_repo_cached

        config = load_config()
        registry = _get_model_registry()
        configured = _get_configured_models(config)

        result = []
        for cap_id, info in registry.items():
            cap_type = info["type"]
            builtin = info.get("builtin", False)
            platform_req = info.get("platform")
            venv_name = info.get("venv")
            repo = info.get("repo")
            check_file = info.get("check_file", "config.json")

            # Platform check
            if platform_req == "darwin":
                platform_ok = sys.platform == "darwin"
            elif platform_req == "apple_silicon":
                platform_ok = await asyncio.to_thread(is_apple_silicon)
            else:
                platform_ok = True

            # Venv check
            if venv_name:
                venv_installed = await asyncio.to_thread(is_venv_installed, venv_name)
            else:
                venv_installed = True  # no venv needed

            # Model cache check
            if repo:
                model_cached = await asyncio.to_thread(is_repo_cached, repo, check_file)
            else:
                model_cached = True  # no model to download

            # Builtin readiness: check binary exists
            if builtin:
                if cap_id == "say":
                    ready = platform_ok and await asyncio.to_thread(
                        lambda: shutil.which("say") is not None
                    )
                elif cap_id == "espeak":
                    ready = await asyncio.to_thread(
                        lambda: (
                            shutil.which("espeak-ng") is not None
                            or shutil.which("espeak") is not None
                        )
                    )
                else:
                    ready = platform_ok
            else:
                ready = platform_ok and venv_installed and model_cached

            # Download state
            job = server.download_jobs.get(cap_id) or server.download_jobs.get(f"tts-install-{venv_name}")
            downloading = job is not None and job.get("status") == "downloading"

            result.append({
                "id": cap_id,
                "type": cap_type,
                "description": info["description"],
                "size_gb": info["size_gb"],
                "platform_ok": platform_ok,
                "ready": ready,
                "venv_installed": venv_installed if venv_name else None,
                "model_cached": model_cached if repo else None,
                "configured": cap_id in configured,
                "builtin": builtin,
                "downloading": downloading,
                "download_fraction": job.get("fraction") if downloading else None,
            })

        return {"capabilities": result}

    @app.post("/api/capabilities/{cap_id}/install")
    async def capability_install(cap_id: str):
        """Install a capability (venv + model download)."""
        from dictare.cli.models import _get_model_registry
        from dictare.tts.venv import is_venv_installed
        from dictare.utils.hf_download import is_repo_cached

        registry = _get_model_registry()
        if cap_id not in registry:
            raise HTTPException(status_code=404, detail=f"Unknown capability: {cap_id}")

        info = registry[cap_id]
        if info.get("builtin"):
            raise HTTPException(status_code=400, detail="Builtin capability — nothing to install")

        venv_name = info.get("venv")
        repo = info.get("repo")

        # Already fully installed?
        venv_ok = not venv_name or is_venv_installed(venv_name)
        model_ok = not repo or is_repo_cached(repo, info.get("check_file", "config.json"))
        if venv_ok and model_ok:
            return {"status": "ready"}

        # Check for existing job
        if cap_id in server.download_jobs and server.download_jobs[cap_id].get("status") == "downloading":
            return {"status": "installing"}

        loop = asyncio.get_running_loop()
        t = threading.Thread(
            target=server.run_capability_install,
            args=(cap_id, info, loop),
            daemon=True,
            name=f"cap-install-{cap_id}",
        )
        t.start()
        return {"status": "started"}

    @app.delete("/api/capabilities/{cap_id}/install")
    async def capability_uninstall(cap_id: str):
        """Uninstall a capability: removes venv and/or cached model files."""
        import shutil

        from dictare.cli.models import _get_model_registry
        from dictare.tts.venv import VENV_ENGINES, uninstall_venv
        from dictare.utils.hf_download import get_hf_cache_dir

        registry = _get_model_registry()
        if cap_id not in registry:
            raise HTTPException(status_code=404, detail=f"Unknown capability: {cap_id}")

        info = registry[cap_id]
        if info.get("builtin"):
            raise HTTPException(status_code=400, detail="Cannot remove a builtin capability")

        venv_name = info.get("venv")
        repo = info.get("repo")

        if not venv_name and not repo:
            raise HTTPException(status_code=400, detail="Nothing to remove for this capability")

        if venv_name and venv_name in VENV_ENGINES:
            await asyncio.to_thread(uninstall_venv, venv_name)

        if repo:
            cache_dir = get_hf_cache_dir(repo)
            if cache_dir.exists():
                await asyncio.to_thread(shutil.rmtree, cache_dir, True)

        return {"status": "ok"}

    @app.post("/api/capabilities/{cap_id}/select")
    async def capability_select(cap_id: str):
        """Select a capability as the active STT model or TTS engine.

        Maps capability ID to the appropriate config key/value,
        saves it, and triggers an engine restart.
        """
        from dictare.cli.models import _get_model_registry
        from dictare.config import set_config_value

        registry = _get_model_registry()
        if cap_id not in registry:
            raise HTTPException(status_code=404, detail=f"Unknown capability: {cap_id}")

        info = registry[cap_id]
        cap_type = info["type"]

        if cap_type == "stt":
            # Map registry key to stt.model value
            # "whisper-tiny" → "tiny", "parakeet-v3" → "parakeet-v3"
            if cap_id.startswith("whisper-"):
                model_value = cap_id[len("whisper-"):]
            else:
                model_value = cap_id
            try:
                set_config_value("stt.model", model_value)
                logger.info("capabilities.select stt.model=%s", model_value)
            except (KeyError, ValueError) as e:
                raise HTTPException(status_code=400, detail=str(e))

        elif cap_type == "tts":
            # Map registry key to tts.engine value
            # "coqui-xtts-v2" → "coqui" (via venv field), "piper" → "piper"
            engine_value = info.get("venv", cap_id)
            try:
                set_config_value("tts.engine", engine_value)
                logger.info("capabilities.select tts.engine=%s", engine_value)
            except (KeyError, ValueError) as e:
                raise HTTPException(status_code=400, detail=str(e))

        else:
            raise HTTPException(status_code=400, detail=f"Unknown type: {cap_type}")

        return {"status": "ok", "restart_required": True}
