#!/usr/bin/env python3
"""Dump every form and input on a page, with a suggested Playwright locator for each.

Run this before writing form-filling code so the selectors come from the real
rendered DOM rather than from guesswork or from source that may not match what
ships. Also flags accessibility problems that will bite you later — an input
with no label is both an a11y bug and an unstable thing to target.

    python3 inspect_forms.py https://example.com/signup
    python3 inspect_forms.py http://127.0.0.1:3000/app --storage-state ./auth.json --json

Password field values are never printed.
"""

import argparse
import json
import sys

try:
    from playwright.sync_api import Error as PWError
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("Playwright is not installed. Run: python3 scripts/check_env.py")

# Runs in the page. Collects controls grouped by their owning form (or a
# synthetic "no form element" bucket, which is normal for React/Vue apps).
EXTRACT_JS = r"""
() => {
  const labelFor = (el) => {
    if (el.labels && el.labels.length) {
      const t = [...el.labels].map(l => l.innerText.trim()).filter(Boolean).join(' ');
      if (t) return t;
    }
    if (el.getAttribute('aria-label')) return el.getAttribute('aria-label').trim();
    const lb = el.getAttribute('aria-labelledby');
    if (lb) {
      const t = lb.split(/\s+/).map(id => {
        const n = document.getElementById(id);
        return n ? n.innerText.trim() : '';
      }).filter(Boolean).join(' ');
      if (t) return t;
    }
    const wrap = el.closest('label');
    if (wrap) return wrap.innerText.trim();
    return '';
  };

  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };

  const describe = (el) => {
    const tag = el.tagName.toLowerCase();
    const type = tag === 'input' ? (el.type || 'text').toLowerCase() : tag;
    const d = {
      tag, type,
      name: el.name || null,
      id: el.id || null,
      testid: el.getAttribute('data-testid') || el.getAttribute('data-test-id')
              || el.getAttribute('data-test') || null,
      label: labelFor(el) || null,
      placeholder: el.getAttribute('placeholder') || null,
      required: !!el.required || el.getAttribute('aria-required') === 'true',
      disabled: !!el.disabled,
      readonly: !!el.readOnly,
      visible: visible(el),
      autocomplete: el.getAttribute('autocomplete') || null,
      constraints: {},
      value: null,
      options: null,
    };
    for (const a of ['minlength', 'maxlength', 'min', 'max', 'step', 'pattern', 'accept']) {
      const v = el.getAttribute(a);
      if (v !== null) d.constraints[a] = v;
    }
    if (type === 'password') {
      d.value = el.value ? '<non-empty, redacted>' : null;
    } else if (type === 'checkbox' || type === 'radio') {
      d.value = el.checked ? 'checked' : 'unchecked';
      if (el.value && el.value !== 'on') d.constraints.value = el.value;
    } else if (tag === 'select') {
      d.options = [...el.options].map(o => ({
        value: o.value, text: o.text.trim(), selected: o.selected,
      }));
      d.multiple = el.multiple;
    } else {
      d.value = el.value ? String(el.value).slice(0, 120) : null;
    }
    return d;
  };

  const CONTROLS = 'input, select, textarea, [contenteditable="true"]';
  const BUTTONS = 'button, input[type=submit], input[type=button], input[type=reset], [role=button]';
  // input[type=submit] etc. match CONTROLS too — they belong under buttons, not fields.
  const NON_FIELD = new Set(['hidden', 'submit', 'button', 'reset', 'image']);
  const isField = (el) => !NON_FIELD.has((el.type || '').toLowerCase());

  const forms = [...document.forms].map((f, i) => ({
    index: i,
    id: f.id || null,
    name: f.getAttribute('name') || null,
    action: f.getAttribute('action') || null,
    method: (f.getAttribute('method') || 'get').toLowerCase(),
    role: f.getAttribute('role') || null,
    novalidate: f.noValidate,
    fields: [...f.querySelectorAll(CONTROLS)].filter(isField).map(describe),
    hidden_fields: [...f.querySelectorAll('input[type=hidden]')]
      .map(el => ({ name: el.name || null, has_value: !!el.value })),
    buttons: [...f.querySelectorAll(BUTTONS)].map(b => ({
      text: (b.innerText || b.value || '').trim() || null,
      type: (b.type || 'submit').toLowerCase(),
      testid: b.getAttribute('data-testid') || null,
      disabled: !!b.disabled,
    })),
  }));

  const orphans = [...document.querySelectorAll(CONTROLS)]
    .filter(el => !el.form && isField(el))
    .map(describe);

  const looseButtons = [...document.querySelectorAll(BUTTONS)]
    .filter(b => !b.form)
    .map(b => ({
      text: (b.innerText || b.value || '').trim() || null,
      type: (b.type || 'button').toLowerCase(),
      testid: b.getAttribute('data-testid') || null,
      disabled: !!b.disabled,
    }))
    .filter(b => b.text);

  return { forms, orphans, looseButtons, title: document.title, url: location.href };
}
"""

