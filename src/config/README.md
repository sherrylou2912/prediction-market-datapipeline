# Pipeline Configuration

Edit `defaults/storage.json` for disk capacity policy and `defaults/runtime.json` for runtime defaults. These files contain non-secret defaults and are version controlled. The six data layer names and schema contracts are fixed architecture rules, so they are not editable settings.

The pipeline loads `src/config/defaults/` by default. Set `PIPELINE_CONFIG_DIR` to an absolute path to use another directory containing both files.

Precedence is: process environment, local `.env`, then these JSON files. `DATA_ROOT` has no file default and must be set in the environment or local `.env`. The environment overrides are `DATA_MIN_FREE_GIB` and `PIPELINE_LOG_LEVEL`; an empty value falls back to the JSON default.

Keep credentials only in environment variables or the ignored local `.env`. Copy `.env.example` to `.env` and fill in the keys needed by your workflow. The pipeline reads `.env` without copying secret values into `PipelineConfig` or printing them.

The loader rejects missing files, malformed JSON, unexpected keys, wrong types, and invalid values with a configuration error. Run `python -m src check` after changing either file. This command checks configuration and path suitability only; it does not check free disk space, test write access, or create directories.

Read-only jobs call `PipelineConfig.validate_for_read()` to require an existing readable `DATA_ROOT`. Write-producing jobs call `PipelineConfig.validate_for_write()` to check the `storage.json` free-space threshold, create the root if needed, and test actual write access. They then call `DataLayout.create()` to prepare the six data layers. A read-only job does not need the free-space threshold to be met.
