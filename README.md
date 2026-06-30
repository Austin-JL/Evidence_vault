# Evidence Vault

Evidence Vault is a local-first CLI for preserving photo and video proof of real-world events.

It copies original media files into a managed archive, extracts available metadata, computes SHA256 hashes, records structured metadata in JSON and SQLite, keeps an operation audit log, and can generate date-based reports and ZIP evidence packages.

The current CLI uses `in` and `out` as simple event direction labels. They are intentionally lightweight labels, not a hard product boundary. The project can evolve toward a more general event model with event types, tags, categories, and workflows.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Basic Usage

Import an event file:

```bash
python -m app.main import --file ~/Downloads/IMG_3287.HEIC --direction in --date 2026-06-29
```

`--date` accepts either `YYYY-MM-DD` or compact `YYYYMMDD`.

Photos use EXIF metadata when available. Videos such as `.MOV` and `.MP4` use `ffprobe` when it is installed to read capture time, device tags, duration, and resolution. If no capture date is found, pass `--date` explicitly.

Import another event file with a note:

```bash
python -m app.main import --file ~/Downloads/IMG_3299.HEIC --direction out --date 2026-06-29 --note "Supporting event record"
```

List records for a month:

```bash
python -m app.main list --month 2026-06
```

Generate a monthly PDF report:

```bash
python -m app.main report --month 2026-06
```

Export a monthly ZIP package:

```bash
python -m app.main archive --month 2026-06
```

Run a monthly integrity check:

```bash
python -m app.main integrity-check --month 2026-06
```

Run monthly housekeeping, which performs integrity checking, report generation, manifest generation, and archive export:

```bash
python -m app.main housekeep --month 2026-06
```

## Safe Removal

Remove an imported record by ID:

```bash
python -m app.main remove --id 2
```

Removal shows the record details and requires typing `DELETE`. Existing original files and metadata are moved to `data/trash/` with a `removed_record.json` audit file instead of being directly discarded.

Refresh metadata for an existing record after extractor improvements:

```bash
python -m app.main refresh-metadata --id 7
```

Refresh verifies that the stored original still matches the recorded SHA256 before updating the database fields and JSON sidecar.

## Edit/View Mode

Configure passcode-gated edit mode:

```bash
python -m app.main mode set-passcode
python -m app.main mode edit
python -m app.main mode view
python -m app.main mode status
```

After a passcode is configured, `import`, `remove`, and `refresh-metadata` are allowed only in edit mode. Read-only commands such as `list`, `integrity-check`, `report`, `archive`, `housekeep`, and `audit` remain available in view mode.

Edit mode is short-lived: it expires after 5 minutes and automatically returns to view mode after one successful `import` or `remove`.

## Operation Log

View the operation log:

```bash
python -m app.main audit
python -m app.main audit --action import
python -m app.main audit --status failed
```

Each CLI operation writes an entry to `operation_log`, including actor, action, status, timestamp, target record, and non-secret details. The default actor is the current system user. To set an explicit actor for a command:

```bash
EV_ACTOR="Austin" python -m app.main import --file ~/Downloads/IMG_3287.HEIC --direction in --date 2026-06-29
```

## Data Location

Runtime data is stored under `data/`:

```text
data/
  originals/
  metadata/
  reports/
  archives/
  trash/
  evidence.db
  mode.json
```

The `data/` directory is intentionally ignored by Git because it may contain private files, personal metadata, passcode state, and audit records.

## Integrity Model

Evidence Vault currently provides local integrity controls:

- original files are copied and not modified in place
- duplicate imports are rejected by SHA256
- metadata and database records store SHA256 hashes
- removal is confirmed and moved to trash with an audit file
- operations are logged in SQLite
- monthly integrity checks verify original files, metadata sidecars, hashes, and duplicate stored paths
- monthly archives include a manifest and manifest checksum
- audit events are appended with hash chaining
- edit mode reduces accidental modification risk

These controls are useful for personal organization and tamper-evident record keeping, but they are not tamper-proof against the same operating-system user who owns the files. A future stronger model should add external trust anchors such as hash-chain manifests, signed digests, immutable storage, or timestamped commits to a remote repository.
