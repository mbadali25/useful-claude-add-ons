---
description: Ask the local chat model a question about this repo, grounded in indexed excerpts
argument-hint: <question> [--k N] [--glob <pattern>]
allowed-tools: Read, Bash, Grep, mcp__localgpu__search_code
---

Put a question to `chat_model` on this machine's GPU, with excerpts from the local
index as its context. `$ARGUMENTS` is the question, plus the same `--k` and
`--glob` flags `/localgpu:search` takes.

Nothing leaves `127.0.0.1`. That is the point of the command, and it is also the
whole of its advantage — read the next section before using it for anything that
matters.

## What this model is for, and what it is not

`qwen2.5-coder:7b-instruct-q4_K_M` is a 7-billion-parameter model at 4-bit
quantization. It is fast, free, and private. It is also several tiers below the
model reading this command.

| Ask it | Do not ask it |
|---|---|
| "What does this module appear to do?" | "Is this change correct?" |
| "Which of these files is most likely to own X?" | "Review this diff" |
| "Summarize this function in one line" | "Is this a security problem?" |
| "Draft a docstring for this" | "Design the migration" |
| Triage: which of twenty files deserves a real read | Any decision that gets committed unreviewed |

The right frame is a fast first pass that narrows what the expensive model has to
look at. Anything where being wrong is expensive belongs to a frontier model, and
`/localgpu:crew` is where that boundary is written down.

## How to run it

1. Retrieve first. Call `search_code` with the question as the query. The chat
   model sees excerpts, not the repository.
2. If the retrieval is thin — few hits, weak scores — say so and stop. A 7B model
   handed poor context does not say "I do not know"; it produces a fluent answer
   about code it never saw, which is the single most expensive failure mode here.
3. Send the question plus the excerpts to `chat_model` at `ollama_url`, with
   `"keep_alive": "30s"` in the body. This is a one-shot question, not a session:
   the `5m` lease belongs to `localgpu shell`, where a person is typing between
   turns, and taking it here pins 4.7 GB against the next index run for five
   minutes over a single answer.
4. Report the answer **and the excerpts it was given**, as `file:line`.

Step 4 is not optional. An answer with its sources attached can be checked in
seconds; the same answer without them has to be re-derived from scratch, and the
user cannot tell which of the two they are reading.

## Attribute every answer

Label the output with the model that produced it, every time — `qwen2.5-coder:7b
(local)`. Never fold a local answer into your own prose as though you had
concluded it. A 7B claim inheriting a frontier model's credibility is how a wrong
answer gets acted on, and the label is the entire defence.

If the answer contradicts something you can check directly, check it and report the
contradiction. Do not relay it.

## VRAM

This loads the chat model, which is ~4.7 GB. On an 8 GB card with a display
attached, that means the embed model is being evicted to make room — expect the
retrieval in step 1 to be slower than usual if the chat model was already
resident, and expect the next `/localgpu:index` run to pay the load cost again.

Interleaving `/localgpu:ask` with an index build is the one combination to avoid.
Finish the build, then ask.

## When this is the wrong command

This relays one answer into the session you are in, and every relay costs you the
excerpt-gathering and the attribution above. Past two or three questions in a row,
that is the expensive way to do it: `localgpu shell` opens a **separate** Claude
Code session running entirely on the local model, so the back-and-forth never
touches this session's context at all. Say so instead of relaying a fifth answer.

It is a separate session on purpose, and it does not change this one. What it also
does not do is make a local model safe for gate work — a `/crew:*` command run
inside it is answered by the 7B and labelled like any other. `/localgpu:crew`.
