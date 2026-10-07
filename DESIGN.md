# Design

Aplicativo (overlay, Ajustes, Calibração). O site tem identidade própria (âmbar, Red Hat) descrita no AGENTS.md.

## Princípios
- **Minimalista por padrão, poderoso sob demanda:** o ditado é um atalho e um orbe. Recursos avançados ficam em Ajustes, atrás de um switch mestre por aba (revelação progressiva).
- **Linguagem macOS (modo escuro):** sidebar com ícones em quadrados coloridos, páginas com título grande, grupos arredondados (inset grouped), controles à direita, aplicação instantânea sem Salvar/Cancelar.
- **O visual serve à latência:** nada no overlay bloqueia clique (click-through); animações a 60 fps em Cairo, com "reduzir movimento".

## Tokens (`src/jrwhisper/ui/theme.py`)

### Cores
| Token | Valor | Uso |
|---|---|---|
| `bg` | `#1C1C1E` | Fundo das janelas |
| `sidebar` | `#161618` | Sidebar |
| `card` | `#2C2C2E` | Grupos |
| `control` | `#3A3A3C` | Botões, trilhos, switches desligados |
| `text` / `text2` | `#F5F5F7` / `#98989D` | Texto primário / secundário |
| `hairline` | `rgba(255,255,255,0.07)` | Separador entre linhas |
| Sucesso / Aviso / Perigo | `#30D158` / `#FFC83C` / `#FF6B5E` | Estados |

### Acento (configurável)
Cada acento tem a cor sólida da UI e um gradiente com contraste de matiz (o orbe precisa dele para ter profundidade).

| Acento | UI | Gradiente |
|---|---|---|
| Índigo (padrão) | `#7C6CFF` | `#3D6BFF` → `#D45CFF` |
| Ciano | `#2EC8FF` | `#2FE6FF` → `#3A55FF` |
| Âmbar | `#F59E0B` | `#FFC83A` → `#FF4D3A` |
| Verde | `#30D158` | `#7CF08F` → `#00A8C8` |
| Rosa | `#FF5FA2` | `#FF7AB8` → `#7C5CFF` |
| Personalizado | cor livre | clara → escura da mesma cor |

### Tipografia
Inter variável (OFL, `assets/fonts/`): títulos de página 22/700, linhas 13/400, subtítulos 11 em `text2`, status do overlay 11,5/500.

### Forma
Grupos 10 px · controles 6 px · botões principais em pílula · overlay de texto 16 px.

## Overlay (`ui/visuals.py`, `ui/overlay.py`)
- **Orbe (padrão):** anel com gradiente rotativo e brilho aditivo, miolo escuro sólido, ícone de mic (check ao colar). Ouvindo = acento; transcrevendo = gira rápido e pulsa; colado = verde → ciano; erro = vermelho.
- **Ondas:** pílula com ondas fluidas e núcleo luminoso.
- **Barras:** pílula com 32 bandas de espectro (log) e reflexo.
- Texto em pílula escura que cresce (acima do visual quando o overlay está embaixo); linhas antigas esmaecem. Status em pílula para contraste sobre qualquer fundo.
- Tamanho P/M/G (0,8 / 1 / 1,25), posição embaixo/centro/topo no monitor do mouse.
