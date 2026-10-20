export const meta = {
  name: 'wave',
  description: 'Run an approved crew wave set as parallel worktree lanes: start, lanes, collect',
  whenToUse: 'After /crew:autopilot wave has recorded a set and the owner approved it. Args: {"set": "<slug>"}.',
  phases: [{ title: 'Start' }, { title: 'Lanes' }, { title: 'Collect' }],
}

// The deterministic work stays in crew_wave.py (start --json, lane-prompt, collect --json).
// This script only fans the lanes out and never reads a lane's result as clean unless it
// says so. Anything missing, malformed or rejected is `unknown`.
// A lane agent also keeps the lane's own rules: lane-init, review, lane-done (the lane prompt).

const LANE_STATES = ['clean', 'findings', 'question', 'failed']
const SLUG = /^[A-Za-z0-9][A-Za-z0-9._-]*$/

const START_SCHEMA = {
  type: 'object',
  properties: {
    stop: { type: 'boolean' },
    stopReason: { type: 'string' },
    maxLanes: { type: 'integer' },
    lanes: {
      type: 'array',
      items: {
        type: 'object',
        properties: { ticket: { type: 'string' }, prompt: { type: 'string' }, model: { type: 'string' } },
        required: ['ticket', 'prompt'],
      },
    },
  },
  required: ['stop', 'stopReason', 'maxLanes', 'lanes'],
}

const LANE_SCHEMA = {
  type: 'object',
  properties: {
    ticket: { type: 'string' },
    state: { type: 'string' },
    reason: { type: 'string' },
  },
  required: ['ticket', 'state', 'reason'],
}

const COLLECT_SCHEMA = {
  type: 'object',
  properties: {
    lanes: {
      type: 'array',
      items: {
        type: 'object',
        properties: { ticket: { type: 'string' }, state: { type: 'string' }, reason: { type: 'string' } },
        required: ['ticket', 'state'],
      },
    },
  },
  required: ['lanes'],
}

const isObject = (value) => value !== null && typeof value === 'object' && !Array.isArray(value)
const text = (value) => (typeof value === 'string' ? value : '')

const slug = isObject(args) ? args.set : undefined
if (typeof slug !== 'string' || !SLUG.test(slug)) {
  return { error: 'args.set must be the wave set slug, e.g. {"set": "my-wave"}' }
}
const scriptsHint = isObject(args) && typeof args.scripts === 'string' ? args.scripts : ''

const locate = `Find crew's hooks/scripts directory (the one holding crew_wave.py): ${scriptsHint
  ? `use ${scriptsHint}`
  : 'use $CLAUDE_PLUGIN_ROOT/hooks/scripts when that variable is set; otherwise the newest installed crew plugin, ' +
    '`ls -d ~/.claude/plugins/cache/*/crew/*/hooks/scripts | sort -V | tail -1`; inside the crew repo itself, plugin/crew/hooks/scripts'}. ` +
  'Check that crew_wave.py is there; if not, return stop=true with stopReason naming what you tried.'

// ---- Start ---------------------------------------------------------------------------------
phase('Start')
const started = await agent(
  `You are in the main checkout. ${locate}\n` +
  `1. Run: python3 -B <scripts>/crew_wave.py start --root . --set ${slug} --json\n` +
  'The output is JSON with "stop", "stopReason", "plan" (its "maxLanes") and "launches": a list of ' +
  '{"ticket", "argv"}.\n' +
  '2. If "stop" is true, return stop=true, the stopReason, maxLanes=0 and lanes=[]. Run nothing else.\n' +
  '3. Otherwise, for each launches[i], run its argv as one command (each word one shell argument), in order, ' +
  'and capture its whole stdout unchanged: that is the lane prompt. Do not shorten, summarise or edit it.\n' +
  '4. Return stop=false, stopReason="", maxLanes = the JSON\'s plan.maxLanes, and lanes = ' +
  '[{ticket, prompt, model}] for every launches entry, in order (omit model when the entry has none). If a command failed, return stop=true with the ' +
  'command and its error as stopReason. Never launch or start anything yourself.',
  { label: `start ${slug}`, phase: 'Start', schema: START_SCHEMA },
).catch(() => null)

