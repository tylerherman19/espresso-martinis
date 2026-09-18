# Milwaukee Drinks — design system

The site is set like a bar's own menu, not like a web app. Two rooms share one
structure and swap atmosphere when you change the drink:

- **Espresso Martinis** — a hotel cocktail lounge in daylight. Warm ivory paper,
  espresso ink, brass.
- **Spotted Cow** — a good pub in the afternoon. Cream paper, oak ink, amber.

Both are light. The swap is a real change of room — paper, ink, accent, the map's
own warmth and the ornament all move together over 600ms — but the grid, the type
scale and the spacing never move. That is what keeps it feeling like one place.

Every value used in `styles.css` is below. A component that needs a value not
listed here adds it here first.

## Color tokens

Named by job. Each theme carries exactly one accent, and the accent is only ever
used for a fact about money — a price under the median, a happy-hour price — or
for the one control that is currently active.

| Token | Martini | Spotted Cow | Job |
| --- | --- | --- | --- |
| `--paper` | `#F6F2EC` | `#F5F1E6` | The page |
| `--paper-lift` | `#FCFAF6` | `#FBF8F0` | Raised surfaces: bar, panel, field |
| `--ink` | `#17120F` | `#1B1710` | Names, figures, headlines |
| `--ink-2` | `#4A403A` | `#4C443A` | Body copy |
| `--muted` | `#746A62` | `#746B5F` | Meta, labels, captions (4.8:1 on paper) |
| `--line` | `#E4DBD0` | `#E3DACA` | Hairlines |
| `--accent` | `#9A7328` brass | `#A15A20` amber | Rules, marks, active control fills |
| `--accent-ink` | `#6E5119` | `#7A4315` | The accent as *text* — darker, ≥7:1 |
| `--accent-soft` | `#EFE6D3` | `#F2E5D6` | The one tint, used behind nothing but a control |
| `--tile-warm` | `sepia(.10) saturate(.9) brightness(1.02) contrast(1.02)` | `sepia(.16) saturate(.92) brightness(1.02) contrast(1.02)` | Filter that warms the map to match the paper |

## Type

Two faces from one family pairing: **Instrument Serif** (400, italic) for display
and for the name of every spot, **Instrument Sans** (400/500/600) for everything
functional. Prices use `font-variant-numeric: tabular-nums`. No monospace.

Setting names in serif and prices in sans is how a printed menu is set, and it is
what makes a 96-row list read as a list of places rather than a database table.

| Step | Size / line-height | Face | Use |
| --- | --- | --- | --- |
| cover | `clamp(46px, 9vw, 104px)` / 0.96 · `-.02em` | Serif 400 | The drink name on the cover |
| section | `clamp(26px, 3vw, 34px)` / 1.1 · `-.01em` | Serif 400 | Footer and panel headings |
| chapter | `11.5px` / 1 · `.16em` · caps | Sans 600 | Neighborhood headings |
| name | `19px` / 1.3 · `-.005em` | Serif 400 | A spot's name |
| price | `17px` / 1 tabular | Sans 600 | Prices in rows |
| figure | `clamp(26px,3vw,34px)` / 1 tabular | Sans 500 | Index numbers on the cover |
| body | `15px` / 1.65 | Sans 400 | Prose |
| meta | `13px` / 1.45 | Sans 400 | Row meta, captions |
| label | `11px` / 1 · `.14em` · caps | Sans 600 | Eyebrows, column labels |
| tag | `11px` / 1 · `.1em` · caps | Sans 600 | The one badge on a row |

Both faces are served from `vendor/fonts/`. Instrument Sans is variable, so one
file covers 400 through 600 and the page fetches it once.

## Space, edge, depth

- Spacing scale (4px base): `4 8 12 16 20 24 32 40 56 72 96 128`.
- Page gutter `20px`, `36px` ≥760px, `56px` ≥1200px. List column caps at `760px`.
- Corners stay close to sharp — paper, not plastic: `3px` on fields and marks,
  `6px` on panels, `999px` on the drink switch alone.
- Depth is almost absent. One shadow, `0 18px 50px -24px rgba(23,18,15,.28)`, and
  only on things that genuinely float: the detail panel and the map's own chrome.
  Everything else separates with a hairline.

## Motion

- `120ms` for a control's own state, `240ms` for a list change, `420ms` for the
  detail panel, `600ms` for the room swap, `700ms` for the ornament drawing itself.
- Easing `cubic-bezier(.22,.68,.24,1)` in, `cubic-bezier(.4,0,.24,1)` out.
- Reveals travel `8px`, never more, and stagger `26ms` to a cap of ten.
- Under `prefers-reduced-motion: reduce` every duration collapses to ~0 and the
  ornament simply appears drawn.

## Rules this project does not break

1. No gradient anywhere except the single scrim behind the detail panel.
2. Icons are drawn on a 24px grid at 1.5px stroke. No emoji.
3. Nothing is colored that is not a price fact or an active control. A caveat
   about how well a line is evidenced is not a price fact: it stays `--muted`
   at weight 500, so the accent keeps meaning money.
4. No card grid. Rows are ruled lines on paper, as on a menu.
5. No number appears that the sweep or a recorded hand-check did not produce.
6. Nothing the page needs is fetched from a third party. Leaflet and the fonts
   live in `vendor/`, and the map is the only thing allowed to fail — when it
   does, `body.no-map` takes the column and the Map button away rather than
   leaving a dead panel.
