# C-0047: cloud-guard sabotage entries retired from sabotage_cloud.py

Retired 2026-10-07 (owner) so G4 (T-0009) lands green; re-add in H2.

T-0009 (environment-scoped workflow deploys, PR #336, landing in rush group G4) rewrote the
command-word trigger in `cloud_guard.py` and `crew_guards.py` and moved the dispatch reader into
`crew_dispatch.py`. That removed the line each entry below is anchored to, so
`test_sabotage_harness.py::test_every_shipped_anchor_is_present_in_its_target_exactly_once` fails
once T-0009 lands. `scripts/check-tooling-pr.py` does not allow a harness change in the same PR
as feature work, so these entries leave `plugin/crew/tests/sabotage_cloud.py` in a harness-only PR
first. H2 re-adds each one, anchored to the new code (`crew_dispatch.py`, or the new
`cloud_guard.py` / `crew_guards.py`), red again on its named test.

28 entries, in file order. Each block is the entry's source exactly as it stood in
`sabotage_cloud.py` at origin/main 7cb442217, in the tuple shape
`(label, target, anchor, mutation, test)`. `GUARD` is `plugin/crew/hooks/scripts/cloud_guard.py` and `GUARDS` is
`plugin/crew/hooks/scripts/crew_guards.py`; the test-id prefixes (`_T`, `_E`, `_S9`, `_R5`, `_S10`, ...) are defined at
the top of that file and stay there.

## 1. cloud guard env: prodUnattended read from the repo alone

- Target: `plugin/crew/hooks/scripts/cloud_guard.py`
- Test: `tests/test_cloud_guard_environments.py::test_must_block_env_python[prod-repo-only-unattended]`

```python
("cloud guard env: prodUnattended read from the repo alone", GUARD,
     '    out["prodUnattended"] = crew_config.resolve_ratcheted(\n'
     '        root, "environments.prodUnattended")["effective"] is True\n',
     '    out["prodUnattended"] = crew_state.load_config(root).get(\n'
     '        "environments", {}).get("prodUnattended") is True\n',
     _EB + "[prod-repo-only-unattended]")
```

## 2. cloud guard env: a malformed environments block reads as empty

- Target: `plugin/crew/hooks/scripts/cloud_guard.py`
- Test: `tests/test_cloud_guard_environments.py::test_must_block_env_python[unknown-malformed-block]`

```python
("cloud guard env: a malformed environments block reads as empty", GUARD,
     '            out = {"nonProd": [], "problem": problem}\n',
     '            out = {"nonProd": [], "problem": ""}\n',
     _EB + "[unknown-malformed-block]")
```

## 3. cloud guard step 9: the gate triggered by any word again

- Target: `plugin/crew/hooks/scripts/cloud_guard.py`
- Test: `tests/test_cloud_guard_environments.py::test_command_word_must_allow_python[s9a-commit-message]`

```python
("cloud guard step 9: the gate triggered by any word again", GUARD,
     "        found = command_trigger(text, _GATE_HELPERS)\n",
     "        named = __import__(\"crew_guards\").names_terraform(text, "
     "shell)\n"
     "        found = None if named is None else (named, False)\n",
     _S9A + "[s9a-commit-message]")
```

## 4. cloud guard step 9: an unknown command word never gated

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_command_word_must_block_python[s9-variable-name]`

```python
("cloud guard step 9: an unknown command word never gated", GUARDS,
     "        named = _verb_on_line(top)\n"
     "        return None if named is None else (named, True)\n",
     "        return None\n", _S9 + "[s9-variable-name]")
```

## 5. cloud guard step 9: `bash -c` payload not read

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard.py::test_could_not_tell_is_refused_under_block[was-bash-c-dashdash-taint]`

```python
("cloud guard step 9: `bash -c` payload not read", GUARDS,
     "            return _bash_trigger(positional[0], top, helpers, "
     "depth + 1,\n                                 line)\n",
     "            return None\n",
     _T + "test_could_not_tell_is_refused_under_block"
     "[was-bash-c-dashdash-taint]")
```

## 6. cloud guard step 9: a shell reading stdin not gated

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_command_word_must_block_python[s9-pipe-to-shell]`

```python
("cloud guard step 9: a shell reading stdin not gated", GUARDS,
     '        named = names_terraform(top, "bash")\n'
     "        return None if named is None else (named, True)\n"
     "    if head in _GATE_PWSH:\n",
     "        return None\n    if head in _GATE_PWSH:\n",
     _S9 + "[s9-pipe-to-shell]")
```

## 7. cloud guard step 9: `pwsh -c` payload not read

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_command_word_must_block_python[s9-pwsh-c]`

```python
("cloud guard step 9: `pwsh -c` payload not read", GUARDS,
     "            return None if named is None else (named, True)\n"
     "        return ps_trigger(ps_normalise(payload)[0], helpers, depth + 1)\n",
     "            return None if named is None else (named, True)\n"
     "        return None\n", _S9 + "[s9-pwsh-c]")
```

## 8. cloud guard step 9: `eval` payload not read

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_command_word_must_block_python[s9-eval]`

```python
("cloud guard step 9: `eval` payload not read", GUARDS,
     '        return _bash_trigger(" ".join(args), top, helpers, depth + 1, '
     "line)\n", "        return None\n", _S9 + "[s9-eval]")
```

## 9. cloud guard step 9: a command word that is a script not read

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_command_word_must_block_python[s9-watch-string]`

```python
("cloud guard step 9: a command word that is a script not read", GUARDS,
     '        return _bash_trigger(" ".join(argv), top, helpers, depth + 1, '
     "line)\n", "        return None\n", _S9 + "[s9-watch-string]")
```

## 10. cloud guard step 9: the reader's give-up gates nothing

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_command_word_must_block_python[s9-case]`

```python
("cloud guard step 9: the reader's give-up gates nothing", GUARDS,
     '        named = names_terraform(text, "bash") or '
     'names_terraform(top, "bash")\n'
     "        return None if named is None else (named, True)\n",
     "        return None\n", _S9 + "[s9-case]")
```

## 11. cloud guard r5: a PowerShell path run with a verb not read

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_round5_must_block_python[r5-ps-copied-binary]`

```python
("cloud guard r5: a PowerShell path run with a verb not read", GUARDS,
     "    if head in copies and verb is not None and verb.lower() in "
     "_GATE_VERBS:\n", "    if False:\n", _R5 + "[r5-ps-copied-binary]")
```

## 12. cloud guard r5: a bash command run with a verb not read

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_round5_must_block_python[r5-ln-dot-slash]`

```python
("cloud guard r5: a bash command run with a verb not read", GUARDS,
     '    if head in line["copies"] and verb is not None \\\n',
     "    if False and verb is not None \\\n", _R5 + "[r5-ln-dot-slash]")
```

## 13. cloud guard r5: a copied binary not noticed

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_round5_must_block_python[r5-cp-bare-name]`

```python
("cloud guard r5: a copied binary not noticed", GUARDS,
     '    line["copies"] |= _copies_terraform(cmds, helpers[4])\n',
     '    line["copies"] |= set()\n', _R5 + "[r5-cp-bare-name]")
```

## 14. cloud guard r5: zsh's =terraform as the command word ignored

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_round5_must_block_python[r5-zsh-equals-taint]`

```python
("cloud guard r5: zsh's =terraform as the command word ignored", GUARDS,
     "    if _zsh_names_tool(first):\n        return first, True\n", "",
     _R5 + "[r5-zsh-equals-taint]")
```

## 15. cloud guard r5: find -exec not read

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_round5_must_block_python[r5-find-exec-found-binary]`

```python
("cloud guard r5: find -exec not read", GUARDS,
     "        return _find_exec_trigger(args, top, helpers, depth, line)\n",
     "        return None\n", _R5 + "[r5-find-exec-found-binary]")
```

## 16. cloud guard r5: find -exec read line-wide again

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_round5_must_allow_python[r5a-find-exec-grep]`

```python
("cloud guard r5: find -exec read line-wide again", GUARDS,
     "        return _find_exec_trigger(args, top, helpers, depth, line)\n",
     '        named = names_terraform(top, "bash")\n'
     "        return None if named is None else (named, True)\n",
     _R5A + "[r5a-find-exec-grep]")
```

## 17. cloud guard r5: a script runner read line-wide again

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_round5_must_allow_python[r5a-source-then-plan]`

```python
("cloud guard r5: a script runner read line-wide again", GUARDS,
     "        own = names_terraform(top if any(_HOLE in a for a in args)\n"
     '                              else " ".join(args), "bash")\n',
     '        own = names_terraform(top, "bash")\n',
     _R5A + "[r5a-source-then-plan]")
```

## 18. cloud guard r5: a script runner's run-time words not read

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_command_word_must_block_python[s9-source-procsub]`

```python
("cloud guard r5: a script runner's run-time words not read", GUARDS,
     "        own = names_terraform(top if any(_HOLE in a for a in args)\n"
     '                              else " ".join(args), "bash")\n',
     '        own = names_terraform(" ".join(args), "bash")\n',
     _S9 + "[s9-source-procsub]")
```

## 19. cloud guard r5: a shell running a script file gated

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_round5_must_allow_python[r5a-bash-script-file]`

```python
("cloud guard r5: a shell running a script file gated", GUARDS,
     "        if not has_c and positional and _HOLE not in positional[0] \\\n"
     "                and not _names_tool(positional[0]):\n",
     "        if False:\n", _R5A + "[r5a-bash-script-file]")
```

## 20. cloud guard s10: the unknown-wrapper fallback reinstated

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_ordinary_command_is_allowed[s10a-rg-var]`

```python
("cloud guard s10: the unknown-wrapper fallback reinstated", GUARDS,
     "        named = names_terraform(top, \"bash\")\n"
     "        if named is not None:\n"
     "            return named, True\n"
     "    return None\n",
     "        named = names_terraform(top, \"bash\")\n"
     "        if named is not None:\n"
     "            return named, True\n"
     "    for index, arg in enumerate(args):\n"
     "        if _HOLE in arg or not _arg_names_tool(arg):\n"
     "            continue\n"
     "        rest = [a for a in args[index + 1:] if not a.startswith(\"-\")]\n"
     "        if rest and (_HOLE in rest[0] or rest[0].lower() in _GATE_VERBS):\n"
     "            return arg, True\n"
     "    return None\n", _S10A + "[s10a-rg-var]")
```

## 21. cloud guard s10: PowerShell gets the any-word trigger again

- Target: `plugin/crew/hooks/scripts/cloud_guard.py`
- Test: `tests/test_cloud_guard_environments.py::test_ordinary_command_is_allowed[s10a-ps-commit-message]`

```python
("cloud guard s10: PowerShell gets the any-word trigger again", GUARD,
     "        found = ps_trigger(_ps_normalise(text)[0], _GATE_HELPERS)\n",
     "        named = __import__(\"crew_guards\").names_terraform(\n"
     "            _ps_normalise(text)[0], shell)\n"
     "        found = None if named is None else (named, False)\n",
     _S10A + "[s10a-ps-commit-message]")
```

## 22. cloud guard s10: PowerShell's read-only subcommands gated

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_ordinary_command_is_allowed[s10a-ps-output-raw]`

```python
("cloud guard s10: PowerShell's read-only subcommands gated", GUARDS,
     "        return None if _tf_read_only(argv, []) else (first, False)\n",
     "        return first, False\n", _S10A + "[s10a-ps-output-raw]")
```

## 23. cloud guard s10: PowerShell's command word naming terraform ignored

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_direct_spelling_is_denied_unattended[s10-ps-call-quoted-plan-ask]`

```python
("cloud guard s10: PowerShell's command word naming terraform ignored",
     GUARDS,
     "        return None if _tf_read_only(argv, []) else (first, False)\n",
     "        return None\n", _S10 + "[s10-ps-call-quoted-plan-ask]")
```

## 24. cloud guard s10: a PowerShell command word made at run time ignored

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_direct_spelling_is_denied_unattended[s10-ps-variable-command-ask]`

```python
("cloud guard s10: a PowerShell command word made at run time ignored",
     GUARDS,
     "        named = _ps_verb_on_line(normal)\n"
     "        return None if named is None else (named, True)\n",
     "        return None\n", _S10 + "[s10-ps-variable-command-ask]")
```

## 25. cloud guard s10: PowerShell's `pwsh -c` payload not read

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_direct_spelling_is_denied_unattended[s10-ps-pwsh-quoted-plan-ask]`

```python
("cloud guard s10: PowerShell's `pwsh -c` payload not read", GUARDS,
     "            return ps_trigger(ps_normalise(payload)[0], helpers, "
     "depth + 1)\n", "            return None\n",
     _S10 + "[s10-ps-pwsh-quoted-plan-ask]")
```

## 26. cloud guard s10: PowerShell's `bash -c` payload not read

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_direct_spelling_is_denied_unattended[s10-ps-bash-c-quoted-plan-ask]`

```python
("cloud guard s10: PowerShell's `bash -c` payload not read", GUARDS,
     "            return _bash_trigger(positional[0], positional[0], helpers,\n"
     "                                 depth + 1)\n",
     "            return None\n", _S10 + "[s10-ps-bash-c-quoted-plan-ask]")
```

## 27. cloud guard s10: PowerShell's `$(...)` not read

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_direct_spelling_is_denied_unattended[s10-ps-subexpression-quoted-plan-ask]`

```python
("cloud guard s10: PowerShell's `$(...)` not read", GUARDS,
     "    hits = [ps_trigger(sub, helpers, depth + 1) for sub in subs]\n",
     "    hits = []\n", _S10 + "[s10-ps-subexpression-quoted-plan-ask]")
```

## 28. cloud guard s10: a verb after a mention read as a renamed terraform

- Target: `plugin/crew/hooks/scripts/crew_guards.py`
- Test: `tests/test_cloud_guard_environments.py::test_ordinary_command_is_allowed[s10a-fmt-then-kubectl]`

```python
("cloud guard s10: a verb after a mention read as a renamed terraform",
     GUARDS, '    if head in line["copies"] and verb is not None \\\n',
     "    if names_terraform(top, \"bash\") and verb is not None \\\n",
     _S10A + "[s10a-fmt-then-kubectl]")
```
