---
title: ATLAS Design Principles
status: locked
last-updated: 2026-04-15
---

# ATLAS Design Principles

These are locked design decisions. Every mockup and every production screen must conform. Do not revisit without a recorded design review session.

---

## 1. Surface treatment — locked

**Grey-on-white. Default theme only.**

| Token | Value | Role |
|---|---|---|
| `--bg-app` | `#F7F8FA` | Page background |
| `--bg-surface` | `#FFFFFF` | Cards, panels, tables |
| `--bg-surface-alt` | `#FBFBFC` | Zebra stripes |
| `--bg-inset` | `#F2F4F7` | Code blocks, inset wells |

The Ivory, Paper, and Warm-white theme variants exist in tokens.css for experimentation but are **not in production scope**. Do not ship alternate themes without a product decision.

---

## 2. Color is functional, never decorative

**Two semantic layers. Nothing else.**

### Layer 1: RAG — signal vocabulary (data signals)

Red / Amber / Green is the primary classification system for every quantitative signal.

| Signal | Use | Tokens |
|---|---|---|
| Green | Outperforming, healthy, within limits | `--rag-green-*` |
| Amber | Watch, borderline, needs attention | `--rag-amber-*` |
| Red | Underperforming, breach, alert | `--rag-red-*` |

**Rules:**
- RAG is always icon + label + color together (never color alone)
- Amber is not "warning decoration" — amber means "this needs a decision"
- The absence of RAG on a data point is also a signal (grey = insufficient data)

### Layer 2: Petrol — chrome and identity (brand only)

`--accent-700: #134F5C` (petrol teal) is used **only** for:
- Navigation active states
- Primary action buttons
- Brand identity marker (the atlas. dot)
- "Your fund" / "your portfolio" identity lines in charts

Petrol **must not** be used as a category color in charts or as decorative fill. If you want "the fund" to be petrol in a chart, that's allowed — it means "this is the entity you're analyzing."

---

## 3. Benchmark comparison — mandatory on all quantitative visuals

**ATLAS is a relative strength intelligence platform. Every quantitative output must show performance relative to benchmark.**

This is the single most important design rule: context without a benchmark is incomplete.

### Three standard benchmark patterns

#### Pattern A: Dual line (line charts, area charts, performance charts)
```
Fund   → solid line, RAG-colored (green if outperforming, red if under)
Benchmark → dashed grey line, --text-tertiary (#8A909C), stroke-dasharray="3 2"
Legend → always rendered below chart: "▬ Fund name · +28.4%  - - Benchmark name · +19.1%"
```

#### Pattern B: Active weight bar (bar charts, sector charts)
```
Bars represent fund weight MINUS benchmark weight (signed delta)
Zero line = benchmark allocation
Green bar = overweight + right call (Brinson contribution positive)
Red bar = overweight + wrong call (or underweight + right call flipped)
Grey bar = negligible contribution
```

#### Pattern C: Reference marker (scatter plots, bubble charts)
```
Benchmark appears as a labelled anchor point (grey filled circle, no RAG color)
Label: "Nifty MC 150" or relevant index name
Positioned at its actual risk/return coordinates
All other dots are colored RAG relative to the benchmark dot's position
```

### Alpha display convention

Every visual that shows fund vs benchmark should also display the alpha (outperformance gap):
- Positive alpha: `+9.3pp α` in `--rag-green-700`
- Negative alpha: `−2.9pp α` in `--rag-red-700`
- Near-zero (< 1pp): `+0.7pp α` in `--rag-amber-700`

### Which benchmark?

| Category | Benchmark |
|---|---|
| Mid cap | Nifty Midcap 150 TRI |
| Small cap | Nifty Smallcap 250 TRI |
| Large cap | Nifty 50 TRI |
| Flexi / multi-cap | Nifty 500 TRI |
| Thematic | Category-specific (label explicitly) |

TRI = Total Return Index (includes reinvested dividends). Never compare against price-only index.

---

## 4. Card sizing — S / M / L only

Three sizes. No exceptions.

| Size | Class | Column span | Use |
|---|---|---|---|
| Small | `.card--sm` | `span-3` or `span-4` | Single KPI, delta pill, narrow stat |
| Medium | `.card--md` | `span-6` | Standard chart, table panel |
| Large | `.card--lg` | `span-12` | Full-width chart, detail view |

Avoid `span-9`, `span-7`, or custom widths. The three-size constraint creates visual rhythm.

---

## 5. Typography constraint

- **Serif** (`--font-serif: Source Serif 4`) for page titles and card headlines only
- **Inter tabular** (`--font-sans` + `font-variant-numeric: tabular-nums`) for all numbers
- **No custom font weights beyond** 400 / 500 / 600 / 700
- **No text decoration, gradient text, or text shadows**

---

## 6. The reading primitive (explainability on every visual)

Every chart or analytical output must have a "reading" component with four zones:

1. **Verdict** — one sentence, plain English, no jargon, RAG-coded
2. **How to read** tab — explains what the chart shows and how to interpret it
3. **Formula** tab — the exact math, with actual values plugged in
4. **Actions** — 2–4 contextual next steps

This is non-negotiable for analytical outputs. Simple KPI metrics can use the compact `verdict-strip` instead.

---

## 7. Motion budget

150ms maximum. No bounces, no springs, no parallax. Transitions exist only to prevent disorientation (e.g., modal entrance), not to delight.

```css
--dur-fast:   100ms;
--dur-normal: 150ms;
--dur-slow:   220ms;  /* modals only */
```

---

## 8. Iconography rules

- Icons are functional (carry information or indicate action), never ornamental
- Every icon appears alongside text or a tooltip — never icon-only in data context
- Icon set: inline SVG, 20×20 viewport, 1.8px stroke, `currentColor`

---

## Reference implementations

All patterns are showcased in `frontend/mockups/styleguide.html`.
Live preview: `python3 -u frontend/mockups/_devserver.py` (port 8765).
