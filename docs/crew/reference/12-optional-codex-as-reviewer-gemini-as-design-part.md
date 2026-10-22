<!-- Moved verbatim from plugin/crew/README.md (12. Optional: Codex as reviewer, Gemini as design partner) by L-0726; the README keeps an index entry. -->

## 12. Optional: Codex as reviewer, Gemini as design partner

A different model reviewing is real independent review. The same model family reviewing itself agrees with itself more than it should, because the author's reasoning is exactly the reasoning it finds persuasive.

Put `codex` on your `PATH` and set `qa.provider` to `auto` or `codex`. `/crew:review` writes the diff to a file, has Codex return one line per defect, and reads only the findings back — the diff never re-enters your context.

`auto` is the shipped default, so a machine with `codex` installed gets Codex review without configuring anything.

Without Codex, `/crew:review` walks `qa.order` — `["codex", "kimi", "copilot", "claude"]` by default — and takes the first provider whose probe answers — a real call for Codex (`review_run.py --probe`), not just `command -v` — announcing every one it skipped and why.

**A gone pin falls back across families, never to Claude by default (L-0712).** When a pinned model is unavailable, the `qa.fallback` / `dev.fallback` model runs on the provider that serves its family (`crew_state.provider_for_model`: a `gpt-6.1-sol` fallback dispatches to Codex), and a fallback in the author's family is skipped for the next provider in `qa.order` whose family did not write the diff and which answers. If none answers, the round is INCOMPLETE and refunded, never a same-family read; a same-family review runs only on the operator's explicit choice and is labelled so. Before this, every fallback was hard-coded to `claude`. `/crew:status` prints `review   same-family: N of M completed rounds (P%)` across every ledger, and marks a ticket line `same-family round`; the target is under 5%.

To check a provider by hand, `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/provider_probe.py" codex --root .` (or `copilot --root . --model <m>`) makes one real call with review's own command line (`review_run.command_for` and `launch`): `--skip-git-repo-check`, `-C <root>` and the repo root as its working directory, from whatever directory it is run in, so it never hits Codex's "Not inside a trusted directory". It prints `codex: ok (<model>)` (exit 0), `codex: FAILED - <reason>` (exit 1: a failed call, an event stream with no completed turn, or a timeout after 120 s) or `codex: not installed` (exit 2). It costs one call, reserves nothing, and no hook or `/crew:status` runs it (T-0065).

