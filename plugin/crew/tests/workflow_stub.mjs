// A stub of the Claude Code workflow runtime, enough to run plugin/crew/workflows/*.js under node.
//
//   node workflow_stub.mjs <workflow.js> <scenario.json>
//
// scenario.json: {"args": <value>, "agents": [{"match": "<label prefix>", "result": <value>}
//                  | {"match": ..., "reject": "<message>"} | {"match": ..., "raw": <value>}], "delayMs": 5}
// Each agent() call takes the first scripted entry whose `match` is a prefix of the call's label
// and runs it; a call with no entry rejects (so a workflow cannot pass by an unscripted agent).
// Prints one JSON line: {"result", "thrown", "calls": [{label, prompt, options}], "peak"}.
import { readFileSync } from 'node:fs'

const [, , workflowPath, scenarioPath] = process.argv
const scenario = JSON.parse(readFileSync(scenarioPath, 'utf8'))
const source = readFileSync(workflowPath, 'utf8')

const calls = []
let running = 0
let peak = 0

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

const agent = async (prompt, options = {}) => {
  const label = options.label || ''
  calls.push({ label, prompt, options })
  running += 1
  peak = Math.max(peak, running)
  try {
    await sleep(scenario.delayMs ?? 5)
    const entry = (scenario.agents || []).find((candidate) => label.startsWith(candidate.match))
    if (!entry) throw new Error(`no scripted agent for label ${JSON.stringify(label)}`)
    if ('reject' in entry) throw new Error(entry.reject)
    if ('raw' in entry) return entry.raw
    return entry.result
  } finally {
    running -= 1
  }
}

// parallel(): all thunks, a throwing thunk resolves to null, as the real runtime does.
const parallel = (thunks) => Promise.all(thunks.map((thunk) => Promise.resolve().then(thunk).catch(() => null)))

const pipeline = async (items, ...stages) => Promise.all(items.map(async (item, index) => {
  try {
    let value = item
    for (const stage of stages) value = await stage(value, item, index)
    return value
  } catch {
    return null
  }
}))

const body = source.replace(/^export const meta\s*=/m, 'const meta =')
const AsyncFunction = Object.getPrototypeOf(async () => {}).constructor
const run = new AsyncFunction('agent', 'parallel', 'pipeline', 'phase', 'log', 'args', 'budget', body)

let result = null
let thrown = null
try {
  result = await run(agent, parallel, pipeline, () => {}, () => {}, scenario.args,
    { total: null, spent: () => 0, remaining: () => Infinity })
} catch (error) {
  thrown = String(error && error.message ? error.message : error)
}
process.stdout.write(JSON.stringify({ result, thrown, calls, peak }) + '\n')
