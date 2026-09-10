# Milwaukee Drinks

What an espresso martini or a Spotted Cow actually costs, bar by bar, across the
Milwaukee metro. Prices come off live menus every week; the ones a script cannot
reach are hand-checked.

Live at https://tylerherman19.github.io/espresso-martinis/

## Repo

| Path | What it is |
| --- | --- |
| `index.html`, `styles.css`, `app.js` | The whole site. No build step, no framework. |
| `DESIGN.md` | The design system — color tokens, type scale, spacing, motion. Read this before changing anything visual. |
| `data/martinis.json`, `data/cow.json` | The index the page renders. |
| `data/manual.json` | Hand-verified spots merged into the sweep. |
| `scripts/sweep.py` | The weekly sweep that rewrites `data/martinis.json`. |

The map is Leaflet with OpenStreetMap tiles and clustered price pins.
