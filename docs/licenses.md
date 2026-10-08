# Auditoria de Licenças — JRWhisperLinux

**Data:** 2026-10-08 (revisão: dependências da v4 e IA local)
**Projeto:** MIT
**Conclusão:** o projeto e todas as dependências obrigatórias são software livre. Os modelos de IA local opcionais têm licença própria (ver abaixo).

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
| requests *(apt)* | sistema | Apache 2.0 | Apache-2.0 |
| python-xlib *(apt)* | sistema | LGPL 2.1+ | LGPL-2.1-or-later |

## Interface (sistema)

| Componente | Licença | SPDX |
|------------|---------|------|
| PyGObject (GTK3) | LGPL 2.1+ | LGPL-2.1-or-later |
| Pango | LGPL 2.1 | LGPL-2.1-only |
| Cairo | LGPL 2.1 / MPL 1.1 | LGPL-2.1-only, MPL-1.1 |
| librsvg (ícones vetoriais) | LGPL 2.1+ | LGPL-2.1-or-later |
| AT-SPI (campo em foco) | LGPL 2.1+ | LGPL-2.1-or-later |
| Inter (fonte, embarcada) | SIL OFL 1.1 | OFL-1.1 |
| Lucide (ícones, embutidos) | ISC | ISC |

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
| libsecret-tools (`secret-tool`) | LGPL 2.1+ | LGPL-2.1-or-later |
| dconf | LGPL 2.1+ | LGPL-2.1-or-later |
| Docker Engine *(opcional, IA local)* | Apache 2.0 | Apache-2.0 |
| Ollama *(opcional, imagem `ollama/ollama`)* | MIT | MIT |

## Modelos de Rede Neural

| Modelo | Licença |
|--------|---------|
| Whisper (OpenAI) | MIT |
| RNNoise Models | Domínio Público (não sujeito a copyright) |
| Silero VAD | MIT |

### Modelos de IA local (opcionais, baixados pelo usuário no Ollama)

| Modelo | Licença | Uso |
|--------|---------|-----|
| Qwen2.5 7B (`qwen2.5`) | Apache 2.0 | Reescrita do ditado (1º da fila) |
| Hunyuan MT 1.5 1.8B | Licença comunitária própria da Tencent (não OSI; confira o card do modelo antes de uso comercial) | Tradutor opcional das legendas |

Com NVIDIA NIM ou DeepSeek, o texto vai para a API do serviço, sujeito aos termos dele. Nenhum desses serviços é necessário: sem IA, o ditado funciona 100% local.

## Notas

- Ferramentas GPL (xclip, wl-clipboard, ffmpeg) são dependências externas de sistema. O usuário as instala via gerenciador de pacotes. O projeto não as distribui nem faz link direto com elas.
- Nenhuma dependência obrigatória possui restrições de uso comercial (o Hunyuan MT, opcional, tem licença própria).
- Nenhuma dependência possui patentes ativas que restrinjam o uso.
- Os modelos obrigatórios (Whisper, RNNoise, Silero VAD) são MIT ou domínio público. Os modelos de IA local são opcionais e têm a licença de cada um (tabela acima).

## Metodologia

```bash
# Para cada pacote Python no venv:
~/.local/share/dictation-venv/bin/pip show <pacote> | grep License

# Para cada pacote de sistema:
apt-cache show <pacote> | grep License
dpkg -s <pacote> | grep License
```
