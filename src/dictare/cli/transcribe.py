"""Transcribe command — local STT from any media file. 100% offline."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Annotated

import typer


def _translate_local(text: str, from_lang: str, to_lang: str) -> str:
    """Translate using NLLB-200 via CTranslate2 — 100% local, no PyTorch needed."""
    import os
    import ctranslate2
    import sentencepiece as spm

    # NLLB flores-200 language codes
    NLLB_CODES: dict[str, str] = {
        "it": "ita_Latn", "en": "eng_Latn", "fr": "fra_Latn",
        "de": "deu_Latn", "es": "spa_Latn", "pt": "por_Latn",
        "nl": "nld_Latn", "pl": "pol_Latn", "ru": "rus_Cyrl",
        "zh": "zho_Hans", "ja": "jpn_Jpan", "ko": "kor_Hang",
        "ar": "arb_Arab", "tr": "tur_Latn", "sv": "swe_Latn",
        "da": "dan_Latn", "fi": "fin_Latn", "nb": "nob_Latn",
    }
    src = NLLB_CODES.get(from_lang, from_lang)
    tgt = NLLB_CODES.get(to_lang, to_lang)

    model_dir = os.path.expanduser("~/.cache/ctranslate2/nllb-600m-int8")
    # SPM tokenizer lives in the original HF model cache
    hf_cache = os.path.expanduser("~/.cache/huggingface/hub/models--facebook--nllb-200-distilled-600M")
    spm_path = next(
        (os.path.join(r, f) for r, _, files in os.walk(hf_cache) for f in files if f.endswith(".spm") or f == "sentencepiece.bpe.model"),
        None,
    )
    if spm_path is None:
        raise RuntimeError("sentencepiece.bpe.model not found in NLLB HF cache")

    sp = spm.SentencePieceProcessor()
    sp.load(spm_path)
    translator = ctranslate2.Translator(model_dir, device="cpu", inter_threads=4)

    # Split into chunks (max ~600 chars each to stay within token limit)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    chunks, current, current_len = [], [], 0
    for line in lines:
        if current_len + len(line) > 600:
            if current:
                chunks.append(" ".join(current))
            current, current_len = [], 0
        current.append(line)
        current_len += len(line)
    if current:
        chunks.append(" ".join(current))

    results = []
    for chunk in chunks:
        tokens = sp.encode(chunk, out_type=str)
        # NLLB CTranslate2 format: tokens + </s> + src_lang
        src_tokens = tokens + ["</s>", src]
        output = translator.translate_batch([src_tokens], target_prefix=[[tgt]])
        tgt_tokens = output[0].hypotheses[0][1:]  # skip target lang prefix token
        results.append(sp.decode(tgt_tokens))

    return "\n".join(results)


def register(app: typer.Typer) -> None:
    @app.command()
    def transcribe(
        file: Annotated[Path, typer.Argument(help="Media file to transcribe (mp4, mkv, wav, ...)")],
        parakeet: Annotated[bool, typer.Option("--parakeet", help="Use Parakeet via onnx-asr")] = False,
        model: Annotated[str, typer.Option("--model", help="faster-whisper model name")] = "large-v3-turbo",
        translate: Annotated[str | None, typer.Option("--translate", help="Translate to language code (it, en, fr, de, es, ...) — local model")] = None,
        from_lang: Annotated[str | None, typer.Option("--from-lang", help="Source language for translation (required with --parakeet --translate)")] = None,
        timestamps: Annotated[bool, typer.Option("--timestamps", help="Prefix each line with [HH:MM:SS] (faster-whisper only)")] = False,
    ) -> None:
        """Transcribe a media file to stdout using local STT. 100% offline, no temp files."""
        import numpy as np

        if not file.exists():
            typer.echo(f"File not found: {file}", err=True)
            raise typer.Exit(1)

        # Extract audio in memory — dynaudnorm amplifies quiet speech dynamically
        typer.echo(f"► Extracting audio from {file.name} ...", err=True)
        proc = subprocess.run(
            [
                "ffmpeg", "-i", str(file),
                "-af", "dynaudnorm=p=0.9:s=5",
                "-ar", "16000", "-ac", "1", "-f", "f32le", "-",
            ],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        if proc.returncode != 0:
            typer.echo("ffmpeg failed — is ffmpeg installed?", err=True)
            raise typer.Exit(1)

        audio = np.frombuffer(proc.stdout, dtype=np.float32)
        duration = len(audio) / 16000
        typer.echo(f"  audio: {duration:.1f}s", err=True)

        detected_lang: str | None = None

        if parakeet:
            import onnx_asr
            typer.echo("► Loading model: nemo-parakeet-tdt-0.6b-v3 ...", err=True)
            providers = ["CPUExecutionProvider"] if sys.platform == "darwin" else None
            m = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v3", providers=providers)
            typer.echo("► Transcribing ...", err=True)
            text = m.recognize(audio, sample_rate=16_000).strip()
            detected_lang = from_lang  # parakeet doesn't expose language

        else:
            from faster_whisper import WhisperModel
            typer.echo(f"► Loading model: {model} ...", err=True)
            m = WhisperModel(model, device="auto", compute_type="int8")
            typer.echo("► Transcribing ...", err=True)
            segments, info = m.transcribe(audio, beam_size=5)
            typer.echo(f"  language: {info.language}  (p={info.language_probability:.2f})", err=True)
            detected_lang = from_lang or info.language

            def _fmt(seconds: float) -> str:
                m2, s = divmod(int(seconds), 60)
                return f"{m2:02d}:{s:02d}"

            lines = []
            for seg in segments:
                line = f"[{_fmt(seg.start)}] {seg.text.strip()}"
                lines.append(line)
            text = "\n".join(lines)

        if translate:
            if not detected_lang:
                typer.echo("--from-lang required when using --parakeet --translate", err=True)
                raise typer.Exit(1)
            typer.echo(f"► Translating [{detected_lang}] → [{translate}] (local model) ...", err=True)
            text = _translate_local(text, detected_lang, translate)

        typer.echo("\n" + "─" * 60, err=True)
        typer.echo(text)
