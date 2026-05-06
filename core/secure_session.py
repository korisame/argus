"""Encrypted session jars at-rest using macOS Keychain.

The plain browser-harness session jar (cookies + localStorage + IndexedDB)
lives at ~/.browser-harness-pro/sessions/<name>/. Today it's cleartext on
disk. This module wraps it:
  - encrypt: tar+gzip the jar, encrypt with AES-256 using a key in Keychain,
             store the ciphertext at <jar>.enc, delete the cleartext
  - decrypt: read <jar>.enc, decrypt, untar to <jar>/

Key is generated once per (account, jar) pair and stored as a generic
password in the user's login keychain. Survives reboots.
"""
from __future__ import annotations

import base64
import os
import secrets
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Optional

SESSIONS_DIR = Path(os.path.expanduser("~/.browser-harness-pro/sessions"))
KEYCHAIN_SERVICE = "argus-session"


def _have_keychain() -> bool:
    return shutil.which("security") is not None


def _keychain_get(name: str) -> Optional[str]:
    if not _have_keychain():
        return None
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE,
             "-a", name, "-w"],
            capture_output=True, text=True, timeout=4,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return None


def _keychain_set(name: str, value: str) -> bool:
    if not _have_keychain():
        return False
    try:
        # delete existing first (otherwise add fails)
        subprocess.run(
            ["security", "delete-generic-password", "-s", KEYCHAIN_SERVICE,
             "-a", name],
            capture_output=True, timeout=4,
        )
        r = subprocess.run(
            ["security", "add-generic-password", "-s", KEYCHAIN_SERVICE,
             "-a", name, "-w", value, "-T", ""],
            capture_output=True, text=True, timeout=4,
        )
        return r.returncode == 0
    except Exception:
        return False


def _ensure_key(name: str) -> Optional[bytes]:
    k = _keychain_get(name)
    if k:
        try: return base64.b64decode(k)
        except Exception: pass
    raw = secrets.token_bytes(32)
    if _keychain_set(name, base64.b64encode(raw).decode()):
        return raw
    return None


def _aes_encrypt(data: bytes, key: bytes) -> bytes:
    """AES-GCM-256. Returns nonce(12) + ciphertext + tag(16)."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        nonce = secrets.token_bytes(12)
        aes = AESGCM(key)
        ct = aes.encrypt(nonce, data, None)
        return nonce + ct
    except ImportError:
        # Fallback: openssl CLI
        with tempfile.NamedTemporaryFile(delete=False) as f_in, \
             tempfile.NamedTemporaryFile(delete=False) as f_out:
            f_in.write(data); f_in.flush()
            r = subprocess.run(
                ["openssl", "enc", "-aes-256-cbc", "-pbkdf2",
                 "-salt", "-pass", "fd:0",
                 "-in", f_in.name, "-out", f_out.name],
                input=base64.b64encode(key).decode(), text=True,
                capture_output=True, timeout=10,
            )
            if r.returncode != 0:
                raise RuntimeError(f"openssl encrypt failed: {r.stderr}")
            with open(f_out.name, "rb") as fr:
                return b"OPENSSL:" + fr.read()


def _aes_decrypt(blob: bytes, key: bytes) -> bytes:
    if blob.startswith(b"OPENSSL:"):
        with tempfile.NamedTemporaryFile(delete=False) as f_in, \
             tempfile.NamedTemporaryFile(delete=False) as f_out:
            f_in.write(blob[len(b"OPENSSL:"):]); f_in.flush()
            r = subprocess.run(
                ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-d",
                 "-salt", "-pass", "fd:0",
                 "-in", f_in.name, "-out", f_out.name],
                input=base64.b64encode(key).decode(), text=True,
                capture_output=True, timeout=10,
            )
            if r.returncode != 0:
                raise RuntimeError(f"openssl decrypt failed: {r.stderr}")
            with open(f_out.name, "rb") as fr:
                return fr.read()
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce, ct = blob[:12], blob[12:]
    return AESGCM(key).decrypt(nonce, ct, None)


def encrypt_jar(name: str = "default") -> dict:
    jar_dir = SESSIONS_DIR / name
    if not jar_dir.is_dir():
        return {"ok": False, "error": f"no jar at {jar_dir}"}
    key = _ensure_key(name)
    if not key:
        return {"ok": False, "error": "could not get/create keychain key"}
    # tar.gz the jar
    with tempfile.NamedTemporaryFile(suffix=".tgz", delete=False) as tarf:
        with tarfile.open(tarf.name, "w:gz") as t:
            t.add(jar_dir, arcname=name)
        with open(tarf.name, "rb") as fr:
            data = fr.read()
        os.unlink(tarf.name)
    enc = _aes_encrypt(data, key)
    out = jar_dir.parent / f"{name}.enc"
    out.write_bytes(enc)
    # delete cleartext
    shutil.rmtree(jar_dir, ignore_errors=True)
    return {"ok": True, "encrypted_to": str(out), "size": len(enc),
            "cleartext_removed": True}


def decrypt_jar(name: str = "default") -> dict:
    enc_path = SESSIONS_DIR / f"{name}.enc"
    if not enc_path.is_file():
        return {"ok": False, "error": f"no encrypted jar at {enc_path}"}
    key = _keychain_get(name)
    if not key:
        return {"ok": False, "error": "keychain key missing for this jar"}
    raw_key = base64.b64decode(key)
    blob = enc_path.read_bytes()
    try:
        data = _aes_decrypt(blob, raw_key)
    except Exception as e:
        return {"ok": False, "error": f"decrypt failed: {e}"}
    with tempfile.NamedTemporaryFile(suffix=".tgz", delete=False) as f:
        f.write(data); f.flush()
        with tarfile.open(f.name, "r:gz") as t:
            t.extractall(path=SESSIONS_DIR)
        os.unlink(f.name)
    return {"ok": True, "extracted_to": str(SESSIONS_DIR / name)}


def list_jars() -> dict:
    if not SESSIONS_DIR.is_dir():
        return {"plain": [], "encrypted": []}
    plain = sorted(p.name for p in SESSIONS_DIR.iterdir() if p.is_dir())
    enc = sorted(p.stem for p in SESSIONS_DIR.glob("*.enc"))
    return {"plain": plain, "encrypted": enc}
