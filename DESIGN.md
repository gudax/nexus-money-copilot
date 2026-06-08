# DESIGN.md — NEXUS "Verified" design system

> One shared visual language for both Google AI Agents Challenge entries:
> **NEXUS Money Copilot** (Track 1) and **Sentinel Mesh** (Track 2).
> v3 (2026-06-08) replaces every prior look — the cream/serif "passbook" of
> Money Copilot and the beige "Examiner's Desk" working-papers of Sentinel Mesh.
> Both read as generic AI-generated entries (one editorial-beige, one dark-purple).
> v3 is a **bright AI-lab** language (Claude/Mistral family): warm-white canvas,
> clean humanist sans, generous space, one warm accent, and crisp semantic
> verdict pills that ARE the product (verified / blocked).

## Hard rules

1. **English only.** No Korean on any rendered surface (UI, film on-screen text,
   SVGs, captions). Product copy, labels, probes, stamps — all English.
   The Korean-language production line may be *described* in prose, never shown.
2. **No beige, no paper grain, no ledger margin rule, no serif display, no rubber
   stamps rotated like ink.** Those are the rejected v1/v2 systems. Delete them.
3. **No generic AI purple/indigo gradient hero.** The accent is a warm clay, used
   sparingly. Color carries meaning (verified=green, blocked=red), not decoration.

## Tokens (copy verbatim)

```css
:root{
  /* canvas — warm white, NOT beige */
  --bg:#faf9f7; --surface:#ffffff; --surface-sunken:#f3f1ec;
  --border:#e8e4dc; --border-strong:#d6d0c4;
  /* ink */
  --ink:#1c1b18; --ink-2:#565049; --ink-3:#8f897e;
  /* warm clay accent — brand + interactive only */
  --accent:#cc5a36; --accent-ink:#9e4527; --accent-bg:#fbece4;
  /* semantic verdicts — the product itself */
  --ok:#117a4d; --ok-bg:#e6f4ec; --ok-border:#bfe3cd;
  --no:#c43d2e; --no-bg:#fcebe8; --no-border:#f2c7bf;
  --info:#2f6db0; --info-bg:#e9f1fa;
  /* type */
  --sans:"Inter",system-ui,-apple-system,"Segoe UI",sans-serif;
  --mono:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  /* shape */
  --r-sm:8px; --r:12px; --r-lg:16px; --r-pill:999px;
  --sh-sm:0 1px 2px rgba(28,27,24,.06);
  --sh:0 4px 16px -4px rgba(28,27,24,.10);
  --sh-lg:0 16px 48px -12px rgba(28,27,24,.18);
}
```

Fonts via Google Fonts:
```
https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap
```

## Type scale

- Display: Inter 700/800, `clamp(32px,5vw,56px)`, `letter-spacing:-.02em`, line 1.08.
- Subhead: Inter 600, 20–24px, `-.01em`.
- Lead / body: Inter 400–500, 15–17px, line 1.6, color `--ink-2` for body, `--ink` for emphasis.
- Mono meta/labels: JetBrains Mono 500, 12–13px, `letter-spacing:.04em`, often UPPERCASE for section labels in `--ink-3`.
- Tabular numbers: always mono, `font-variant-numeric:tabular-nums`.

## Signature components (use these patterns everywhere)

**Brand lockup** — tight ink wordmark + product name + live dot:
```html
<div class="brand">
  <span class="mark">NEXUS</span><span class="prod">Money Copilot</span>
  <span class="live">● LIVE · LMX exchange</span>
</div>
```
```css
.brand{display:flex;align-items:baseline;gap:10px;font-family:var(--sans)}
.brand .mark{font-weight:800;letter-spacing:-.03em;color:var(--ink)}
.brand .prod{font-weight:500;color:var(--ink-2)}
.brand .live{margin-left:auto;font-family:var(--mono);font-size:12px;color:var(--ok)}
.brand .live::first-letter{color:var(--ok)} /* dot */
```

