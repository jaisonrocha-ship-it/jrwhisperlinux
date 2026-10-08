# Configuração — JRWhisperLinux

Tudo fica em `~/.config/dictate/config.json`. Os Ajustes (`dictate -s`) gravam cada mudança na hora (escrita atômica, com 350 ms de espera para agrupar mudanças seguidas). Chaves ausentes usam o padrão de `DEFAULT_CONFIG` em `src/jrwhisper/config.py`. A mescla é rasa: um objeto no seu arquivo (ex.: `word_overrides`) substitui o padrão inteiro. `dictate --config` mostra o resultado efetivo.

Se o arquivo estiver corrompido, o app abre com os padrões e registra o erro no log.

As chaves de API **não** ficam aqui: ficam no chaveiro do sistema (`secret-tool lookup service jrwhisper provider nvidia`, idem `deepseek`).

---

## Reconhecimento

| Chave | Padrão | Ajustes | O que faz |
|---|---|---|---|
| `model` | `"medium"` | Reconhecimento → Modelo Whisper | Modelo do faster-whisper (`base`, `medium`, `large-v3`, `large-v3-turbo`…). Trocar vale no próximo ditado; o serviço recarrega sozinho. |
| `language` | `"pt"` | Geral → Idioma | `pt`, `en` ou `auto`. |
| `auto_languages` | `["pt", "en"]` | — | Com `auto`, o idioma é escolhido só entre estes (livre, o Whisper chuta outro idioma em trechos curtos). |
| `initial_prompt` | termos de logística | Reconhecimento → Vocabulário | Vocabulário que o Whisper deve reconhecer (nomes, siglas, jargão), separado por vírgula. As correções aprendidas também entram aqui (até 60 termos). |
| `no_speech_threshold` | `0.6` | Avançado → Sem fala acima de | Segmento com probabilidade de "sem fala" acima disso é descartado. |
| `log_prob_threshold` | `-1.0` | Avançado → Log-prob mínimo | Confiança mínima de um segmento. |
| `compression_ratio_threshold` | `2.4` | Avançado → Taxa de compressão | Texto repetitivo demais (alucinação em loop) é descartado. |
| `gpu_min_vram_mb` | `2500` | Avançado → VRAM livre mínima | Abaixo disso, a transcrição local de reserva roda na CPU. |

## Captura e detecção de fala

| Chave | Padrão | Ajustes | O que faz |
|---|---|---|---|
| `mic_device` | `"@DEFAULT_SOURCE@"` | Microfone → Entrada | Fonte do PulseAudio/PipeWire, ou `@DEFAULT_MONITOR@` para o som do computador. Desconectado: usa o padrão do sistema e avisa. |
| `sample_rate` | `16000` | — | Taxa de captura (o Whisper usa 16 kHz). |
| `silence_threshold` | `0` | Avançado → Limite manual | Limiar fixo de fala (RMS). `0` usa a calibração do mic ou mede o ruído a cada ditado. |
| `silence_duration` | `2.5` | Reconhecimento → Pausa para encerrar | Segundos de silêncio que encerram o ditado. |
| `listen_timeout` | `15` | Reconhecimento → Esperar fala por | Sem fala neste tempo, o ditado fecha. |
| `max_duration` | `60` | Reconhecimento → Duração máxima | Limite de um ditado (e do som do computador), em segundos. |
| `mic_calibrations` | `{}` | Microfone → Calibração | Calibração por mic: limiar, níveis medidos, data e, no Yeti GX, o ganho de hardware. Gravada pela calibração; ganho do Yeti diferente em mais de 5 invalida. |
| `noise_suppression` | `true` | Microfone → Supressão de ruído | RNNoise antes da transcrição (`~/.config/dictate/bd.rnnn`). |
| `pause_media` | `true` | Microfone → Pausar música e vídeos | Pausa o que estiver tocando (MPRIS) e retoma depois. |
| `audio_ducking` | `true` | Microfone → Abaixar o som ao ditar | Abaixa o volume do sistema durante o ditado. |
| `ducking_volume` | `0.20` | Microfone → Volume durante o ditado | Volume (0–1) enquanto dita. |

## Texto