# Roles used when suggesting get_by_role for a field.
ROLE_BY_TYPE = {
    "checkbox": "checkbox",
    "radio": "radio",
    "select": "combobox",
    "search": "searchbox",
    "textarea": "textbox",
}


def suggest_locator(f):
    """Best-practice Playwright locator for a field, most robust first."""
    def q(s):
        return s.replace('"', '\\"')

    if f.get("label"):
        label = " ".join(f["label"].split())[:60]
        return f'page.get_by_label("{q(label)}")'
    if f.get("testid"):
        return f'page.get_by_test_id("{q(f["testid"])}")'
    if f.get("placeholder"):
        return f'page.get_by_placeholder("{q(f["placeholder"])}")'
    role = ROLE_BY_TYPE.get(f["type"])
    if role and f.get("name"):
        return f'page.locator("{f["tag"]}[name=\'{f["name"]}\']")  # no label — role lookup needs a name'
    if f.get("name"):
        return f'page.locator("{f["tag"]}[name=\'{q(f["name"])}\']")'
    if f.get("id"):
        return f'page.locator("#{q(f["id"])}")'
    return f'page.locator("{f["tag"]}")  # UNSTABLE: no label, name, id, or test id'


def fill_snippet(f):
    """How you'd actually drive this control."""
    loc = suggest_locator(f).split("  #", maxsplit=1)[0]
    t = f["type"]
    if t in ("checkbox", "radio"):
        return f"{loc}.check()"
    if t == "select":
        first = (f.get("options") or [{}])[0].get("value", "VALUE")
        return f'{loc}.select_option("{first}")'
    if t == "file":
        return f'{loc}.set_input_files("path/to/file")'
    if t == "password":
        return f'{loc}.fill(os.environ["APP_PASSWORD"])'
    return f'{loc}.fill("VALUE")'


