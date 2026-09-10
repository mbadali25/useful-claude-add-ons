# Operator safety: the irreversible steps and their gates

Shared by `exchange-mailbox-cleanup` and `exchange-mailbox-restore`. None of the commands below have
a `ShouldProcess` gate the skill can rely on - `Remove-MgUser -Confirm` is a Y/N the operator can
reflex through, `New-Mailbox -InactiveMailbox` has none, `Set-Mailbox -LitigationHoldEnabled $false`
has none. **The gate lives in the conversation.** Follow these scripts exactly.

## Rules that apply to every gate

1. **Say what is about to happen in the operator's words**, with the count and what is lost. Not
   "this will call Remove-MgUser". "This will permanently delete 3 accounts. Their mailboxes are on
   hold, so the mail is kept; their sign-in, OneDrive and Teams chat are not."
2. **Require a typed phrase that includes the count.** `DELETE 3`, `RECOVER 1`, `DESTROY 1`. A bare
   `yes`, `y`, `ok`, `go ahead`, `proceed` or an empty reply does **not** proceed. Say so and re-ask.
3. **Never make the destructive path the default.** Do not print a command with `-Confirm:$false`.
   Do not put the destructive command in the same block as a read. One command, one gate.
4. **One mailbox first, then the rest.** For any batch, gate and run the first identity alone, take
   it through the validating phase, and only then gate the remainder as a second batch.
5. **Refuse on a wrong precondition, do not warn.** If the precondition below is not met, do not
   print the command at all. Tell the operator which check failed and which step fixes it.
6. **Record the gate in the ticket.** Who typed the phrase, when, against which list. Run
   `ticketctl.py redact-check --emit` on the note first.

## Gate 1 - Account deletion (cleanup, Step 30)

**Precondition (all must be true, from the artifacts, not from memory):**

- `Test-MailboxPreservation.ps1` CSV for this identity shows `Verdict = PreservedReadyToDelete`
  and `SafeToDeleteAccount = True` (Step 21).
- `Get-M365OffboardingStatus.ps1` CSV shows `Stage2Ready = True` and `BlockingIssue` empty (Step 26).
- `OnPremisesSyncEnabled` is known for this identity (Step 27) - `True` routes to on-prem AD,
  `False`/empty routes to Entra.
- Sign-off is recorded in the ticket (Step 28).
- A baseline `ItemCount` is written down (Step 21).

**Script:**

> Step 30 of 41. This is the point of no return.
>
> I am about to have you delete **{N}** account(s): {list of UPNs}.
>
> What is kept: each mailbox is on Litigation Hold (verified at Step 19 and Step 21), so it becomes
> an *inactive mailbox* - preserved for seven years and searchable in Purview. The licence seat is
> released.
>
> What is lost: the person's sign-in, OneDrive files, Teams chats and group memberships. The Entra
> object can be undeleted for 30 days; after that it cannot.
>
> {If any is on-prem synced:} {M} of these are mastered in on-premises AD. Deleting them in Entra
> would be undone at the next sync, so those are deleted in AD and then synced - I will print that
> separately.
>
> To proceed, type exactly: **DELETE {N}**
> To stop, type anything else.

On `DELETE {N}` with the right N: print **only** the command for the first identity. On anything
else: "Stopped. Nothing was deleted." and stay at Step 29.

**Commands (one identity at a time):**

Cloud-only (`OnPremisesSyncEnabled` False or empty):

```powershell
Remove-MgUser -UserId "first.last@contoso.com" -Confirm
```

On-prem synced (`OnPremisesSyncEnabled = True`) - on a domain-joined host with RSAT, **as the
operator**, then on `AWSPRDINFAAD01`. Say the machine boundary out loud: *"This one step runs on
the server AWSPRDINFAAD01. Connect with Remote Desktop, open the same blue Windows PowerShell
window there, run the two ADSync lines, then come back to your own PC."*

```powershell
# On a domain-joined admin host
Get-ADUser -Identity "first.last" -Properties UserPrincipalName, Enabled | Format-List
Remove-ADUser -Identity "first.last" -Confirm

# On AWSPRDINFAAD01, blue Windows PowerShell window - ADSync has no PowerShell 7 build
Import-Module ADSync
Start-ADSyncSyncCycle -PolicyType Delta
```

Then wait until `Get-MgUser -UserId "first.last@contoso.com"` returns `Request_ResourceNotFound`
before treating the cloud object as gone.

