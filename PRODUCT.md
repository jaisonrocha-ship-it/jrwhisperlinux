# Product

## Register

product

## Users
- **Target User:** JR (Brazilian Portuguese speaker, power user, desktop developer/editor on Linux Mint 22.3 Cinnamon X11).
- **User Context:** Workstation with NVIDIA RTX 4060 GPU, Yeti GX mic. Uses voice dictation to quickly write text, documentation, emails, and code.
- **Job to be Done:** Dictate text naturally in PT-BR with zero-latency visual feedback, getting immediate clipboard-pasted text that requires no manual fixing of punctuation or spacing.

## Product Purpose
- Provides a macOS-WhisperFlow-style voice dictation interface on Linux X11/Wayland.
- Reduces transcription latency to absolute zero by running a background Whisper daemon pre-loaded on CUDA.
- Displays a beautiful, translucent overlays with real-time waveform visualization during capture.

## Brand Personality
- **Voice:** Reliable, professional, developer-focused, distraction-free.
- **Style:** Premium, polished, minimalist. Clean dark mode aesthetics with HSL/RGB tailored accents.
- **Emotional Goals:** Confidence, fluidity, flow state.

## Anti-references
- Clunky, high-opacity window boxes with window title bars, borders, or generic Linux GTK grey colors.
- Overflowing text, visual lag, or layout shifts when lines wrap.
- Intrusive icons that float outside of window boundaries or cut off elements (like floating outside the rounded border of the overlay box).

## Design Principles
- **Aesthetic Serves Performance:** Latency must be visually hidden or minimized.
- **Perfect Spacing and Alignment:** Every element must fit within the translucent rounded modal bounds. Nothing overflows or cuts off.
- **Discrete & Subtle Elements:** Icons, status text, and indicators should not fight for attention; they should support the user's flow state quietly.

## Accessibility & Inclusion
- Clear typography (Inter font family, balanced font weights).
- High-contrast text on dark translucent backgrounds.
- Consideration for keyboard accessibility (global shortcut Super+Shift+V triggers and closes the recording cleanly).