| Chave | Padrão | Ajustes | O que faz |
|---|---|---|---|
| `enable_formatting` | `true` | Texto → Formatação automática | Maiúsculas, espaços e ponto final. |
| `remove_fillers` | `true` | Texto → Remover hesitações | Tira "hmm", "ahn", "éh", "uh". |
| `voice_commands` | `true` | Texto → Comandos de voz | "vírgula", "ponto final", "nova linha", "novo parágrafo"… |
| `word_overrides` | marcas de logística | Texto → Dicionário | Palavra ouvida (minúscula) → palavra escrita. |
| `snippets` | `{}` | Texto → Atalhos de texto | Gatilho falado → texto (aceita várias linhas). Entra depois da IA, exatamente como escrito. |
| `learn_corrections` | `true` | Texto → Aprender com as correções | Palavra corrigida na revisão vira regra do dicionário ao colar. |
| `learn_counts` | `{}` | — | Correções de palavra comum esperando a 2ª ocorrência (preenchido sozinho). |
| `lexicon_enabled` | `true` | Texto → Usar o léxico | Léxico de logística: vocabulário do Whisper, pistas e traduções para a IA. |
| `lexicon_note` | `""` | Texto → Nota | Caminho da nota "Léxico de logística.md". |
| `lexicon_glossary` | `"~/glossario-logistica/data.json"` | — | Glossário de origem. |
| `lexicon_books` | `""` | — | Pasta de livros em `.md` (só os de porto, comex e supply chain contam). |

## Aparência

| Chave | Padrão | Ajustes | O que faz |
|---|---|---|---|
| `overlay_style` | `"orb"` | Aparência → Estilo | `orb`, `waves` ou `bars`. |
| `accent` | `"indigo"` | Aparência → Cor de destaque | `indigo`, `cyan`, `amber`, `green`, `pink` ou `custom`. |
| `accent_custom` | `null` | Aparência → Cor de destaque | Cor hexadecimal quando `accent` é `custom`. |
| `overlay_size` | `"m"` | Aparência → Tamanho | `s`, `m` ou `l`. |
| `overlay_position` | `"bottom"` | Aparência → Posição | `bottom`, `center` ou `top` (no monitor onde está o mouse). |
| `overlay_glow` | `0.8` | Aparência → Brilho | Intensidade do brilho do visual (0–1). |
| `overlay_show_text` | `true` | Aparência → Mostrar texto | Mostra o texto parcial durante o ditado. |
| `reduce_motion` | `false` | Aparência → Reduzir movimento | Sem rotação, ondulação, pontinhos animados nem faixa de luz. |
| `sounds` | `false` | Geral → Sons de início e fim | Toque discreto ao começar a ouvir e ao colar. |

## Legendas ao vivo

| Chave | Padrão | Ajustes | O que faz |
|---|---|---|---|
| `caption_language` | `"pt"` | Reconhecimento → Legendar em | Idioma de destino (`pt`, `en`, `es`; `""` mantém o original). |
| `caption_translator` | `"auto"` | Reconhecimento → Tradutor | `auto` (DeepSeek → NVIDIA → Ollama, a 1ª com chave), `deepseek`, `nvidia`, `ollama` ou `hymt` (Hunyuan MT local). |
| `caption_lines` | `8` | Reconhecimento → Linhas na tela | Altura do cartão das legendas. |
| `caption_lens` | `true` | Reconhecimento → Frase em foco | A frase mais nova fica maior e parada; as anteriores menores. Desligado: texto corrido. |
| `caption_lens_zoom` | `1.5` | Reconhecimento → Aumento | Tamanho da frase em foco (1,1–2×). |
| `caption_lens_pos` | `"center"` | Reconhecimento → Posição do foco | `top`, `center` ou `bottom`. |

## Inteligência