## Gate 2 - Recover an inactive mailbox (restore, Path 3)

**Precondition:**

- `MailboxState = Inactive` from `Test-MailboxPreservation.ps1` (Step 0) - not `SoftDeleted`, not
  `Active`.
- The `ExchangeGuid` is recorded and is the identity used in the command.
- The requester has confirmed in writing that **nobody** needs the preserved copy for legal or HR.
  If there is any doubt, Path 2 (restore a copy into a shared mailbox) is the answer and this gate
  is not reached.
- The directory decision is made (Path 3, step 3.2): on-prem user created and synced first, or
  cloud-only.

**Script:**

> Path 3, step 3.3. This consumes the preserved mailbox.
>
> Recovering **{DisplayName}** ({ExchangeGuid}) turns the inactive mailbox back into a normal
> licensed mailbox for the returning person.
>
> What is lost: the *preserved copy* ceases to exist and the Litigation Hold goes with it. If a
> legal or HR matter later needs the mailbox as it stood on {WhenSoftDeleted}, there will be nothing
> to produce. Path 2 (copy into a shared mailbox, hold untouched) is the alternative and is still
> available right now.
>
> To proceed, type exactly: **RECOVER 1**
> To take Path 2 instead, type **PATH 2**. Anything else stops.

## Gate 3 - Permanent destruction (restore, Path 5)

**Precondition:**

- Written authorisation exists, naming who authorised it, when, and against which retention
  schedule. Ask for the reference and record it in the ticket **before** printing any command.
- The four-way hold check (Path 5, step 5.1) shows only Litigation Hold remaining. If `InPlaceHolds`
  still lists a `UniH` or `mbx` entry, removing Litigation Hold changes nothing - and that is a
  safety feature. Stop and release the other holds first, through their own owners.
- `ExchangeGuid` recorded.
- The `-RemoveDelayHoldApplied` / `-RemoveDelayReleaseHoldApplied` parameters have been checked
  against current Microsoft Learn this session.

**Script:**

> Path 5, step 5.2. This is permanent destruction. There is no undo and no Microsoft support path.
>
> Removing the last hold from **{DisplayName}** ({ExchangeGuid}) starts the purge. After the delay
> hold clears (~30 days, or immediately if you also clear it at step 5.3) the mailbox and every item
> in it are gone.
>
> Authorisation on file: {reference}. Retention schedule: {schedule}.
>
> To proceed, type exactly: **DESTROY 1**
> Anything else stops, and nothing has changed.

## Not a gate - a refusal: licence removal

The operator will ask, at some point, to "just remove the licence" to free the seat. Do not gate
this. **Refuse it**, every time, with:

> Removing the licence from a live mailbox soft-deletes the mailbox and purges it in 30 days, and
> the Litigation Hold does not prevent that. The seat is released by *deleting the account* (Phase
> C), which turns the mailbox inactive and keeps the mail. I will not print a licence-removal
> command. Shall we continue to Step {n}?

The only licence decision in either runbook is `restore` Path 1, step 1.4 - and there the skill
prints `Get-MgUserLicenseDetail` (a read) and says the seat is the person's to keep or hand back
through normal licensing, **only after** step 1.3 shows no hold of any kind remains.

## Not a gate - a refusal: the deprecated export script

`Export-Terminated-Mailbox-to-PST.ps1` is marked deprecated and throws on execution. Never print it,
never suggest it as "the old way". Export is a Purview portal action (`runbook-steps.md` Step 39)
and the runbook's stated preference is to **not export at all** - restore into a shared mailbox
instead (`exchange-mailbox-restore` Path 2).

## Steps that are reversible but still need a stated count

These get a plain confirmation, not a typed phrase, but the count must be stated first:

| Step | What to say |
|---|---|
| Hold apply (cleanup Step 17) | "This applies a seven-year hold to {N} mailboxes and assigns a temporary {Sku} seat to any that lack one. Reversible with `restore` Path 1. Continue?" |
| eDiscovery grant (cleanup Step 13) | "This makes {Admin} an eDiscovery Manager. They can then search every mailbox they are granted. Continue?" |
| Restore request (restore Path 2, step 2.3) | "This copies {ItemCount} items from the inactive mailbox into `{target}`. The source is untouched. Continue?" |
| Hold removal on an **active** mailbox (restore Path 1, step 1.2) | "This removes Litigation Hold from {User}. Items past their retention age become deletable on the next pass. `InPlaceHolds` shows {decoded list}. Continue?" |