def render_field(f, indent="    "):
    flags = []
    if f["required"]:
        flags.append("required")
    if f["disabled"]:
        flags.append("disabled")
    if f["readonly"]:
        flags.append("readonly")
    if not f["visible"]:
        flags.append("NOT VISIBLE")
    for k, v in (f.get("constraints") or {}).items():
        flags.append(f"{k}={v}")
    flagstr = f"  [{', '.join(flags)}]" if flags else ""

    ident = f["name"] or f["id"] or f.get("testid") or "(anonymous)"
    lines = [f"{indent}{f['type']:<10} {ident}{flagstr}"]
    lines.append(f"{indent}  label     : {f['label'] or '** NONE — a11y issue **'}")
    if f.get("value"):
        lines.append(f"{indent}  value     : {f['value']}")
    if f.get("options"):
        opts = ", ".join(f"{o['value']!r}" for o in f["options"][:8])
        more = "" if len(f["options"]) <= 8 else f" ... {len(f['options'])} total"
        lines.append(f"{indent}  options   : {opts}{more}")
    lines.append(f"{indent}  locator   : {suggest_locator(f)}")
    lines.append(f"{indent}  fill with : {fill_snippet(f)}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("url")
    ap.add_argument("--storage-state", help="auth JSON saved by login.py")
    ap.add_argument("--wait-for", help="CSS selector to wait for before inspecting")
    ap.add_argument("--frame", help="inspect inside the iframe whose URL contains this string")
    ap.add_argument("--timeout", type=int, default=30000)
    ap.add_argument("--browser", default="chromium",
                    choices=["chromium", "firefox", "webkit"])
    ap.add_argument("--ignore-https-errors", action="store_true")
    ap.add_argument("--json", action="store_true", help="raw JSON instead of a report")
    ap.add_argument("--out", help="also write the JSON to this path")
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = getattr(p, args.browser).launch()
        ctx_args = {"ignore_https_errors": args.ignore_https_errors}
        if args.storage_state:
            ctx_args["storage_state"] = args.storage_state
        context = browser.new_context(**ctx_args)
        page = context.new_page()
        page.set_default_timeout(args.timeout)
        page.goto(args.url, wait_until="load", timeout=args.timeout)
        if args.wait_for:
            try:
                page.locator(args.wait_for).first.wait_for(state="visible")
            except (PWTimeout, PWError) as exc:
                print(f"WARNING: --wait-for never appeared ({exc.__class__.__name__});"
                      " inspecting anyway", file=sys.stderr)
        target = page
        if args.frame:
            target = page.frame(url=lambda u: args.frame in u)
            if target is None:
                sys.exit(f"No iframe matching {args.frame!r}. Frames present: "
                         + ", ".join(f.url for f in page.frames))
        data = target.evaluate(EXTRACT_JS)
        context.close()
        browser.close()

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    if args.json:
        print(json.dumps(data, indent=2))
        return 0

    print(f"\n{data['title']!r}  —  {data['url']}")
    print(f"{len(data['forms'])} <form> element(s), "
          f"{len(data['orphans'])} control(s) outside any form\n")

    for form in data["forms"]:
        ident = form["id"] or form["name"] or f"index {form['index']}"
        print(f"FORM {ident}")
        print(f"  {form['method'].upper()} -> {form['action'] or '(same page / JS handler)'}"
              + ("   [novalidate]" if form["novalidate"] else ""))
        if form["hidden_fields"]:
            print("  hidden: " + ", ".join(
                f"{h['name']}{'' if h['has_value'] else ' (empty)'}"
                for h in form["hidden_fields"]))
        print("  fields:")
        for f in form["fields"]:
            print(render_field(f))
        if form["buttons"]:
            print("  buttons:")
            for b in form["buttons"]:
                dis = " [disabled]" if b["disabled"] else ""
                name = b["text"] or "(no accessible name)"
                print(f'    {b["type"]:<8} {name!r}{dis}')
                print(f'      locator : page.get_by_role("button", name="{name}")')
        print()

    if data["orphans"]:
        print("CONTROLS NOT IN A FORM  (normal for SPA frameworks)")
        for f in data["orphans"]:
            print(render_field(f))
        print()

    if data["looseButtons"]:
        print("OTHER BUTTONS ON PAGE")
        for b in data["looseButtons"][:20]:
            print(f'    {b["text"]!r}'
                  f'{" [disabled]" if b["disabled"] else ""}')
        print()

    unlabeled = [f for form in data["forms"] for f in form["fields"] if not f["label"]]
    unlabeled += [f for f in data["orphans"] if not f["label"]]
    if unlabeled:
        print(f"NOTE: {len(unlabeled)} control(s) have no accessible label. "
              "That's an accessibility bug and it forces brittle selectors — "
              "worth reporting to the user.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
