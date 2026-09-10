# Screenshots: anonymisation and provenance

Two checks before any screenshot goes into a document. Both are easy to skip and both
caught real defects in the measured production set — real mailboxes, usernames, asset tags
and file paths shipped more than once.

## 1. Anonymise — and audit the whole image, not just the field you are fixing

Stand-ins come from the brand pack (`screenshots.stand_in_email`,
`screenshots.stand_in_user`; neutral: `firstname.lastname@example.com`, `user`). Use them
consistently so a reader recognises them as placeholders.

Edit with Pillow, using a system font that matches the UI in the capture
(`C:\Windows\Fonts\segoeui.ttf` for Windows dialogs), then **crop the edited region 3–4×
and look at it**: small white boxes clip callout borders and leave stray letters behind.

A mail-client screenshot carries identity in *every* pane — sender list, subject lines,
reading pane, title bar, taskbar, notification area. One was shipped with the obvious
mailbox replaced while a colleague's surname, an external domain and three e-mail subjects
sat in the message-list pane at the edge of the same capture. Found by a reviewer, not by
the person editing it.

**Crop away whatever the caption does not need.** It is safer than redacting it, and a
tighter crop is usually a better illustration anyway.

Things that count as identity and are routinely missed:

| Where | What leaks |
|---|---|
| Title bar, tab strip | account name, mailbox, document title |
| Status bar | signed-in user, sync state with account |
| Taskbar, system tray | other open applications, notification previews |
| File dialogs | `C:\Users\<name>\…`, share paths with server names |
| Device pages | asset tags, serial numbers, hostnames |
| Browser | URL with tenant name, bookmarks bar, profile avatar |

## 2. Check provenance

A screenshot recycled from another document often still carries *that* document's
annotations — arrows and highlight boxes pointing at steps yours never mentions. Open
every supplied image and confirm it depicts the steps it sits under. If it does not,
recapture rather than crop around the annotations; a partially visible arrow is worse
than none.

## Where source images live

Keep the source PNGs under the brand pack's `sop.assets_dir` as
`<assets_dir>\<sop-slug>\NN-what-it-shows.png` so a document rebuilds from its spec without
unpacking the `.docx`. `extract_spec.py` writes there when it pulls images out of an
existing master. This skill's own `assets/` holds only brand packs and the self-test
fixture — never production screenshots.

## Layout

Never exceed the 7.5" text column. `build_sop.py` scales down to 7.5" × 6.5"
automatically, never up; set `width_in` when a capture must stay readable at a particular
size. The border and the `wp:effectExtent` that keeps it from being clipped are applied
by the generator — never `add_picture()` by hand (see `template-spec.md`).
