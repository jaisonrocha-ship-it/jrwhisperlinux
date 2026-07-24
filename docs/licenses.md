# Auditoria de Licenças — JRWhisperLinux

**Data:** 2026-07-24
**Projeto:** MIT
**Conclusão:** ✅ 100% Open Source. Nenhum componente proprietário.

## Python (pip)

| Pacote | Versão | Licença | SPDX |
|--------|--------|---------|------|
| faster-whisper | latest | MIT | MIT |
| ctranslate2 | latest | MIT | MIT |
| onnxruntime | latest | MIT | MIT |
| numpy | latest | BSD 3-Clause | BSD-3-Clause |
| huggingface-hub | latest | Apache 2.0 | Apache-2.0 |
| PyAV | latest | BSD 3-Clause | BSD-3-Clause |
| tqdm | latest | MIT + MPL 2.0 | MIT, MPL-2.0 |

## Interface (sistema)

| Componente | Licença | SPDX |
|------------|---------|------|
| PyGObject (GTK3) | LGPL 2.1+ | LGPL-2.1-or-later |
| Pango | LGPL 2.1 | LGPL-2.1-only |
| Cairo | LGPL 2.1 / MPL 1.1 | LGPL-2.1-only, MPL-1.1 |

## Sistema (externo, não bundado)

| Ferramenta | Licença | SPDX |
|------------|---------|------|
| xdotool | BSD | BSD-3-Clause |
| wtype | MIT | MIT |
| xclip | GPL 2 | GPL-2.0-only |
| wl-clipboard | GPL 3 | GPL-3.0-only |
| ffmpeg | LGPL/GPL | LGPL-2.1-or-later, GPL-2.0-or-later |
| PulseAudio | LGPL 2.1 | LGPL-2.1-only |
| PipeWire | LGPL 2.1 | LGPL-2.1-only |

## Modelos de Rede Neural

| Modelo | Licença |
|--------|---------|
| Whisper (OpenAI) | MIT |
| RNNoise Models | Domínio Público (não sujeito a copyright) |
| Silero VAD | MIT |

## Notas

- Ferramentas GPL (xclip, wl-clipboard, ffmpeg) são dependências externas de sistema. O usuário as instala via gerenciador de pacotes. O projeto não as distribui nem faz link direto com elas.
- Nenhuma dependência possui restrições de uso comercial.
- Nenhuma dependência possui patentes ativas que restrinjam o uso.
- Todos os modelos de IA são distribuídos sob licenças permissivas ou domínio público.

## Metodologia

```bash
# Para cada pacote Python no venv:
~/.local/share/dictation-venv/bin/pip show <pacote> | grep License

# Para cada pacote de sistema:
apt-cache show <pacote> | grep License
dpkg -s <pacote> | grep License
```
