# Milwaukee Drinks — design system

The reference for this rebuild is a modern consumer ticketing site (light mode,
white chrome on a cool gray page, one saturated interactive color, heavy
geometric display type, generous whitespace, soft-radius cards). We borrowed its
*arrangement* — sticky chrome, a copy-left / art-right hero, a stat band, a
search-and-filter section, then content — and not its skin. The palette is
Milwaukee blue and brass, chosen for this project.

Every color, size, radius and duration used in `styles.css` comes from this file.
If a new component needs a value that is not here, add it here first.

## Color tokens (named by job, never by hue)

| Token | Value | Job |
| --- | --- | --- |
| `--bg` | `#F1F4F8` | Page ground |
| `--surface` | `#FFFFFF` | Cards, chrome, inputs |
| `--surface-sunk` | `#E9EEF5` | Chip rests, table zebra, map frame |
| `--ink` | `#0B1B33` | Headlines, primary text |
| `--ink-2` | `#33455F` | Body copy |
| `--muted` | `#6B7C93` | Labels, meta, captions |
| `--line` | `#DCE3EC` | Hairlines, card borders |
| `--primary` | `#145CC6` | The one interactive color: links, buttons, active state, focus, pins |
| `--primary-strong` | `#0E4098` | Pressed / hover of primary |
| `--primary-soft` | `#E6EDFA` | Primary tint backgrounds (active chip, hero strip) |
| `--brass` | `#9C6F1C` | The one data accent: lowest price and happy-hour pricing **only** |
| `--brass-soft` | `#F6EEDB` | Brass tint, used once per group at most |

Discipline: `--primary` marks anything you can *do*. `--brass` marks a *fact
about money* (a best price, a happy-hour price). Nothing else is ever colored.

## Type

One family: **Plus Jakarta Sans** (400 / 500 / 600 / 800). Numbers use
`font-variant-numeric: tabular-nums` — no monospace anywhere; monospace in a
price list is costume, not information.

| Step | Size / line-height | Weight | Use |
| --- | --- | --- | --- |
| display | `clamp(42px, 7.2vw, 76px)` / 0.98 | 800 | Hero headline |
| h2 | `clamp(28px, 4vw, 42px)` / 1.06 | 800 | Section headings |
| h3 | `20px` / 1.25 | 700 | Card and panel titles |
| lede | `clamp(16px, 1.4vw, 19px)` / 1.55 | 400 | Hero and section subcopy |
| body | `15.5px` / 1.6 | 400 | Prose |
| meta | `13px` / 1.4 | 500 | Row meta, captions |
| label | `11.5px` / 1 · `.09em` · uppercase | 700 | Eyebrows and column labels only |
| price | `18px` / 1 tabular | 700 | Prices in rows |
| price-lg | `28px` / 1 tabular | 800 | Stat band figures |

Tracking: `-0.03em` on display, `-0.02em` on h2, `-0.01em` on h3, 0 elsewhere.

## Space, radius, elevation

- Spacing scale (4px base): `4 8 12 16 24 32 48 64 96 128`. Nothing off-scale.
- Page gutter: `20px` mobile, `32px` ≥720px, `48px` ≥1080px. Max content width `1200px`.
- Radius: `10px` controls, `14px` inputs and chips, `20px` cards and panels, `999px` pills.
- Elevation (ink at low alpha, never gray):
  - rest `0 1px 2px rgba(11,27,51,.06)`
  - raised `0 6px 20px -8px rgba(11,27,51,.16)`
  - overlay `0 24px 60px -20px rgba(11,27,51,.34)`

## Motion

- Durations: `140ms` state, `240ms` reveal, `320ms` panel, `520ms` count-up.
- Easing: `cubic-bezier(.2,.7,.2,1)` for entrances, `cubic-bezier(.4,0,.2,1)` for exits.
- Reveals travel `10px` maximum and stagger `28ms`, capped at 12 items.
- Everything above collapses to zero under `prefers-reduced-motion: reduce`.

## Rules this project does not break

1. No gradients. Flat fills only.
2. No emoji standing in for an icon — icons are drawn as SVG on a 24px grid at 1.75px stroke.
3. No decorative chart, meter or bar without a real number behind it.
4. No color fill behind a word to "highlight" it; color lives on glyphs and on real controls.
5. No slogan band at the bottom. The page ends on the method notes, which are real information.
