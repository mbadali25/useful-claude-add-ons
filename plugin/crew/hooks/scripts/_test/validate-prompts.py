import os, re, glob, json, sys
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))

OK = []; BAD = []
def ok(m):  OK.append(m)
def bad(m): BAD.append(m)

def frontmatter(path):
    t = open(path, encoding='utf-8').read()
    if not t.startswith('---\n'):
        return None, t
    end = t.index('\n---\n', 3)
    fm = {}
    for line in t[4:end].split('\n'):
        if ':' in line and not line.startswith(' '):
            k, v = line.split(':', 1)
            fm[k.strip()] = v.strip()
    return fm, t[end+5:]

agents = {os.path.basename(f)[:-3] for f in glob.glob('agents/*.md')}
cmds   = {os.path.basename(f)[:-3] for f in glob.glob('commands/*.md')}
skills = {os.path.basename(os.path.dirname(f)) for f in glob.glob('skills/*/SKILL.md')}
KNOWN_TOOLS = {'Read','Write','Edit','Bash','Grep','Glob','Agent','Skill','WebSearch',
               'WebFetch','ToolSearch','NotebookEdit','PowerShell','Task','MultiEdit'}

print("=== COMMANDS (%d) ===" % len(cmds))
for f in sorted(glob.glob('commands/*.md')):
    n = os.path.basename(f)
    fm, body = frontmatter(f)
    if fm is None: bad(f"{n}: no YAML frontmatter"); continue
    if not fm.get('description'): bad(f"{n}: no description")
    elif len(fm['description']) > 120: bad(f"{n}: description {len(fm['description'])} chars (keep it short)")
    else: ok(f"{n}: description")
    at = fm.get('allowed-tools', '')
    if not at: bad(f"{n}: no allowed-tools")
    else:
        unknown = [t.strip() for t in at.split(',') if t.strip() and t.strip() not in KNOWN_TOOLS]
        if unknown: bad(f"{n}: unknown tool(s) {unknown}")
        else: ok(f"{n}: allowed-tools")
    # agents it invokes must exist
    for m in re.finditer(r'`?crew:([a-z-]+)`?\s+subagent|`crew:([a-z-]+)`', body):
        a = m.group(1) or m.group(2)
        if a in cmds or a in skills: continue
        if a not in agents: bad(f"{n}: references agent crew:{a} which does not exist")
    # any plugin-root path it names must exist
    for m in re.finditer(r'\$\{CLAUDE_PLUGIN_ROOT\}/([A-Za-z0-9_\-./]+)', body):
        p = m.group(1).rstrip('.,`)')
        if not os.path.exists(p): bad(f"{n}: names missing path {p}")
    # a command that spawns agents must be allowed to
    if re.search(r'crew:(explorer|planner|analyst|qa-reviewer|security|dba|docs-writer|smoke-author|browser-tester)', body):
        if 'Agent' not in at: bad(f"{n}: spawns a subagent but allowed-tools has no Agent")
        else: ok(f"{n}: Agent permitted for the subagents it spawns")
    if len(body.strip()) < 200: bad(f"{n}: body is only {len(body.strip())} chars")

print("=== AGENTS (%d) ===" % len(agents))
for f in sorted(glob.glob('agents/*.md')):
    n = os.path.basename(f)
    fm, body = frontmatter(f)
    if fm is None: bad(f"{n}: no YAML frontmatter"); continue
    if fm.get('name') != n[:-3]: bad(f"{n}: name '{fm.get('name')}' != filename")
    else: ok(f"{n}: name matches filename")
    if not fm.get('description'): bad(f"{n}: no description")
    else: ok(f"{n}: description")
    for k in fm:
        if k not in ('name','description','tools','model'):
            bad(f"{n}: unsupported frontmatter key '{k}' (silently ignored)")
    t = fm.get('tools','')
    unknown = [x.strip() for x in t.split(',') if x.strip() and x.strip() not in KNOWN_TOOLS]
    if unknown: bad(f"{n}: unknown tool(s) {unknown}")
    else: ok(f"{n}: tools")
    m = fm.get('model','inherit')
    if m not in ('inherit','opus','sonnet','haiku'): bad(f"{n}: odd model '{m}'")
    else: ok(f"{n}: model")
    # a read-only agent must not hold write tools
    if 'read-only' in fm.get('description','').lower() or 'Read-only' in body[:400]:
        for w in ('Write','Edit'):
            if w in t: bad(f"{n}: described as read-only but holds {w}")
    if len(body.strip()) < 200: bad(f"{n}: body is only {len(body.strip())} chars")

print("=== SKILLS (%d) ===" % len(skills))
total_desc = 0
for f in sorted(glob.glob('skills/*/SKILL.md')):
    d = os.path.basename(os.path.dirname(f))
    fm, body = frontmatter(f)
    if fm is None: bad(f"{d}: no frontmatter"); continue
    if fm.get('name') != d: bad(f"{d}: name '{fm.get('name')}' != directory")
    else: ok(f"{d}: name matches directory")
    desc = fm.get('description','')
    if not desc: bad(f"{d}: no description")
    total_desc += len(desc)
    for k in fm:
        if k not in ('name','description','license','allowed-tools'):
            bad(f"{d}: unsupported frontmatter key '{k}'")
    for m in re.finditer(r'\$\{CLAUDE_PLUGIN_ROOT\}/([A-Za-z0-9_\-./]+)', body):
        p = m.group(1).rstrip('.,`)')
        if not os.path.exists(p): bad(f"{d}: names missing path {p}")

print()
print("PASS: %d checks" % len(OK))
if BAD:
    print("FAIL: %d" % len(BAD))
    for b in BAD: print("   -", b)
else:
    print("FAIL: 0")
print()
print("always-loaded skill description cost: %d chars (~%d tokens)" % (total_desc, total_desc//4))
sys.exit(1 if BAD else 0)
