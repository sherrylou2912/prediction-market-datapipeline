# Changelog

## Unreleased

- Define v1 data contracts, configuration, directory permissions, and a versioned venue adapter interface.
- Add a network-free mock adapter and an architecture decision record.
- Move the pipeline into `src/`, split editable defaults into `src/config/defaults/storage.json` and `src/config/defaults/runtime.json`, and document the environment and test workflow.
- Separate configuration, read-only, and write preflight checks so low disk space does not block read-only work.
- Document the rule that future jobs validate tunable parameters before runs and log effective non-secret settings.
- Share data-root ancestor validation, document the scoped writer threat model, and test missing implementations of all eight adapter operations.
- Scope numeric row constraints by dataset and cover populated rows for all 13 v2 contracts, including text labels in Silver outcomes.
