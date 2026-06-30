# Evidence Vault Design

Evidence Vault is a local-first command-line application for preserving photo and video evidence. It copies originals into a managed `data/` tree, extracts available metadata, records structured state in SQLite and JSON sidecars, logs operations, and produces monthly reports and ZIP evidence packages.

The application is intentionally small: `app/main.py` owns the CLI surface, and each supporting module owns one operational concern such as importing, metadata extraction, integrity checks, archiving, or edit-mode control.

## Runtime Data Model

Runtime data is stored under `data/`, which is ignored by Git because it may contain private evidence, audit records, and passcode state.

```text
data/
  originals/   Imported original media files, organized by date
  metadata/    JSON sidecars, organized by date
  reports/     Generated monthly PDF reports
  archives/    Monthly ZIP packages and manifest files
  trash/       Removed records and removal audit snapshots
  evidence.db  SQLite database
  mode.json    Optional edit/view-mode passcode state
```

SQLite stores two main kinds of records:

- `evidence_records`: active evidence rows with date, direction, source filename, stored paths, SHA256, extracted metadata, and optional note.
- `operation_log`: command-level log entries containing actor, action, target, status, timestamp, and JSON details.

`app/audit.py` also creates `audit_events`, a hash-chained event table used by integrity, import, delete, housekeeping, and archive workflows.

## Command Flow

`python -m app.main ...` is the only user-facing entry point.

Most commands follow this pattern:

1. Parse arguments in `app/main.py`.
2. Call a focused service module.
3. Print a human-readable result.
4. Write an `operation_log` row.
5. For evidence lifecycle events, append a hash-chained `audit_events` row.

Mutating commands are guarded by edit mode when a passcode is configured. `import`, `remove`, and `refresh-metadata` call `require_edit_mode()`. After successful `import` and `remove`, edit mode is locked back to view mode.

## Module Map

### `app/main.py`

CLI orchestration layer.

- Builds the `argparse` command tree.
- Dispatches subcommands to service modules.
- Formats records, integrity results, housekeeping results, and operation logs for terminal output.
- Logs command success/failure through `app.audit.log_operation`.
- Appends lifecycle audit events through `app.audit.append_audit_event`.
- Runs a current-month integrity check before import and aborts if the current month is corrupted.

Important commands:

- `import`
- `list`
- `report`
- `archive`
- `integrity-check`
- `housekeep`
- `remove`
- `refresh-metadata`
- `mode`
- `audit`

### `app/config.py`

Central path and constant definitions.

- Defines `PROJECT_ROOT`, `DATA_DIR`, and all data subdirectories.
- Defines `DB_PATH`, `MODE_PATH`, and valid direction labels.
- Provides `ensure_data_dirs()` so modules can safely create required runtime directories before reading or writing data.

### `app/db.py`

SQLite persistence for active evidence records and the command operation log schema.

- Opens SQLite connections with `sqlite3.Row` results.
- Ensures the base schema exists when connecting.
- Inserts, fetches, deletes, updates, and lists evidence records.
- Lists records by month using date range boundaries.
- Finds duplicate imports by SHA256.

This module is intentionally narrow: it does not know how to copy files, extract metadata, build reports, or enforce edit mode.

### `app/importer.py`

Evidence import workflow.

- Validates the source file and `direction`.
- Computes the source file SHA256.
- Rejects duplicate imports by hash.
- Extracts media metadata with `app.metadata.extract_file_metadata`.
- Resolves the record date from `--date` or captured metadata.
- Copies the original into `data/originals/YYYY/MM/DD/`.
- Writes a JSON sidecar into `data/metadata/YYYY/MM/DD/`.
- Inserts the active record into SQLite.

Path naming uses `in.ext`, `out.ext`, then numbered variants like `in_2.ext` when a date/direction filename already exists.

### `app/metadata.py`

Media metadata extraction and sidecar construction.

- Detects MIME type from filename.
- Extracts image EXIF data with Pillow when available.
- Registers HEIF support through `pillow-heif` when installed.
- Extracts video metadata with `ffprobe` when available.
- Normalizes capture time, GPS, device model/software, file size, media type, duration, and resolution.
- Builds the JSON structure written beside imported evidence.

Extraction is best-effort. If a parser or optional dependency is unavailable, the module returns basic file metadata instead of failing the import.

### `app/hashing.py`

SHA256 helpers.

- `sha256_file(path)` streams files in 1 MB chunks.
- `sha256_bytes(data)` hashes in-memory bytes, used for manifest checksums.

Hashes are the main local integrity signal used across import, metadata, integrity checks, and archive manifests.

### `app/integrity.py`

Monthly integrity verification.

- Validates `YYYY-MM` input.
- Loads active records for the month.
- Checks duplicate stored paths.
- Verifies original file existence and SHA256.
- Verifies metadata sidecar existence, valid JSON, expected record fields, and matching SHA256.
- Returns a structured result with record counts, issue list, and `HEALTHY` or `CORRUPTED` status.

