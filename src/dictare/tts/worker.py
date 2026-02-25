"""Persistent TTS worker subprocess.

Runs as a long-lived process that:
1. Loads the (heavy) TTS engine once at startup
2. Connects as ``__tts__`` agent via the openvip SDK SSE stream
3. Processes speech messages, calling ``engine.speak(text)``
4. Posts completion back to the engine via ``POST /internal/tts/complete``

Usage::

    python -m dictare.tts.worker \\
        --url http://localhost:8770 \\
        --token <bearer-token> \\
        --engine outetts \\
        --language en
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

# Agent ID reserved for the TTS worker
TTS_AGENT_ID = "__tts__"

def _post_completion(
    url: str, token: str, request_id: str, ok: bool, duration_ms: int = 0
) -> None:
    """Notify the engine that a speak() call finished."""
    body = json.dumps({
        "request_id": request_id,
        "ok": ok,
        "duration_ms": duration_ms,
    }).encode()
    req = urllib.request.Request(
        f"{url}/internal/tts/complete",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception:
        logger.warning("Failed to post TTS completion for %s", request_id, exc_info=True)

def main(argv: list[str] | None = None) -> None:
    """Entry point for the TTS worker subprocess."""
    parser = argparse.ArgumentParser(description="Dictare TTS worker")
    parser.add_argument("--url", default="http://localhost:8770", help="Engine URL")
    parser.add_argument("--token", required=True, help="Bearer token")
    parser.add_argument("--engine", required=True, help="TTS engine name")
    parser.add_argument("--language", default="en", help="Language code")
    parser.add_argument("--voice", default="", help="Voice name")
    parser.add_argument("--speed", type=int, default=175, help="Speed")
    args = parser.parse_args(argv)

    from pathlib import Path

    log_dir = Path.home() / ".local" / "share" / "dictare" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "tts-worker.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [tts-worker] %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(),
        ],
    )

    # 1. Load TTS engine (expensive — done ONCE)
    logger.info("Loading TTS engine: %s (language=%s)", args.engine, args.language)
    from dictare.config import TTSConfig
    from dictare.tts import create_tts_engine

    tts_config = TTSConfig(
        engine=args.engine,
        language=args.language,
        voice=args.voice,
        speed=args.speed,
    )
    try:
        tts_engine = create_tts_engine(tts_config)
    except Exception:
        logger.error("Failed to create TTS engine", exc_info=True)
        sys.exit(1)

    logger.info("TTS engine loaded: %s", tts_engine.get_name())

    # 2. Connect as __tts__ via openvip SDK
    from openvip import Client
    from openvip.models.speech_request import SpeechRequest

    client = Client(
        args.url,
        headers={"Authorization": f"Bearer {args.token}"},
    )

    logger.info("Subscribing as %s at %s", TTS_AGENT_ID, args.url)

    # 3. Process speech messages (reconnect=True for resilience)
    import time
    import urllib.error as _urlerr

    _consecutive_403 = 0
    _max_403 = 3  # Exit after 3 consecutive 403s (token expired → engine restarted)

    def _on_connect() -> None:
        nonlocal _consecutive_403
        _consecutive_403 = 0
        logger.info("Connected as %s", TTS_AGENT_ID)

    def _on_disconnect(exc: BaseException | None) -> None:
        nonlocal _consecutive_403
        if isinstance(exc, _urlerr.HTTPError) and exc.code == 403:
            _consecutive_403 += 1
            logger.warning("SSE HTTP 403 (%d/%d)", _consecutive_403, _max_403)
            if _consecutive_403 >= _max_403:
                logger.info("Token expired — exiting (engine was restarted)")
                sys.exit(0)
        else:
            _consecutive_403 = 0
            logger.warning("Disconnected: %s", exc)

    for msg in client.subscribe(
        TTS_AGENT_ID,
        reconnect=True,
        on_connect=_on_connect,
        on_disconnect=_on_disconnect,
    ):
        if not isinstance(msg, SpeechRequest):
            logger.debug("Ignoring non-speech message: type=%s", msg.type)
            continue

        text = msg.text
        request_id = msg.additional_properties.get("request_id", "")
        voice = msg.additional_properties.get("voice")
        language = msg.language  # SpeechRequest has language as a native field
        logger.info("Speaking: %r (request_id=%s, voice=%s, lang=%s)", text, request_id, voice, language)

        start = time.time()
        try:
            ok = tts_engine.speak(text, voice=voice, language=language)
        except Exception:
            logger.warning("TTS speak failed for %r", text, exc_info=True)
            ok = False
        duration_ms = int((time.time() - start) * 1000)

        if request_id:
            _post_completion(args.url, args.token, request_id, ok, duration_ms)

if __name__ == "__main__":
    main()
