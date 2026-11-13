# Changelog

## Unreleased

### Added

- Add `python -m src check`, a non-writing configuration check, and structured JSON logging for pipeline commands. `check` logs every effective non-secret setting with its source and a SHA-256 of the values (`config.effective`); run-record persistence remains PR2 work.
- Add versioned Bronze, Silver, and Gold row contracts, including `gold.market_1m`, with `validate_record` and `arrow_schema` APIs. Generate field documentation from the JSON registry.
- Add a network-free venue adapter and mock implementation, including Bronze provenance and explicit normalization failures. Adapters may declare no API version (`None`) instead of inventing one; Bronze records route by exact venue/API/protocol identity before envelope validation and content parsing. Validation rules come from the shared contracts instead of a per-adapter declaration. Read-only mapping proxies over plain dicts normalize like dicts; other mapping types are kept as original-reference evidence. Evidence is copied before routing.
- Add the `recovery/` area for conflicting writes and abandoned partial files, with checksums and recovery metadata. Coordinate cooperating writers with a lock file that fails immediately when held. Recovery metadata must record its recovery path and completion check.
- Document the foundation decisions in ADR-002 and describe the boundary between row-level contracts and future dataset validation.

### Changed

- Validate shared configuration with pydantic, distinguish read and write preflight checks, and check hard-link support before write jobs.
- Use scoped writer boundaries per data layer. Publish without replacement, synchronize file and parent directory, and preserve conflicting evidence for review.
- Upgrade contracts to schema version 7.0.0, require daily `as_of` to be no earlier than the start of its UTC day, declare row rules in JSON, preserve raw byte records, separate scheduled and actual market open/close times (keeping unclassified source time text verbatim), add optional source market/outcome descriptions and settlement rules, key outcomes by market, allow unknown settlement times, and use feature availability time for the first point-in-time check. A later training and backtest check will apply information delay.
- Keep legacy indexers separate from the new pipeline and document configuration, recovery, and the limits of the current foundation.
