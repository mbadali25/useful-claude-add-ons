# SNS alert-recipient subscribe (thd-refresh-alerts): what blocks automation

Priority: P2 (owner wants agents to run it, but two inputs are missing).
Status: needs ticket (no T-/L-/C- id yet). Recorded 2026-11-17 night from tonight's session findings. Priority is the recording agent's proposal under owner authorization; the owner may change it. Scale used: P1 (correctness or safety hole) / P2 (reliability or hygiene) / P3 (docs or cleanup).

Labels: VERIFIED = read or run by a session tonight and reported; INFERRED = reasoned, not run. The recording agent re-read only the spots named under 'Re-checked'; everything else is relayed.

Topic ARN (VERIFIED from the owner paste): `arn:aws:sns:us-east-1:718678532558:thd-refresh-alerts`. Owner said agents should run the subscribe. Extends `automate-aws-sns-subscribe-alert-recipients.md`.
Blockers: (1) recipient email addresses are not known (VERIFIED: none supplied); (2) no working AWS path: the AWS MCP failed to connect in this session (VERIFIED: server failure notice) and no aws command was run.
Acceptance: owner supplies the addresses; a working AWS path (MCP or CLI profile) is confirmed read-only first (`sts get-caller-identity`); subscribe runs through the approval route; each recipient confirms the emailed subscription (INFERRED: SNS email subscriptions stay pending until confirmed).