When that Codex call fails on a usage limit, rate limit or quota (Codex's own messages, cited in `hooks/scripts/review_limit.py`), Codex is skipped, pinned or not, with the error quoted, and `/crew:review` takes the next cross-family provider in `$ELIGIBLE`. A limit hit in the middle of a round is recorded beside the review ledger, so the next round skips Codex without another call; the one after probes Codex again (T-0088). Since L-0712 (crew 1.2.6) a Claude read after a limit is no longer automatic: when no cross-family reviewer is left, `review_ledger.py --no-reviewer --reason <why>` records the outcome INCOMPLETE and refunded in the ledger's `unreviewed` list (no round, no budget), and a Claude read of Claude's work runs only on the operator's explicit `review_run.py --same-family "<reason>"`, which labels the round, review.json and a CLEAN receipt `same_family` (never auto-accepted), announced `same-family (codex limit)`. `review_run.py --authors "$AUTHORS" --author-source "$AUTHOR_SOURCE"` refuses any reviewer of the author's family, or of a family it cannot tell (an `unknown` source included), with exit 2 and nothing reserved; `--probe` asks it first. With no `--authors`, a Claude or unknown-family reservation is refused the same way unless `--same-family` labels it, whatever other flag (`--round` included) comes with `--reserve-only`; `review_ledger.py --reserve` asks the same guard; a labelled round's metrics row says `same-family: operator choice`. A failed probe of a codex-pinned `review` role is `resolve_role`'s `available`, so `/crew:review` dispatches the resolved fallback (`$FALLBACK`): a `gpt-6.1-sol` fallback runs on Codex. `/crew:status` marks a ticket's no-reviewer outcomes.

Kimi Code (`kimi`) is the second rung of the default order since crew 1.0.85. Its family is `kimi` whatever it is pinned to, so it needs no pin to be independent of a Claude author, and every `qa.roles.<r>` and `dev.roles.<r>` slot accepts a Kimi pin. `/crew:review` launches it since L-0527 (`review_run.py --provider kimi`, step 2e): `kimi_probe.py` runs before the round is reserved and only `ok` launches; since `kimi -p` cannot be made read-only by a flag, the working tree is fingerprinted from before the probe to after the review, and a reviewer write makes the round INCOMPLETE, naming the paths (a probe that wrote exits 8, no round spent); a process the reviewer leaves running is stopped first. `graph.out`, and only while gitignored IDE state and crew's hook logs, are set aside. A Kimi round is not retried in-process (L-0514). The launch gate is unchanged: `crew_config.review_launchable()` is `review_run.LAUNCHED` plus the in-session `claude`, and a `qa.order` provider outside it is reported and skipped; `kimi` in `review_run.LAUNCHED` is what made it eligible. `kimi_probe.py` answers now whether Kimi could review: `ok`, `not-installed`, `not-authenticated`, `rate-limited` or `unknown`, and only `ok` is launchable; `providers.sh --probe-kimi` runs it. See `skills/crew-providers/SKILL.md`, "Kimi Code".

GitHub Copilot is the middle rung, and it earns its place for one reason: it is a gateway to model families nothing else here reaches. Pin `qa.copilot.model` to a Google model such as `gemini-3.7-flash` and the reviewer is genuinely independent of both the author and Codex. Confirm the name against Copilot's current catalog rather than copying one from documentation - the names churn, and a stale one fails at startup with `Model "<name>" from --model flag is not available`. Leave it unset and Copilot is **skipped entirely** — its own default is `claude-sonnet-4.6`, the author's family, so an unpinned Copilot would be a same-family review wearing an independent one's costume. That is worse than the fallback below, which at least admits what it is.

Last is the `reviewer` agent — on `opus`, in its own context window, so it has at least not seen the reasoning that produced the code. Its prompt tells it outright that it shares a model family with the author and must compensate: ask "what input makes this wrong" before "does this look correct." That is genuinely weaker than a different family, and the command says so every time it happens, so you know to review harder yourself. It also says so itself if something dispatches it directly and skips the provider walk.

Two knobs on the Codex rung, both read at call time and both passing no flag when null, so an upgraded repo behaves exactly as it did before: `qa.codex.model` pins a model, and `qa.codex.reasoningEffort` takes `none`, `minimal`, `low`, `medium`, `high`, `xhigh` or `max`. A wrong effort value is safe to get wrong — Codex rejects it with a 400 naming the supported set rather than quietly returning a shallower review.

### Gemini for design

```
/crew:plan T-0042
/crew:plan should the export run inline or move to a queue
```

`/crew:plan`'s optional second opinion gets an independent view on a design
decision before anything is built. Gemini's free tier suits this well — design questions are a
handful of calls a week, so rate limits never bite.

**It works from a brief, never from your code.** Free tiers are funded by prompts
and generally train on them, so what leaves the machine is the shape of the
problem: constraints, volumes, latency budgets, the options under consideration,
and what has already been ruled out. No source, no real schema names, no service
names, no ticket text.

The control is not a promise — it is an artifact. `/crew:plan` writes the brief to
`.work/briefs/`, shows it to you, and waits for approval before sending. You can
read exactly what goes out, every time.

Two rules that make the output worth having:

- **The disagreement is the product.** The agent reports where the external
  opinion differs *in full*, including reasoning it finds unconvincing, rather
  than blending both views into a smooth consensus. Merging it away means paying
  for a second opinion and throwing it out.
- **Don't hardcode the model name.** Free catalogs churn and models get retired.
  It lives in `secondOpinion.model` and is read at call time.

If code must not leave the machine at all, set `provider` to `local` and point it
at Ollama, or `none` and accept single-opinion planning. Both are legitimate —
the agent just has to say which is in effect.

### Verifying either one

```bash
bash skills/crew-setup/scripts/providers.sh
```

Presence on `PATH` is not working auth, and the difference shows up later as a
gate that never fails. Phase 2 of `/crew:init` requires one real round trip per
configured provider before marking itself done.
