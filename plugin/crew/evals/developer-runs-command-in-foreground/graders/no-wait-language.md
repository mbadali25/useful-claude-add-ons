---
type: regex
target: last_message
pattern: "(?<!(?:no need to|not|never|without)[\\s\\S]{0,12})\\b(?:I(?:'ll| will| am|'m) (?:wait|waiting)\\b|waiting for (?:the )?(?:completion|notification)\\b)"
flags: i
match: not_contains
---

The final reply doesn't commit to waiting for a background job or
notification — because there shouldn't be one to wait for.

Round 5: the prior version (`wait for|notification|check back|let you know
when`, bare substrings) rejected a correct reply that ran the command in
the foreground, reported its output, and *explicitly said there was
nothing to wait for* — "No need to wait for a notification." — because
"wait for" and "notification" are both literally present in that sentence
regardless of the "no need to" in front of them. The trigger is now scoped
to the actual first-person commitment ("I'll wait", "I will wait", "I am
waiting", "I'm waiting") or a bare "waiting for the completion/notification"
construction, and neither counts if a negation ("no need to", "not",
"never", "without") appears within the twelve characters before it.
