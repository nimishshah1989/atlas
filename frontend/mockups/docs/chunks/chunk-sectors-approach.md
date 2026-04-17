---
chunk: pulse-sectors
project: ATLAS
date: 2026-04-17
status: success
---

# Approach: pulse-sectors.html

## What we're building
A static HTML mockup of the India Sector Compass page for ATLAS.
No backend calls — this is a reference design for React developers.

## Design system reuse
- Copy nav/sidebar/topbar exactly from pulse-breadth.html
- Reuse: regime-banner, ss-strip, sec-hd, sim-trigger CSS patterns verbatim
- Add new CSS classes for: RRG SVG layout, sector table, four-factor grid, conviction chips, Gold RS badges

## Key sections
1. Page header + crumb
2. Regime banner (amber/correction, 17 days) — copy from breadth
3. Signal strip (3 cards) — Leading/Breadth Improving/Lagging
4. RRG SVG (640x520, 4 quadrants, 10 sectors as labelled dots)
5. Sector comparison table (11 columns, 10 rows)
6. Four-factor convergence panel (4×10 grid with RAG dots)
7. Rotation narrative (serif italic headline + 3 paragraphs)
8. Simulation trigger card (petrol border)

## RRG coordinate mapping
Center at SVG (320, 260). Scale: 1 unit = 90px x, 100px y.
x axis is horizontal at y=260, y axis vertical at x=320.
Positive x (RS score) goes right, positive y (momentum) goes up.
dot px = 320 + (rs_score * 90)
dot py = 260 - (rs_momentum * 100)

## Edge cases
- Labels must not overlap — nudge positions manually in SVG
- Dot sizes reflect magnitude (r=7 to r=16)
- Quadrant tints: very subtle (opacity 0.06-0.08) to not obscure dots/labels

## Expected output
Single self-contained HTML ~1100 lines. No external dependencies except
the three linked CSS files (tokens.css, base.css, components.css).
