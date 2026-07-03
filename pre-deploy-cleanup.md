# Plano de Pré-Deploy, Limpeza e Documentação — pre-deploy-cleanup

Este plano orienta a preparação do JRWhisperLinux para publicação oficial (open source no GitHub). Ele foca na remoção de comentários excessivos do código, refatoração profissional de nomenclatura e atualização de toda a documentação de arquitetura e instalação para a versão v3.1.

## Proposed Changes

### 1. Limpeza de Comentários em `src/dictate`
Removeremos comentários explicativos redundantes, mantendo apenas docstrings essenciais de classes e funções públicas para manter o código limpo, profissional e auto-documentado (seguindo o padrão `@clean-code`).

### 2. Atualização do `README.md`
Atualizar o guia de instalação rápida e uso para refletir:
* Requisitos de sistema do Wayland (`wtype`, `wl-clipboard`) e do isolamento de voz (`ffmpeg` com suporte a `arnndn`).
* Instruções sobre como configurar e rodar o Daemon com o systemd.

### 3. Atualização do `docs/architecture.md` e `docs/changelog.md`
* Registrar todas as decisões da versão v3.1 (suporte Wayland, RNNoise integrado com FFmpeg nice level, e janela deslizante Pango).
* Adicionar licença recomendada (ex: Licença MIT) para a publicação open-source.

---

## Verification Plan

### Automated Tests
* Garantir que todas as suítes de teste em `tests/` executem com sucesso após a remoção de comentários.

### Manual Verification
* Testar a execução do executável `src/dictate` em modo cliente e em modo daemon.
