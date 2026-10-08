"""Chaves de API no keyring do sistema (Secret Service via secret-tool). Nunca em arquivo."""
import subprocess

ATTRS = ["service", "jrwhisper", "provider"]


def get_key(provider):
    try:
        out = subprocess.run(["secret-tool", "lookup", *ATTRS, provider],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() or None


def set_key(provider, key):
    # stdin: a chave não aparece na linha de comando (ps).
    subprocess.run(["secret-tool", "store", f"--label=JRWhisper {provider} API key", *ATTRS, provider],
                   input=key.strip(), text=True, check=True, timeout=10)


def delete_key(provider):
    subprocess.run(["secret-tool", "clear", *ATTRS, provider], timeout=5)


def masked(key):
    return f"{key[:6]}…{key[-4:]}" if key and len(key) > 12 else ("definida" if key else "não definida")
