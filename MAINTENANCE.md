# Routine maintenance

Use synthetic folders and a disposable destination when validating changes to the transfer scripts. Production database exports and personal project directories are not needed for routine checks.

## Review before running

- Inspect changes to `send.py` and `receive.py`, especially destination paths, archive handling, pairing, and network timeouts.
- Confirm that the README examples still match the supported command-line options.
- Keep changes to file transfer behavior separate from database-export changes.

## Manual validation checklist

- Start with the sender's documented dry-run mode and disable database export with `--no-db`.
- Use a small synthetic folder with nested directories, empty files, and names containing spaces or non-ASCII characters.
- Verify transferred contents and checksums at a disposable destination.
- Interrupt a transfer, reconnect, and check that resume skips completed files without corrupting partial files.
- Check that failed or locked files are reported clearly.
- Check that a silent connection does not prevent a later sender from connecting.
- Verify the documented default exclusions for dependency and build directories.

## Pull request evidence

Record the operating systems and Python versions used, the synthetic fixture, the checks actually completed, and any unresolved cases. Do not include pairing codes, database dumps, or private file contents in logs or screenshots.

This document is a maintenance procedure; it is not a record of a completed transfer test.