The CLI returns a non-zero exit code when this module reports failures.

### `app/report.py`

Monthly PDF report generation.

- Lists records for a month.
- Groups records by record date.
- Writes `data/reports/YYYY-MM.pdf`.
- Uses ReportLab when installed.
- Falls back to a small built-in text-only PDF writer when ReportLab is unavailable.

Reports include date, generation time, total records, direction, captured time, GPS, SHA256, media label, and filename.

### `app/archive.py`

Monthly evidence package generation.

- Generates or refreshes the monthly report.
- Builds a manifest containing records, originals, metadata, trash files, and audit events for the month.
- Computes SHA256 values for manifest-listed files.
- Writes `data/archives/YYYY-MM.zip`.
- Writes standalone manifest files:
  - `data/archives/YYYY-MM-manifest.json`
  - `data/archives/YYYY-MM-manifest.sha256`

The ZIP contains original files, metadata files, audit events, matching trash files, `report.pdf`, `manifest.json`, and `manifest.sha256`.

### `app/housekeeping.py`

Monthly maintenance workflow.

- Runs `integrity.check_month(month)` first.
- Aborts if integrity fails.
- Generates the monthly report.
- Generates the monthly archive and manifest files.
- Returns a structured result with paths and status.

This module is deliberately small because report and archive details live in their own modules.

### `app/remover.py`

Safe active-record removal.

- Requires edit mode.
- Loads the target record.
- Moves original and metadata files to a timestamped directory under `data/trash/`.
- Writes `removed_record.json` with the removed database row and file movement details.
- Deletes the row from `evidence_records`.

The CLI asks the user to type `DELETE` unless `--yes` is passed.

### `app/refresher.py`

Metadata refresh workflow for existing records.

- Requires edit mode.
- Loads the target record.
- Verifies the stored original exists.
- Recomputes SHA256 and refuses to continue if the file no longer matches the database.
- Re-extracts metadata from the current extractor implementation.
- Rewrites the JSON sidecar.
- Updates selected metadata columns in SQLite.

This is useful after improving EXIF or video extraction support.

### `app/mode.py`

Passcode-gated edit/view mode.

- Without `data/mode.json`, the app behaves as unlocked for backward compatibility.
- `set_passcode()` creates salted PBKDF2 passcode state and locks to view mode.
- `enter_edit_mode()` verifies the passcode and grants edit mode for five minutes.
- `require_edit_mode()` blocks mutating commands when locked or expired.
- `lock_edit_mode()` returns to view mode after successful mutating workflows.

The passcode state is local protection against accidental modification, not a cryptographic boundary against the operating-system user.

### `app/audit.py`

Operational and lifecycle audit logging.

- Provides `log_operation()` for command-level logs.
- Provides `append_audit_event()` for hash-chained lifecycle events.
- Reads actor identity from `EV_ACTOR` or the current system user.
- Supports filtering operation logs by action and status.
- Supports listing and counting audit events by month for manifests.

Audit event hashes are chained by storing the previous event hash and hashing it with the new event timestamp, type, and details JSON.

### `app/__init__.py`

Package marker for `app`.

It contains no runtime logic.

## Integrity Boundaries

Evidence Vault provides local tamper-evident controls:

- originals are copied into managed storage
- duplicate imports are rejected by SHA256
- JSON sidecars and SQLite rows carry matching hashes
- integrity checks verify active originals and metadata
- removal moves files to trash and records the removed row
- lifecycle audit events are hash-chained
- monthly archives include manifests and manifest checksums

These controls are useful for personal record keeping, but they are not tamper-proof against the same OS user who can edit the database, files, and code. Stronger external trust would require signed manifests, immutable storage, remote timestamping, or another trust anchor outside the local workspace.

## Typical Workflows

### Import

```text
main.import
  require_edit_mode
  integrity.check_month(current_month)
  importer.import_evidence
    hashing.sha256_file
    db.find_by_sha256
    metadata.extract_file_metadata
    copy original
    write metadata JSON
    db.insert_record
  audit.log_operation
  audit.append_audit_event
  mode.lock_edit_mode
```

### Monthly Housekeeping

```text
main.housekeep
  housekeeping.housekeep_month
    integrity.check_month
    report.generate_monthly_report
    archive.export_monthly_archive
      archive.build_monthly_manifest
      audit.list_audit_events
      audit.count_audit_events
      hashing.sha256_file / sha256_bytes
  audit.log_operation
  audit.append_audit_event
```

### Removal

```text
main.remove
  db.get_record
  user confirmation
  remover.remove_record
    require_edit_mode
    move original and metadata to trash
    write removed_record.json
    db.delete_record
  audit.log_operation
  audit.append_audit_event
  mode.lock_edit_mode
```
