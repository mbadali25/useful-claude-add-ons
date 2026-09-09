# Palette

Literal hex, copy verbatim — see `word-traps.md` rule 1 for why `var()` must
never appear in an emitted stylesheet.

Chosen for contrast on white **and** for staying distinguishable when printed in
greyscale, which is where most of these documents end up.

## Structure

| Role | Hex | Used for |
|---|---|---|
| Header navy | `#1F4E79` | Table header fill, `h1` rule, masthead band |
| Header text | `#FFFFFF` | Text on header navy |
| Body ink | `#1B1B1F` | Body text |
| Muted ink | `#5C5F6B` | Subtitles, captions, footer |
| Grid line | `#B8BCC6` | All table borders |
| Zebra fill | `#EEF3F8` | `tr.alt` rows, meta-table labels |
| Panel | `#F6F7F9` | Callout and card background |
| Section rule | `#DCDEE5` | `h2` underline |

## Masthead

| Row | Class | Hex | What it is |
|---|---|---|---|
| 1 | `mast-strip` | `#4A90C2` | 4px accent rule |
| 2 | `mast-band` | `#1F4E79` | Navy block: organisation, title, subtitle |
| 3 | `mast-rule` | `#143A5A` | 3px darker navy |
| 4 | `mast-cls` | `#8B1A13` | Classification bar, white letterspaced caps |

The organisation name sits in small letterspaced caps at `#A8C8E4` above a white
26px title.

## Severity — text colour and chip fill

| Severity | Text | Chip background | Meaning |
|---|---|---|---|
| Critical | `#A01B12` | `#FDE8E6` | Act now; exploited or trivially exploitable |
| High | `#9A3412` | `#FFEDD5` | Act this week |
| Medium | `#8A6100` | `#FDF3D7` | Scheduled remediation |
| Low | `#1C6B3F` | `#E3F4EA` | Note and move on |
| Info | `#2F4B7C` | `#E8EFF8` | Context, no action |
| Unverified | `#5C5F6B` | `#EDEEF1` | **Could not be checked — not the same as Pass** |

`Unverified` earns its own row deliberately. **A check that could not run is not
a check that passed**, and a report that renders the two identically is lying by
omission. If a probe failed, say so in its own severity rather than letting it
inherit the colour of success.

## Writing the chips

One class per element, every declaration repeated — `word-traps.md` rule 4.
Grouped selectors are the way to keep that manageable:

```css
.chip-critical, .chip-high, .chip-medium, .chip-low, .chip-info, .chip-unverified {
  display:inline-block; padding:2px 8px; font-weight:700; font-size:11px;
  border-radius:3px; white-space:nowrap;
}
.chip-critical   { background:#FDE8E6; color:#A01B12; }
.chip-high       { background:#FFEDD5; color:#9A3412; }
.chip-medium     { background:#FDF3D7; color:#8A6100; }
.chip-low        { background:#E3F4EA; color:#1C6B3F; }
.chip-info       { background:#E8EFF8; color:#2F4B7C; }
.chip-unverified { background:#EDEEF1; color:#5C5F6B; }
```

Note what that is doing: the shared declarations live in a **grouped selector**,
not in a base class the element also carries. `class="chip chip-critical"` would
apply neither rule.
