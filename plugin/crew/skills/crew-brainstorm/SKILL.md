---
name: crew-brainstorm
description: Turn a request into an approved direction before it becomes a spec - one question per message, options with the recommendation first, never implement before approval. Use at the start of any ticket that is not a known-cause one-subsystem fix.
---

# crew-brainstorm

**Adapted from `superpowers:brainstorming` by Jesse Vincent, MIT licensed. The
full copyright and permission notice is in `plugin/crew/NOTICE.md`.** Upstream:
<https://github.com/obra/superpowers>. The core rules below - one question per
message, recommendation-first options, approval as a hard gate - are
upstream's. What crew changed: upstream classifies every request into
spike/bounded/architectural paths with different artifacts; crew already has
that split at the command layer (`/crew:fix` is the light path, this skill is
the full one), so this rewrite is one path, sized down, ending in one artifact
(`direction.md`) instead of three.

Backs `/crew:brainstorm`. That command owns minting the ticket id and writing
the file; this skill is the method for the conversation in between.

## Core principle

The outcome your human partner can recognize and correct, not the one you
assumed. Ask, don't guess; write it back, don't paraphrase silently.

## The method

1. **Discover intent.** Use the request and whatever context is already
   available to identify the outcome, who it's for, what success looks like.
   Missing purpose gets one focused question before you propose anything.
2. **One question per message, always.** Never a batch, never two questions
   folded into one message hoping to save a round trip - that costs more
   corrections than it saves turns. Prefer multiple choice; open-ended is
   fine when there's no natural option set.
3. **Explore before asking, when the answer is in the repo.** "What does this
   already do" is not a question for the human - use `crew:explorer`, and
   keep what it returns local to this session; only the question it
   sharpens goes back to the human.
4. **Propose 2-3 approaches, recommendation first.** Trade-offs, then your
   pick and why. Lead with the recommendation, not a neutral list the human
   has to rank themselves.
5. **YAGNI ruthlessly.** Strip features that don't serve the stated outcome
   from every approach, including the recommended one.
6. **Write it back.** Once the shape is settled, write the direction (the
   command's `direction.md` template: Ask, Options, Recommendation, Open
   questions) and show it.

## The hard gate

**Before any implementation action** - writing product code, scaffolding,
invoking `/crew:spec` or `/crew:plan` - the human approves the written
direction. A reply approving the idea does not approve an artifact that does
not exist yet: approve the direction specifically, not the conversation that
led to it.

**The ratchet is one-way.** Hidden complexity discovered after approval (a
second subsystem, an unstated dependency) reopens this phase - stop, say so,
propose the revised direction, get it approved again. Nothing about
"we're basically done" downgrades that back to a nod.

## Red flags

| Thought | Reality |
|---|---|
| "This is obvious, I'll skip straight to a spec" | Obvious-to-you is not agreed-by-them. Write it back anyway. |
| "I asked three things in one message to save a round trip" | That's not fewer questions, it's one question with two others hidden inside it, waiting to be re-asked when the answer to the first changes the other two. |
| "They approved the idea in one line, that covers the design" | Approval of scope is not approval of a design that doesn't exist yet. |
| "It grew, but I'm close, no need to redo this" | Redo it. A direction approved for a smaller change is not a direction for this one. |

## Working in existing codebases

Explore current structure before proposing anything. Follow existing
patterns. Where existing code has a problem that affects this work, name it as
part of the direction - not as an unrelated refactor bolted onto the reply.
