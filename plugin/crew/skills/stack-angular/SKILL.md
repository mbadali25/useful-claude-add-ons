---
name: stack-angular
description: |
  Angular and AngularJS pitfalls, checks and verify.json wiring - change detection, RxJS
  composition, subscription leaks, injector hierarchy. Use when the repo has angular.json or
  @angular/core, or an AngularJS 1.x app, or the user asks to write or review a component,
  service, RxJS pipeline, or asks why a list keeps re-rendering or a subscription never cleans up.
---

# Stack: Angular

## When this applies

Any repo with `angular.json` and `@angular/core` in `package.json` - or `angular` (1.x, a
different framework that shares a name) with no `angular.json`. Establish the major version
before writing a line: standalone components, signals, `@if`/`@for`, and `inject()` are all
version-gated. Write in the idiom the repo already uses unless the ticket is the migration.

## Pitfalls that cost time (Angular 2+)

- **A subscription without an end is a leak with a UI.** Every `subscribe()` needs
  `takeUntilDestroyed`, an `async` pipe, or an explicit unsubscribe in `ngOnDestroy`. The
  symptom is a handler running against a destroyed component after navigation, not a crash.
- **Change detection is the performance story.** A function call or a newly-constructed array
  in a template re-evaluates every cycle. `OnPush` fixes that and changes the rules - a
  mutated object is not a new reference, so the view silently stops updating.
- **RxJS composition errors are logic errors, not style choices.** `mergeMap` on a search box
  interleaves responses out of order; `switchMap` cancels the previous one; `concatMap`
  serialises; `exhaustMap` ignores while busy. A stream that errors terminates for good -
  handle it inside the inner observable if the outer must survive.
- **The injector hierarchy decides how many instances exist.** `providedIn: 'root'` is a
  singleton; the same service in a component's `providers` gets one per instance, and shared
  state quietly forks.
- **Template-driven and reactive forms behave differently on validation timing** - a control
  added to a `FormGroup` after init needs `updateValueAndValidity` to be believed.
- **`bypassSecurityTrust*` and `[innerHTML]` are XSS sinks** - sanitisation is the default
  these turn off.
- **A guard returning an observable that never emits hangs navigation** - the router takes the
  first emission and unsubscribes. A lazy route pulling a shared module drags it into its own
  chunk; check the bundle, not the intent.

## AngularJS (1.x) additions

A different framework, not an old Angular version. Most modern ESLint presets assume ES
modules and produce noise on string-annotated dependency injection (`'$scope', '$http', ...`
arrays) - configure the AngularJS-specific deprecated-pattern rules deliberately or the lint
output is worthless. `$digest`/`$apply` cycles are the change-detection equivalent; a manual
`$apply` inside code already in a digest throws "digest already in progress".

## Verification

Run what the repo runs - `ng build` (with `--configuration production` if that is what CI
does; a production build applies stricter template type-checking than the dev server), `ng
test`, `ng lint` - report exit codes, never summary lines. Say whether a test exercised the
subscription lifetime or change-detection change; a component test that never destroys the
component proves nothing about a leak.

## verify.json rule to propose

```json
{
  "paths": ["**/*.ts", "**/*.js", "**/*.html"],
  "run": [
    "sh -c 'E=node_modules/.bin/eslint; P=node_modules/.bin/prettier; [ -x \"$E\" ] || E=$(command -v eslint 2>/dev/null); [ -x \"$P\" ] || P=$(command -v prettier 2>/dev/null); if [ -z \"$E\" ] || [ -z \"$P\" ]; then echo \"TOOL MISSING: eslint and/or prettier is not installed locally (checked node_modules/.bin and PATH) - npx would try to download it rather than reporting UNVERIFIED. This is a missing tool, not a passing or failing check. Run npm install to check locally.\" >&2; exit 77; fi; F=$(git ls-files \"*.ts\" \"*.js\" \"*.html\"); \"$E\" . && { [ -z \"$F\" ] || \"$P\" --check $F; }'"
  ],
  "reach": "local",
  "why": "eslint/prettier catch drift and deprecated patterns before a human reviews the diff"
}
```

The probe checks for an already-installed `eslint`/`prettier` (local `node_modules/.bin` first,
then `PATH`) rather than a bare `command -v npx` - on a modern npm (7+), `npx <missing-pkg>` does
not fail closed on a missing package the way older npx's `--no-install` did; it reaches the registry
and either downloads it or fails with a network/404 error, neither of which is this repo's
tool-missing convention. `prettier --check` is scoped to the same `**/*.ts`/`**/*.js`/`**/*.html`
globs this rule triggers on via `git ls-files`, not the whole repo - prettier also formats
Markdown/JSON/YAML, and an Angular edit should not fail on unrelated drift in those.

Nothing in this repo writes rules into `verify.json` on a skill's behalf (see the
`crew-verification` skill) - add this by hand.

## LSP

Use the Angular language service (decided for crew 1.0) rather than Serena, which was
evaluated and skipped for this stack.
