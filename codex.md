# CODEx.md

## Feature: Monthly Housekeeping & Integrity Check

### Background

Evidence Vault has reached a stable MVP.

The goal is **not** to build a complicated forensic platform, but a lightweight, trustworthy, local-first evidence archive.

This feature introduces monthly integrity checking and archive housekeeping.

---

# Goals

Implement four new capabilities:

1. Monthly Integrity Check
2. Monthly Housekeeping
3. Archive Manifest
4. Hash-Chained Audit Events

No AI features.

No Maker-Checker workflow.

No cloud synchronization.

Keep everything simple.

---

# 1. Integrity Check

New command:

```bash
evidence integrity-check --month YYYY-MM
```

Example:

```bash
evidence integrity-check --month 2026-06
```

Only verify records belonging to that month.

Checks:

## Original File

Verify:

* file exists
* SHA256 matches database

If missing:

```
ERROR
Original file missing
```

If hash mismatch:

```
ERROR
Original file modified
```

---

## Metadata

Verify:

* metadata.json exists
* metadata references correct record
* metadata SHA256 matches original

---

## Duplicate Path

Ensure:

No imported file overwrote another original file.

---

## Result

Example output:

```
Integrity Check

Month:
2026-06

Records:
42

Passed:
42

Failed:
0

Vault Status:
HEALTHY
```

If any record fails:

```
Vault Status:
CORRUPTED
```

Return non-zero exit code.

---

# 2. Automatic Import Check

Before importing a new record:

Automatically run:

```
integrity-check(current_month)
```

Only the current month.

Do NOT scan the whole vault.

If integrity fails:

Abort import.

---

# 3. Monthly Housekeeping

New command:

```bash
evidence housekeep --month YYYY-MM
```

Execution order:

Step 1

Run integrity-check.

If failed:

Abort.

---

Step 2

Generate report.pdf.

---

Step 3

Generate:

manifest.json

Manifest should contain:

```
Month

Generated Time

Vault Version

Total Records

Total Audit Events

Total Trash Items

Original File List

Metadata File List

SHA256 of every file
```

---

Step 4

Generate:

manifest.sha256

This is the SHA256 checksum of manifest.json.

---

Step 5

Create archive:

```
archive/

2026-06.zip
```

Archive contains:

```
originals/

metadata/

audit/

trash/

report.pdf

manifest.json

manifest.sha256
```

---

Optional:

Support:

```
--encrypt
```

If enabled:

Prompt user for archive password.

Standard ZIP AES encryption is sufficient.

Do NOT implement one-time passwords.

Do NOT implement online verification.

---

# 4. Audit Event Ledger

Replace simple logs with append-only audit events.

Create table:

```
audit_events
```

Fields:

```
id

event_type

record_id

month

created_at

details_json

previous_hash

event_hash
```

Supported event types:

```
IMPORT

DELETE

RESTORE

INTEGRITY_CHECK

HOUSEKEEP

ARCHIVE_CREATED
```

Every event hash:

```
SHA256(
previous_hash
+
timestamp
+
event_type
+
details_json
)
```

Never update an audit record.

Never delete an audit record.

Append only.

---

# Design Principles

This project is NOT blockchain.

This project is NOT a distributed ledger.

This project is a lightweight local evidence archive.

Priorities:

1. Original files are immutable.

2. Metadata is reproducible.

3. Audit trail is append-only.

4. Monthly archive is self-contained.

5. Verification is simple and deterministic.

---

# Explicitly Out of Scope

Do NOT implement:

* Maker / Checker workflow
* Multi-user support
* Authentication
* Digital signatures
* Cloud synchronization
* AI analysis
* OCR
* Face recognition
* Semantic extraction
* Blockchain
* One-time password archive
* Online verification

Keep the implementation minimal, clean, and maintainable.
