# Changelog

## Unreleased

- Define v1 data contracts, configuration, directory permissions, and a versioned venue adapter interface.
- Add a network-free mock adapter and an architecture decision record.
- Move the pipeline into `src/`, split editable defaults into `src/config/defaults/storage.json` and `src/config/defaults/runtime.json`, and document the environment and test workflow.
- Separate configuration, read-only, and write preflight checks so low disk space does not block read-only work.
