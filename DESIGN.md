# Design

## Theme
- **Color Strategy:** Restrained. Tinted dark backgrounds with high-contrast text and a single accent color (#64DCFF) used for listening states and active indicators.
- **Visual Style:** Translucent dark overlay with backdrop blurs where supported, rounded borders, and dynamic animations (opacity fading and wave animations).

## Tokens

### Colors
- `bg-overlay`: `rgba(10, 10, 12, 0.62)` (Translucent dark overlay background)
- `border-overlay`: `none` (Overlay has no hard borders, only inner box shadows for depth)
- `text-primary`: `#FFFFFF` (White text for active lines and final transcripts)
- `text-secondary`: `rgba(255, 255, 255, 0.65)` (Translucent white for status text and previous lines)
- `text-muted`: `rgba(255, 255, 255, 0.40)` (Faded white for older lines)
- `accent-listening`: `#64DCFF` (Cyan color for status label during speech input)
- `accent-transcribing`: `#C8AAFF` (Purple color for transcribing states)
- `accent-success`: `#64FFA0` (Green color for successful transcription/paste)
- `accent-error`: `#FF7864` (Soft red for error states)
- `accent-calibrating`: `#FFC83C` (Warm yellow/amber for calibration)

### Typography
- `font-family`: `'Inter', sans-serif`
- `font-size-status`: `10px` (700 weight, 0.1em letter-spacing for status text)
- `font-size-body`: `13.5px` (400 weight for transcription text)
- `line-height`: `1.5`

### Spacing & Layout
- `padding-overlay`: `16px` (Overall internal padding)
- `margin-overlay`: `18px` (Outer margins for layout bounds)
- `border-radius-overlay`: `16px` (Perfect corner rounding for the overlay balloon)
- `overlay-width`: `450px` (Fixed width to prevent resizing jumps on Cinnamon)

### Components

#### Overlay Balloon
- **Style:** Roundness of `16px` (maximum card rounding allowed per system rules is 16px). Uses a subtle inset box-shadow to simulate light reflection on glass.
- **Child Elements Layout:** Vertically stacked Box (`SiriWaveform` -> `status_label` -> `text_label`). Elements must remain within the overlay margins. No elements should float or position absolutely outside this boundary.
