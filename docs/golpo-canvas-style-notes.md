# Golpo Canvas Style Notes

Source page: https://video.golpoai.com/guide/golpo-canvas-styles-guide

Observed videos:

| Style | YouTube ID | Runtime | Key Visual Grammar |
| --- | --- | ---: | --- |
| Chalkboard Black & White | `HjSTQ4kwa0I` | 39s | Black canvas, white chalk only, very sparse top title plus small icon groups. Text and diagrams appear progressively with rough chalk texture. |
| Chalkboard Color | `Am16yCE5RXA` | 24s | Same blackboard grammar, but cyan/yellow accents mark title, arrows, final output and key objects. Still sparse and high contrast. |
| Modern Minimal | `X19QPUjfMTs` | 27s | Warm light grey canvas, thin black line art, one cool accent, large whitespace, small aligned icon clusters. Polished and calm. |
| Technical | `u3Oq_Sx3zsU` | 33s | Deep navy blueprint canvas, pale-blue technical outlines, clustered UI/panel drawings, subtle structured complexity and tiny colored semantic accents. |
| Editorial | `U65SQFA1_6s` | 36s | Warm off-white canvas, bold black ink title, red/orange underline accents, polished collage of papers, media, cards, and object layers. |
| Whiteboard | `MyhDPI9_GJI` | 26s | Off-white board, black marker outlines, blue title/labels, small colored icon fills. Clear educational icon grid with readable spacing. |
| Playful | `fLM7V0kWaxY` | 27s | Cream canvas, multicolor crayon lettering, pastel accents, rounded friendly shapes, playful motion marks and cheerful simple icons. |
| Sharpie | `9KY1pw9ShJs` | 32s | Bright white canvas, thick black marker lettering, real hand visible, bold rough icons, small highlighter accents, raw quick-drawn energy. |

Implementation rules:

- Treat visual style and pen-in-hand as separate layers.
- `video_style` controls canvas material, palette, line quality, density, and composition.
- `pen_style` controls animation feel: `pen`, `fountain_pen`/stylus, `marker`, or `no_hand`.
- Image generation must produce text-free artwork; readable Chinese labels, subtitles, and dynamic callouts remain renderer-controlled.
- Avoid turning every topic into a single whiteboard style. Pick by communication job:
  - complex teaching: Chalkboard B/W, Technical, Whiteboard
  - social/marketing: Chalkboard Color, Playful, Editorial
  - client/investor: Modern Minimal, Editorial
  - raw quick update: Sharpie
  - high craft feel: any style plus pen-in-hand