| Chave | Padrão | Ajustes | O que faz |
|---|---|---|---|
| `ai_enabled` | `false` | Inteligência → Reescrita com IA | Liga a revisão com IA. |
| `ai_chain` | `["ollama", "nvidia", "deepseek"]` | Inteligência → Ordem | Fila de provedores, tentados em ordem (3 s cada; a última leva o resto do tempo). |
| `ai_provider` | `"nvidia"` | — | Provedor único quando não há fila. |
| `ai_timeout` | `8.0` | — | Tempo total da reescrita, em segundos. |
| `ai_ollama_url` | `"http://localhost:11435"` | Inteligência → Endereço do Ollama | O Ollama próprio do ditado (contêiner `jrwhisper-ollama`). |
| `ai_ollama_model` | `"qwen2.5"` | Inteligência → Modelo local | Modelo no Ollama. Fica carregado 30 min após o último uso. |
| `ai_model` | `"nvidia/nemotron-3-super-120b-a12b"` | Inteligência → Modelo da NVIDIA | Modelo da NVIDIA NIM (lista verificada em `ai.RECOMMENDED`). |
| `ai_deepseek_model` | `"deepseek-flash"` | Inteligência → Modelo da DeepSeek | `deepseek-flash` (rápido, sem raciocínio) ou `deepseek-v4-pro`. |
| `ai_modes` | 5 modos | Inteligência → Modos | Lista de `{id, name, enabled, prompt}`. Os números 2–9 da revisão seguem esta ordem. |
| `ai_default_mode` | `""` | Inteligência → Modo padrão | Modo usado quando nenhum outro foi pedido (`""` = Original). |
| `ai_voice_prefix` | `true` | Inteligência → Ativar por voz | "modo e-mail, …" no início escolhe o modo. |
| `context_enabled` | `true` | Inteligência → Usar o campo em foco | App, janela, rótulo e seleção recente vão como contexto para a IA. |
| `style_enabled` | `true` | Inteligência → Usar meu estilo nos e-mails | Os modos de e-mail seguem a nota de estilo e suas últimas correções. |
| `style_note` | `""` | Inteligência → Nota | Caminho de "Meu estilo de escrita.md". |
| `style_sources` | `[]` | Inteligência → Fontes do estilo | Pastas do vault: `{path, filter: "sent" \| "whole", subdirs, enabled}`. |

## Aplicativos

| Chave | Padrão | Ajustes | O que faz |
|---|---|---|---|
| `profiles_enabled` | `false` | Aplicativos → Perfis por aplicativo | Liga as regras por janela. |
| `profiles` | Terminais, Editores, Chat, E-mail | Aplicativos → Perfis | Lista; o 1º cujo `match` (classes separadas por `\|`) casa com a janela ativa vale. |

Campos de um perfil:

| Campo | O que faz |
|---|---|
| `match` | Classes de janela, ex.: `kitty\|guake` |
| `name` | Nome exibido |
| `paste` | `ctrl+v`, `ctrl+shift+v` (terminais) ou `type` (digita) |
| `formatting` | Formatação automática neste app |
| `final_period` | Ponto final no fim |
| `capitalize` | Maiúscula no início |
| `ai_mode` | Modo de IA deste app (`""` = o padrão) |
| `send_key` | Tecla de "Colar e enviar" (`Return` por padrão; `ctrl+Return` no e-mail) |

## Histórico e Obsidian

| Chave | Padrão | Ajustes | O que faz |
|---|---|---|---|
| `history_enabled` | `false` | Histórico → Guardar histórico | Guarda cada ditado em `~/.local/share/dictate/history.jsonl`. |
| `history_retention_days` | `30` | Histórico → Manter por | Dias de retenção (`0` = sempre). |
| `keep_audio` | `true` | Histórico → Guardar o áudio | Cópia em Opus de cada ditado, apagada junto com a entrada. |
| `obsidian_enabled` | `false` | Histórico → Copiar ditados para o Obsidian | Uma nota por dia no vault. |
| `obsidian_dir` | `""` | Histórico → Pasta | Pasta das notas `AAAA-MM-DD.md`. |

## Mãos livres

| Chave | Padrão | Ajustes | O que faz |
|---|---|---|---|
| `ptt_enabled` | `false` | Mãos livres → Push-to-talk | Segure o atalho para falar e solte para transcrever (X11). |
| `handsfree_enabled` | `false` | Mãos livres → Mãos livres | Depois de colar, volta a ouvir. |
| `handsfree_idle_secs` | `20` | Mãos livres → Encerrar após | Segundos sem fala que encerram o modo contínuo. |
| `handsfree_stop_phrase` | `"parar ditado"` | Mãos livres → Frase de parada | Frase que encerra. |

---

## Atalhos globais

Os atalhos não ficam no `config.json`: são atalhos personalizados do desktop (dconf, `/org/cinnamon/desktop/keybindings/custom-keybindings/`), que os Ajustes leem e gravam. Cada um aponta para `~/.local/bin/dictate` com um argumento (`--system`, `--captions`, `--history`, `--mode <id>`).
