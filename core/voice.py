"""TTS (macOS `say`) + STT (record audio + send to local Whisper if available).

Speak is sync. Listen records to a file; transcription is delegated to
whatever STT backend the user has (Flow, whisper-cpp, faster-whisper).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional


def speak(text: str, *, voice: Optional[str] = None,
          rate: Optional[int] = None, async_mode: bool = False) -> dict:
    cmd = ["say"]
    if voice:
        cmd += ["-v", voice]
    if rate:
        cmd += ["-r", str(rate)]
    cmd.append(text)
    try:
        if async_mode:
            subprocess.Popen(cmd)
            return {"ok": True, "spoken": text[:200], "async": True}
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return {"ok": r.returncode == 0, "spoken": text[:200],
                "stderr": r.stderr.strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def list_voices() -> list[dict]:
    try:
        r = subprocess.run(["say", "-v", "?"], capture_output=True,
                           text=True, timeout=5)
        out = []
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                out.append({"name": parts[0], "lang": parts[1]})
        return out
    except Exception:
        return []


def record(seconds: float = 5.0, out_path: str = "/tmp/argus_voice.wav") -> dict:
    """Record audio to WAV via `sox` if available, else `ffmpeg`."""
    if shutil.which("sox"):
        cmd = ["sox", "-d", "-c", "1", "-r", "16000",
               out_path, "trim", "0", str(seconds)]
    elif shutil.which("ffmpeg"):
        cmd = ["ffmpeg", "-y", "-f", "avfoundation", "-i", ":0",
               "-t", str(seconds), "-ac", "1", "-ar", "16000", out_path]
    else:
        return {"ok": False, "error": "install sox or ffmpeg for recording"}
    try:
        subprocess.run(cmd, capture_output=True, text=True,
                       timeout=seconds + 5)
        if os.path.exists(out_path):
            return {"ok": True, "path": out_path,
                    "size": os.path.getsize(out_path),
                    "seconds": seconds}
        return {"ok": False, "error": "no file produced"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def transcribe(audio_path: str, *, model: str = "base") -> dict:
    """Best-effort STT. Tries: whisper-cpp main, whisper, hermes if available."""
    if not os.path.isfile(audio_path):
        return {"ok": False, "error": "audio file not found"}
    # whisper.cpp
    for cmd_name in ("whisper-cpp", "main"):
        if shutil.which(cmd_name):
            try:
                r = subprocess.run([cmd_name, "-m", model, audio_path,
                                     "--output-txt"],
                                    capture_output=True, text=True, timeout=120)
                return {"ok": r.returncode == 0, "via": cmd_name,
                        "transcript": (r.stdout or "").strip()[-2000:]}
            except Exception as e:
                continue
    # OpenAI whisper Python
    if shutil.which("whisper"):
        try:
            r = subprocess.run(["whisper", audio_path, "--model", model,
                                 "--output_format", "txt"],
                                capture_output=True, text=True, timeout=300)
            return {"ok": r.returncode == 0, "via": "whisper",
                    "transcript": (r.stdout or "").strip()[-2000:]}
        except Exception:
            pass
    return {"ok": False, "error": "no STT backend installed (try: brew install whisper-cpp)"}