if (!isObject(started)) {
  return { error: 'start returned no result or a malformed result; nothing was launched' }
}
if (started.stop === true) {
  return { stop: true, error: `start stopped: ${text(started.stopReason) || 'no reason given'}`, lanes: [] }
}
if (typeof started.stop !== 'boolean' || !Array.isArray(started.lanes) ||
    !Number.isInteger(started.maxLanes) || started.maxLanes < 1) {
  return { error: 'start result is missing stop, lanes or a positive maxLanes; nothing was launched' }
}
for (const lane of started.lanes) {
  if (!isObject(lane) || typeof lane.ticket !== 'string' || !lane.ticket) {
    return { error: 'start result has a lane without a ticket; nothing was launched' }
  }
  if (typeof lane.prompt !== 'string' || !lane.prompt.trim()) {
    return { error: `start result has an empty lane prompt for ${lane.ticket}; nothing was launched` }
  }
}
const seen = new Set()
for (const lane of started.lanes) {
  if (seen.has(lane.ticket)) {
    return { error: `start result names ${lane.ticket} twice; nothing was launched` }
  }
  seen.add(lane.ticket)
}

// ---- Lanes ---------------------------------------------------------------------------------
phase('Lanes')
const maxLanes = started.maxLanes
const queue = started.lanes.slice()
const results = {}

const unknown = (ticket, reason) => ({ ticket, state: 'unknown', reason })

const runLane = async (lane) => {
  try {
    const options = { label: `lane ${lane.ticket}`, phase: 'Lanes', isolation: 'worktree', schema: LANE_SCHEMA }
    if (typeof lane.model === 'string' && lane.model) options.model = lane.model
    const got = await agent(lane.prompt, options)
    if (!isObject(got)) return unknown(lane.ticket, 'the lane agent returned no result')
    if (got.ticket !== lane.ticket) {
      return unknown(lane.ticket, `the lane agent reported ticket ${JSON.stringify(got.ticket)}`)
    }
    if (!LANE_STATES.includes(got.state)) {
      return unknown(lane.ticket, `the lane agent reported state ${JSON.stringify(got.state)}`)
    }
    return { ticket: lane.ticket, state: got.state, reason: text(got.reason) }
  } catch (error) {
    return unknown(lane.ticket, `the lane agent failed: ${error && error.message ? error.message : String(error)}`)
  }
}

const worker = async () => {
  while (queue.length > 0) {
    const lane = queue.shift()
    results[lane.ticket] = await runLane(lane)
  }
}

const workers = []
for (let i = 0; i < Math.min(maxLanes, started.lanes.length); i++) workers.push(worker)
await parallel(workers.map((run) => () => run()))

// ---- Collect -------------------------------------------------------------------------------
phase('Collect')
const launched = started.lanes.map((lane) => lane.ticket)
const collected = await agent(
  `You are in the main checkout. ${locate}\n` +
  `Run: python3 -B <scripts>/crew_wave.py collect --root . --set ${slug} --json\n` +
  'Return its JSON unchanged: the whole object, with its "lanes" list of {ticket, state, reason}. ' +
  'If the command fails, return lanes=[] and put its error in a "problems" list.',
  { label: `collect ${slug}`, phase: 'Collect', schema: COLLECT_SCHEMA },
).catch(() => null)

const merged = (report, error) => {
  const rows = []
  const byTicket = {}
  if (!error) for (const lane of report.lanes) byTicket[lane.ticket] = lane
  for (const ticket of launched) {
    const mine = results[ticket] || unknown(ticket, 'the lane never reported')
    const theirs = byTicket[ticket]
    if (mine.state === 'unknown') {
      rows.push(mine)
    } else if (error || !theirs) {
      rows.push(unknown(ticket, error ? 'collect was unreadable' : 'collect did not list this launched lane'))
    } else {
      rows.push({ ...theirs, reason: text(theirs.reason) })
    }
  }
  if (!error) {
    for (const lane of report.lanes) if (!launched.includes(lane.ticket)) rows.push({ ...lane, reason: text(lane.reason) })
  }
  return rows
}

const wellFormed = isObject(collected) && Array.isArray(collected.lanes) &&
  collected.lanes.every((lane) => isObject(lane) && typeof lane.ticket === 'string' && lane.ticket &&
    typeof lane.state === 'string' && lane.state)

if (!wellFormed) {
  return { error: 'collect unreadable', lanes: merged(null, true) }
}
return { ...collected, lanes: merged(collected, false) }
