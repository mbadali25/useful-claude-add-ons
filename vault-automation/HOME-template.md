---
cssclasses: [wide]
---

# 🏠 Vault Dashboard

> Auto-maintained by Dataview. Health queries below surface what needs gardening.

## Active projects (touched in the last 14 days)

```dataview
TABLE WITHOUT ID file.link AS Concept, status AS Status, updated AS Updated, observation_count AS Obs
FROM "wiki/concepts"
WHERE startswith(file.name, "Project - ") AND updated >= date(today) - dur(14 days)
SORT updated DESC
```

## 🥀 Stale: developing concepts untouched 30+ days

```dataview
TABLE WITHOUT ID file.link AS Concept, updated AS "Last updated"
FROM "wiki/concepts"
WHERE status = "developing" AND updated < date(today) - dur(30 days)
SORT updated ASC
LIMIT 15
```

## ⚠️ Unsourced concepts (recall treats these as unsupported)

```dataview
TABLE WITHOUT ID file.link AS Concept, status AS Status
FROM "wiki/concepts"
WHERE !sources OR length(sources) = 0
SORT file.name ASC
LIMIT 15
```

## 📅 Recent daily notes

```dataview
LIST
FROM "wiki/daily"
SORT file.name DESC
LIMIT 7
```

## 🗺️ Maps (canvases)


## 📥 Reflection queue

![[pending-reflect]]

---
*Pipeline: sessions auto-queue via SessionEnd/PreCompact hooks → nightly gardener runs /reflect → concepts gain sources and statuses → this page reflects the result. Vault synced by Obsidian Sync; optional git layer adds history (obsidian-git 15-min auto-commit) when installed with -UseGit.*
