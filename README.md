# Milwaukee Drinks

Every espresso martini and every Spotted Cow pour we can find in the Milwaukee
metro, with what it costs and where to find it.

Live at https://tylerherman19.github.io/espresso-martinis/

The site is set like a bar's own menu. Two rooms share one structure and swap
atmosphere when you change the drink — a cocktail lounge for the martinis, a pub
for the Cow. Both are light; the paper, ink, accent and map warmth all move
together, and the grid never does.

## Repo

| Path | What it is |
| --- | --- |
| `index.html`, `styles.css`, `app.js` | The whole site. No build step, no framework. |
| `DESIGN.md` | The design system — color tokens per room, type scale, spacing, motion. Read it before changing anything visual. |
| `data/martinis.json`, `data/cow.json` | The index the page renders. |
| `data/manual.json` | Hand-verified spots merged into the sweep. |
| `scripts/sweep.py` | The weekly sweep that rewrites `data/martinis.json`. |

The map is Leaflet on CARTO Positron tiles, warmed with a CSS filter to match the
paper. Rows and pins are two views of one selection: hover either and the other
answers.

## What counts

A line counts when it is a standalone espresso martini or a standalone Spotted
Cow pour. Bottled liqueur, six-packs, and a chaser tacked onto another drink do
not. Prices are the menu price before tax and tip; a happy-hour number appears
only where the bar posts one for these drinks specifically.
