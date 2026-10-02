# Milwaukee Drinks

Every espresso martini and every Spotted Cow pour we can find in the Milwaukee
metro, with what it costs and where to find it. Downtown leads: the Deer
District, the Theater District, Water Street, the Third Ward, Walker's Point
and the rest of downtown come first, and one filter narrows the list to them.

Live at https://tylerherman19.github.io/espresso-martinis/

The site is set like a bar's own menu. Two rooms share one structure and swap
atmosphere when you change the drink — a cocktail lounge for the martinis, a pub
for the Cow. Both are light; the paper, ink, accent and map warmth all move
together, and the grid never does.

## Repo

| Path | What it is |
| --- | --- |
| `index.html`, `styles.css`, `app.js` | The whole site. No build step, no framework. |
| `vendor/` | Leaflet and the two webfonts, served from here. The page makes no third-party request. |
| `DESIGN.md` | The design system — color tokens per room, type scale, spacing, motion. Read it before changing anything visual. |
| `data/martinis.json` | Swept weekly off live ordering platforms. |
| `data/cow.json` | Hand-researched, updated by hand. Every line carries its source and how well it is evidenced. |
| `data/manual.json` | Hand-verified martini spots merged into the sweep. |
| `scripts/sweep.py` | The weekly sweep that rewrites `data/martinis.json`. |
| `tests/` | Tests for the sweep. `python -m unittest discover tests`; CI runs them on every push and pull request, and the sweep runs them before it writes anything. |

The map is Leaflet on OpenStreetMap tiles, warmed with a CSS filter to match the
paper. Rows and pins are two views of one selection: hover either and the other
answers. If Leaflet fails to load the map stands down and the list carries on.

## What counts

A line counts when it is a standalone espresso martini or a standalone Spotted
Cow pour. Bottled liqueur, six-packs, and a chaser tacked onto another drink do
not. Prices are the menu price before tax and tip; a happy-hour number appears
only where the bar posts one for these drinks specifically.

## When a source does not answer

The sweep never trusts silence. If Toast or Clover does not answer, the spots
behind it keep their last reading, with the date it was taken in `seen_at`, and
the run goes red so GitHub emails about it. If a run would still shrink the list
below half of the last one, it writes nothing and fails; `--force` writes anyway
when the drop is real. This exists because on 2026-09-30 Toast started answering
403 and the sweep replaced 98 spots with 2.

## How sure a line is

An espresso martini line is graded by age. A swept line carries `seen_at`, the
day its menu was last read; past 14 days it shows *Menu may be stale*. A
hand-verified line in `data/manual.json` carries `verified_at` and holds for 90
days. The Spotted Cow list is researched by hand and each entry records a
`confidence`:

| `confidence` | On the row | Means |
| --- | --- | --- |
| `menu` | nothing | A current official menu or a posted price backs it. |
| `stale` | *Menu may be stale* | A menu backed it, but that source is old. |
| `reported` | *Not on a menu* | A check-in, review or article put it there; no menu confirms it. |

The **On a menu** filter keeps only the first kind, in both rooms. Each entry's
`notes` field says exactly what the evidence was, and the detail panel shows it.

## What a price is

A row shows the everyday price (`price_cents`), and so do the cover's figures.
The happy-hour price takes the row's place only with the **Happy hour** filter
on, or when it is the only price a bar posts.

## Where a spot sits

`app.js` carries a box per downtown district and reads them in order, so the
named districts win before the Downtown catch-all. Outside those boxes a spot
falls back to its neighborhood — the real one inside the city of Milwaukee, the
municipality everywhere else, because "Lowell Damon Woods" locates nothing and
"Wauwatosa" does.
