# Docker Desktop socket startup failure on Windows

The local machine encountered Windows error 1920 on two stale AF_UNIX endpoints:
`%LOCALAPPDATA%\Docker\run\dockerInference` and
`%LOCALAPPDATA%\docker-secrets-engine\engine.sock`.
This happens before the Linux engine pipe is available and is separate from the
application's container configuration. A related [Docker issue](https://github.com/docker/desktop-feedback/issues/460)
describes the failure class.

Recovery performed on 1 November 2026:

1. Confirmed the engine was unavailable and closed the failed Desktop startup.
2. Inspected the affected directories. The Secrets Engine directory contained only
   its transient `engine.sock` endpoint, not credential records.
3. Backed up both runtime IPC directories together under timestamped sibling names.
4. Recreated the two empty runtime directories and restarted Docker Desktop.
5. Verified that the engine responded with version 29.1.3.

Backing up only one directory at a time was insufficient: the next failed startup
could strand the other endpoint again. No factory reset, data purge, pruning,
WSL unregister, or image/volume deletion was performed. Backups remain in place.

If this Windows failure recurs, stop the failed Desktop instance before touching
runtime files. Do not rename image storage, VHDX files, containers or volumes.
If a reversible IPC-only repair is insufficient, an orderly Windows restart may
be required; it is not performed automatically by this project.
