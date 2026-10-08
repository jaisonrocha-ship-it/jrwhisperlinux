#!/usr/bin/env python3
"""Lançador ~/.local/bin/dictate: acha o repositório movido/renomeado e se corrige; sem ele, avisa."""
import os
import shutil
import subprocess
import sys
import tempfile

LAUNCHER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "dictate-launcher.sh")


def _fake_repo(path):
    """Repositório mínimo: src/dictate imprime onde está e os argumentos."""
    os.makedirs(os.path.join(path, "src", "jrwhisper"))
    open(os.path.join(path, "src", "jrwhisper", "cli.py"), "w").close()
    dictate = os.path.join(path, "src", "dictate")
    with open(dictate, "w") as f:
        f.write('#!/bin/sh\necho "$(dirname "$(dirname "$0")")|$*"\n')
    os.chmod(dictate, 0o755)


def _run(home, *args):
    bin_dir = os.path.join(home, "fakebin")  # notify-send falso: o teste não abre notificação de verdade
    os.makedirs(bin_dir, exist_ok=True)
    with open(os.path.join(bin_dir, "notify-send"), "w") as f:
        f.write(f'#!/bin/sh\necho "$@" > "{home}/notified"\n')
    os.chmod(os.path.join(bin_dir, "notify-send"), 0o755)
    env = {"HOME": home, "PATH": f"{bin_dir}:/usr/bin:/bin"}
    return subprocess.run(["sh", LAUNCHER, *args], env=env, capture_output=True, text=True)


def test_launcher_follows_moved_repo():
    with tempfile.TemporaryDirectory() as home:
        state = os.path.join(home, ".config", "dictate", "repo")
        os.makedirs(os.path.dirname(state))
        old = os.path.join(home, "dev", "jrwhisperlinux")
        _fake_repo(old)
        with open(state, "w") as f:
            f.write(old + "\n")
        r = _run(home, "--status")
        assert r.stdout.strip() == f"{old}|--status", r                  # caminho salvo vale

        new = os.path.join(home, "projetos", "jr-whisper")              # movido e renomeado
        os.makedirs(os.path.dirname(new))
        shutil.move(old, new)
        _fake_repo(os.path.join(home, "dev", ".claude", "worktrees", "x"))  # cópia de trabalho: ignorada
        r = _run(home, "--settings", "ai")
        assert r.returncode == 0 and r.stdout.strip() == f"{new}|--settings ai", r
        assert open(state).read().strip() == new                         # se corrigiu para a próxima vez

        shutil.rmtree(os.path.join(home, "projetos"))
        shutil.rmtree(os.path.join(home, "dev"))
        default = os.path.join(home, ".local", "share", "jrwhisperlinux")  # onde o curl | bash instala
        _fake_repo(default)
        r = _run(home)
        assert r.stdout.strip() == f"{default}|", r

        shutil.rmtree(default)
        r = _run(home)
        assert r.returncode == 1 and "install.sh" in r.stderr
        assert "install.sh" in open(os.path.join(home, "notified")).read()  # avisa na tela, não some calado


def run_tests():
    failed = False
    for fn in (test_launcher_follows_moved_repo,):
        try:
            fn()
            print(f"{fn.__name__}: PASSED")
        except Exception as e:
            print(f"{fn.__name__}: FAILED — {e!r}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_tests())
