# Plano de Polimento e Performance — polish-performance

Este plano define a estratégia para otimizar o tempo de resposta, limitar o overlay de texto em 3 linhas deslizantes com fading de opacidade e reduzir a histerese de silêncio do JRWhisperLinux.

## Socratic Gate (Alinhamento Concluído)

1. **Fluidez Visual**: O overlay de texto será limitado a **exatamente 3 linhas** fixas usando marcação Pango (`Gtk.Label.set_markup`):
   * Linha 1 (antiga): Opacidade `0.25`
   * Linha 2 (média): Opacidade `0.60`
   * Linha 3 (ativa): Opacidade `0.95` (ou `#FFFFFF` se final, com itálico se parcial)
   * Altura estável para evitar deformação do modal.
2. **Histerese de Silêncio**: Reduzida de `2.5s` para `1.7s` (`silence_duration: 1.7`).
3. **FFmpeg Nice Level**: Adicionado `nice -n 19` ao subprocesso do FFmpeg para priorizar recursos de CPU.

---

## Proposed Changes

### [MODIFY] [dictate](file:///home/brutaldev/dev/jrwhisperlinux/src/dictate)

* **Adição de `wrap_text_to_lines`**:
  ```python
  def wrap_text_to_lines(text, max_chars=45):
      paragraphs = text.split('\n')
      lines = []
      for para in paragraphs:
          if not para:
              lines.append("")
              continue
          words = para.split()
          current_line = []
          current_length = 0
          for word in words:
              addition = len(word) + (1 if current_line else 0)
              if current_length + addition <= max_chars:
                  current_line.append(word)
                  current_length += addition
              else:
                  if current_line:
                      lines.append(" ".join(current_line))
                  current_line = [word]
                  current_length = len(word)
          if current_line:
              lines.append(" ".join(current_line))
      return lines
  ```

* **Atualização de `WhisperFlowOverlay.update_text`**:
  Usa Pango markup para pintar as 3 últimas linhas com opacidades deslizantes.

* **Atualização de `DEFAULT_CONFIG` e `config.json`**:
  Ajusta `silence_duration` para `1.7`.

* **Atualização de `_denoise_file`**:
  Adiciona `nice -n 19` antes do comando do FFmpeg.

---

## Verification Plan

### Manual Verification
* Testar o ditado de textos longos e curtos para verificar se o overlay não se deforma e o fading de 3 linhas funciona.
* Testar a parada rápida (1.7s de silêncio).