**Verdict pill** — clean, confident, slightly tactile; NOT a rotated rubber stamp:
```css
.verdict{display:inline-flex;align-items:center;gap:7px;font-family:var(--mono);
  font-weight:600;font-size:12.5px;letter-spacing:.03em;padding:5px 12px;
  border-radius:var(--r-pill);border:1px solid;line-height:1}
.verdict.ok{color:var(--ok);background:var(--ok-bg);border-color:var(--ok-border)}
.verdict.no{color:var(--no);background:var(--no-bg);border-color:var(--no-border)}
/* text: "✓ Verified"  /  "✕ Blocked" */
```
For the **film**, the pill may use a one-shot scale-overshoot entrance
(`transform:scale(1.6)→1`, 0.4s `cubic-bezier(.2,1.4,.4,1)`) — energetic, not rotated.

**Answer card** — white surface, soft border, audit footer:
```css
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);
  box-shadow:var(--sh-sm);padding:20px 22px}
.card .audit{margin-top:14px;padding-top:12px;border-top:1px solid var(--border);
  display:flex;align-items:center;gap:14px;font-family:var(--mono);font-size:12px;color:var(--ink-3)}
```
Audit footer pattern: `[verdict pill]  ·  3 numbers checked  ·  markets agent  ·  6.6s`

**Data row** — label left (mono, ink-3), value right (mono, tabular, ink):
```css
.row{display:flex;justify-content:space-between;gap:16px;padding:7px 0;
  border-bottom:1px solid var(--border);font-family:var(--mono);font-size:13px}
.row .v{color:var(--ink);font-variant-numeric:tabular-nums;font-weight:500}
```

**Primary button** (clay), **chip** (suggested probe):
```css
.btn{background:var(--accent);color:#fff;border:0;border-radius:var(--r);
  font-family:var(--sans);font-weight:600;font-size:15px;padding:11px 20px;cursor:pointer}
.btn:hover{background:var(--accent-ink)}
.chip{font-family:var(--sans);font-size:14px;border:1px solid var(--border-strong);
  background:var(--surface);border-radius:var(--r-pill);padding:8px 15px;cursor:pointer;color:var(--ink-2)}
.chip:hover{border-color:var(--accent);color:var(--accent)}
```

**Architecture diagram** — white nodes, ink hairline borders, mono labels; the
**Answer Auditor / verification gate is the hero**, outlined in clay (`--accent`),
everything else neutral ink. Connectors: 2px `--border-strong`, the gate's edges
clay. JSON snippets in mono `--info`. No drop-shadow offset blocks (that was v2).

## Surfaces to apply this to

**Track 1 — Money Copilot** (`/Users/kei/projects/nexus-money-copilot`)
| Surface | File |
|---|---|
| Live demo UI | `service/static/index.html` |
| Sample portfolio (vision demo input) | `assets/sample-portfolio.html` |
| Architecture (Devpost gallery) | `assets/architecture.svg` |
| Film (1920×1080) | `film/film.html` |

**Track 2 — Sentinel Mesh** (`/Users/kei/projects/sentinel-mesh`)
| Surface | File |
|---|---|
| Dashboard | `dashboard/index.html` |
| Live playground | `playground/static/index.html` |
| Architecture | `dashboard/architecture.svg` |
| Film (1920×1080) | `film/film.html` |

## Standalone-SVG gotcha

Inside a standalone `.svg` (architecture diagrams used as Devpost images), web
fonts do not load and CSS `feTurbulence` overlays artifact. Use a system stack
inside SVG only: `font-family:"Helvetica Neue",Arial,sans-serif` for labels and
`Menlo,monospace` for data. Keep the same palette tokens (hardcode the hex).
Multi-segment `<path d>` connectors need `fill="none"`.

## Per-product accent note

The system is identical across both tracks (one NEXUS family). The only product
tell is the brand lockup (`Money Copilot` vs `Sentinel Mesh`) and the live-source
label (`LMX exchange` vs `verified-memory control plane`). Keep everything else
pixel-consistent so the two entries visibly belong to the same lab.
