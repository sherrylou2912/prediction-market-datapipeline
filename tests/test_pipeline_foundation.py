"""Acceptance tests for the first v1 architecture PR."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pytest

from src.adapters.base import VenueAdapter
from src.adapters.mock import MockVenueAdapter
from src.cli import main
from src.config.settings import ConfigError, PipelineConfig
from src.data_io.layout import DataLayout, WriteBoundaryError, WriterRole
from src.data_schema.contracts import (
    SCHEMA_REGISTRY,
    SCHEMA_VERSION,
    ContractError,
    arrow_schema,
    get_contract,
    validate_record,
)


def test_config_requires_absolute_data_root_and_reports_unwritable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ConfigError, match="DATA_ROOT is required"):
        PipelineConfig.from_env({})
    with pytest.raises(ConfigError, match="absolute path"):
        PipelineConfig.from_env({"DATA_ROOT": "relative/data"})

    def deny_write(**kwargs: object) -> None:
        raise PermissionError("test denial")

    monkeypatch.setattr("src.config.validation.tempfile.TemporaryFile", deny_write)
    config = PipelineConfig.from_env({"DATA_ROOT": str(tmp_path), "DATA_MIN_FREE_GIB": "0"})
    with pytest.raises(ConfigError, match="DATA_ROOT is not writable.*test denial"):
        config.validate_startup()


def test_config_checks_disk_space_and_environment_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    disk = type("Disk", (), {"free": 3 * 1024**3})()
    monkeypatch.setattr("src.config.validation.shutil.disk_usage", lambda path: disk)
    config = PipelineConfig.from_env(
        {"DATA_ROOT": str(tmp_path), "DATA_MIN_FREE_GIB": "4", "PIPELINE_LOG_LEVEL": "debug"}
    )
    assert config.config_dir == Path(__file__).parents[1] / "src" / "config" / "defaults"
    assert config.log_level == "DEBUG"
    with pytest.raises(ConfigError, match="DATA_MIN_FREE_GIB requires 4 GiB"):
        config.validate_startup()
    assert (
        PipelineConfig.from_env({"DATA_ROOT": str(tmp_path), "DATA_MIN_FREE_GIB": "0"}).validate_startup() == tmp_path
    )
    with pytest.raises(ConfigError, match="nonnegative integer"):
        PipelineConfig.from_env({"DATA_ROOT": str(tmp_path), "DATA_MIN_FREE_GIB": "-1"})


def test_split_config_files_and_environment_precedence(tmp_path: Path) -> None:
    config_dir = tmp_path / "settings"
    config_dir.mkdir()
    (config_dir / "storage.json").write_text('{"min_free_gib": 3}', encoding="utf-8")
    (config_dir / "runtime.json").write_text('{"log_level": "WARNING"}', encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"DATA_ROOT={tmp_path}/from-file\nDATA_MIN_FREE_GIB=2\nKALSHI_API_KEY_ID=private-test-value\n",
        encoding="utf-8",
    )

    file_config = PipelineConfig.load(config_dir=config_dir, environ={}, env_file=env_file)
    assert file_config.data_root == tmp_path / "from-file"
    assert file_config.min_free_gib == 2
    assert file_config.log_level == "WARNING"
    assert "private-test-value" not in repr(file_config)

    process_config = PipelineConfig.load(
        config_dir=config_dir,
        environ={
            "DATA_ROOT": str(tmp_path / "from-process"),
            "DATA_MIN_FREE_GIB": "1",
            "PIPELINE_LOG_LEVEL": "DEBUG",
        },
        env_file=env_file,
    )
    assert process_config.data_root == tmp_path / "from-process"
    assert process_config.min_free_gib == 1
    assert process_config.log_level == "DEBUG"

    default_config = PipelineConfig.load(config_dir=config_dir, environ={"DATA_ROOT": str(tmp_path)})
    assert default_config.min_free_gib == 3
    assert default_config.log_level == "WARNING"


def test_config_files_reject_malformed_or_unexpected_values(tmp_path: Path) -> None:
    config_dir = tmp_path / "settings"
    config_dir.mkdir()
    storage = config_dir / "storage.json"
    runtime = config_dir / "runtime.json"
    runtime.write_text('{"log_level": "INFO"}', encoding="utf-8")
    values = {"DATA_ROOT": str(tmp_path)}

    with pytest.raises(ConfigError, match="Missing configuration file"):
        PipelineConfig.load(config_dir=config_dir, environ=values)
    storage.write_text("{", encoding="utf-8")
    with pytest.raises(ConfigError, match="Cannot read configuration file"):
        PipelineConfig.load(config_dir=config_dir, environ=values)
    storage.write_text('{"min_free_gib": true}', encoding="utf-8")
    with pytest.raises(ConfigError, match="must be int"):
        PipelineConfig.load(config_dir=config_dir, environ=values)
    storage.write_text('{"min_free_gib": 2, "unknown": 1}', encoding="utf-8")
    with pytest.raises(ConfigError, match="only the"):
        PipelineConfig.load(config_dir=config_dir, environ=values)
    storage.write_text('{"min_free_gib": 2}', encoding="utf-8")
    runtime.write_text('{"log_level": "TRACE"}', encoding="utf-8")
    with pytest.raises(ConfigError, match="PIPELINE_LOG_LEVEL"):
        PipelineConfig.load(config_dir=config_dir, environ=values)
    with pytest.raises(ConfigError, match="Environment file does not exist"):
        PipelineConfig.load(config_dir=config_dir, environ=values, env_file=tmp_path / "missing.env")


def test_config_directory_environment_override(tmp_path: Path) -> None:
    directory = tmp_path / "settings"
    directory.mkdir()
    (directory / "storage.json").write_text('{"min_free_gib": 7}', encoding="utf-8")
    (directory / "runtime.json").write_text('{"log_level": "ERROR"}', encoding="utf-8")
    loaded = PipelineConfig.load(environ={"DATA_ROOT": str(tmp_path), "PIPELINE_CONFIG_DIR": str(directory)})
    assert loaded.config_dir == directory
    assert loaded.min_free_gib == 7
    assert loaded.log_level == "ERROR"
    with pytest.raises(ConfigError, match="PIPELINE_CONFIG_DIR must be an absolute path"):
        PipelineConfig.load(environ={"DATA_ROOT": str(tmp_path), "PIPELINE_CONFIG_DIR": "relative/config"})


def test_layout_creates_layers_and_writer_enforces_scope(tmp_path: Path) -> None:
    layout = DataLayout.create(tmp_path)
    assert {entry.name for entry in tmp_path.iterdir()} == {role.value for role in WriterRole}
    collector = layout.writer(WriterRole.COLLECTOR)
    target = collector.write_new("bronze/mock/trades/part-1.jsonl", b'{"trade": 1}\n')
    assert target.read_bytes() == b'{"trade": 1}\n'

    for wrong_path in ("silver/part-1.parquet", "../silver/part-1.parquet", "/tmp/part-1.parquet"):
        with pytest.raises(WriteBoundaryError):
            collector.write_new(wrong_path, b"data")
    with pytest.raises(WriteBoundaryError, match="replace"):
        collector.write_new("bronze/mock/trades/part-1.jsonl", b"replacement")
    with pytest.raises(TypeError):
        layout.writer("bronze")  # type: ignore[arg-type]
    assert not list((tmp_path / "silver").iterdir())


def test_writer_rejects_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    layout = DataLayout.create(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    (layout.root / "bronze" / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(WriteBoundaryError, match="symbolic link"):
        layout.writer(WriterRole.COLLECTOR).write_new("bronze/escape/nested/file", b"data")
    assert not list(outside.iterdir())


def test_layout_rejects_symlinked_layer(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    (root / "bronze").symlink_to(outside, target_is_directory=True)
    with pytest.raises(WriteBoundaryError, match="real directory"):
        DataLayout.create(root)


def test_writer_cleans_temporary_file_on_publish_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    layout = DataLayout.create(tmp_path)

    def deny_link(source: str, target: Path) -> None:
        raise OSError("test publication failure")

    monkeypatch.setattr("src.data_io.layout.os.link", deny_link)
    with pytest.raises(OSError, match="test publication failure"):
        layout.writer(WriterRole.COLLECTOR).write_new("bronze/failure.bin", b"payload")
    assert not list((tmp_path / "bronze").iterdir())


@pytest.mark.parametrize("role", list(WriterRole))
def test_each_writer_is_bound_to_its_layer(tmp_path: Path, role: WriterRole) -> None:
    layout = DataLayout.create(tmp_path)
    writer = layout.writer(role)
    assert writer.write_new(f"{role.value}/proof.bin", b"ok").read_bytes() == b"ok"
    other = next(candidate for candidate in WriterRole if candidate != role)
    with pytest.raises(WriteBoundaryError):
        writer.write_new(f"{other.value}/wrong.bin", b"bad")
    assert not (tmp_path / other.value / "wrong.bin").exists()


def test_schema_document_matches_code_registry() -> None:
    document = (Path(__file__).parents[1] / "docs" / "SCHEMAS.md").read_text(encoding="utf-8")
    match = re.search(r"```json\n(.*?)\n```", document, flags=re.DOTALL)
    assert match is not None
    declared = json.loads(match.group(1))
    assert declared == SCHEMA_REGISTRY
    assert declared["version"] == SCHEMA_VERSION
    assert len(declared["datasets"]) == 13
    with pytest.raises(ContractError, match="Unknown dataset"):
        get_contract("silver.unknown")
    for dataset, contract in declared["datasets"].items():
        schema = arrow_schema(dataset)
        assert schema.names == list(contract["fields"])
        assert schema.metadata[b"schema_version"].decode() == SCHEMA_VERSION
        for field in schema:
            assert field.nullable == contract["fields"][field.name].endswith("?")
            assert isinstance(field.type, pa.DataType)


def test_bronze_and_silver_validation_rejects_bad_rows() -> None:
    when = datetime(2024, 1, 1, tzinfo=timezone.utc)
    raw = {
        "run_id": "run-1",
        "record_index": 0,
        "venue": "mock",
        "source": "test",
        "message_type": "market",
        "source_event_id": None,
        "event_time": None,
        "received_at": when,
        "ingested_at": when,
        "sequence": None,
        "api_version": "1",
        "protocol_version": None,
        "schema_version": SCHEMA_VERSION,
        "raw_payload": '{"id":"mock-1"}',
    }
    validate_record("bronze.raw", raw)
    with pytest.raises(ContractError, match="valid JSON"):
        validate_record("bronze.raw", {**raw, "raw_payload": "{bad"})
    with pytest.raises(ContractError, match="valid JSON"):
        validate_record("bronze.raw", {**raw, "raw_payload": "NaN"})
    with pytest.raises(ContractError, match="timezone-aware UTC"):
        validate_record("bronze.raw", {**raw, "received_at": when.replace(tzinfo=None)})
    with pytest.raises(ContractError, match="unknown fields"):
        validate_record("bronze.raw", {**raw, "unexpected": 1})
    with pytest.raises(ContractError, match="nonnegative"):
        validate_record("bronze.raw", {**raw, "record_index": -1})

    adapter = MockVenueAdapter()
    trade = adapter.normalize_trade(adapter.backfill_trades(when, when + timedelta(days=1)).items[0])
    with pytest.raises(ContractError, match="between 0 and 1"):
        validate_record("silver.trades", {**trade, "price": Decimal("1.1")})
    with pytest.raises(ContractError, match="finite Decimal"):
        validate_record("silver.trades", {**trade, "price": 0.65})
    with pytest.raises(ContractError, match="decimal128"):
        validate_record("silver.trades", {**trade, "price": Decimal("0.12345678901")})


def test_gold_one_second_requires_aligned_utc_time() -> None:
    when = datetime(2024, 1, 1, tzinfo=timezone.utc)
    row = {
        "venue": "mock",
        "market_id": "mock-1",
        "outcome_id": "yes",
        "second": when,
        "best_bid": Decimal("0.4"),
        "best_ask": Decimal("0.6"),
        "spread": Decimal("0.2"),
        "mid": Decimal("0.5"),
        "microprice": None,
        "bid_depth_top_n": None,
        "ask_depth_top_n": None,
        "imbalance": None,
        "last_trade_price": None,
        "rolling_volume": Decimal("0"),
        "update_count": 0,
        "book_age_ms": None,
        "receive_latency_ms": None,
        "gap": False,
        "recovery": False,
        "as_of": when,
        "source_manifest_ids": '["manifest-1"]',
        "schema_version": SCHEMA_VERSION,
    }
    validate_record("gold.market_1s", row)
    assert pa.Table.from_pylist([row], schema=arrow_schema("gold.market_1s")).num_rows == 1
    with pytest.raises(ContractError, match="align to a UTC second"):
        validate_record("gold.market_1s", {**row, "second": when + timedelta(microseconds=1)})
    with pytest.raises(ContractError, match="between 0 and 1"):
        validate_record("gold.market_1s", {**row, "best_bid": Decimal("1.1")})


def test_training_features_obey_point_in_time_contract() -> None:
    when = datetime(2024, 1, 1, tzinfo=timezone.utc)
    row = {
        "dataset_name": "test",
        "venue": "mock",
        "market_id": "mock-1",
        "observation_time": when,
        "features": '{"volume": 2}',
        "max_feature_event_time": when + timedelta(seconds=1),
        "label": None,
        "label_available_at": None,
        "source_manifest_ids": '["manifest-1"]',
        "schema_version": SCHEMA_VERSION,
    }
    with pytest.raises(ContractError, match="known by observation_time"):
        validate_record("gold.training_datasets", row)
    with pytest.raises(ContractError, match="at least one manifest ID"):
        validate_record(
            "gold.training_datasets",
            {**row, "max_feature_event_time": when, "source_manifest_ids": "[]"},
        )
    validate_record("gold.training_datasets", {**row, "max_feature_event_time": when})


def test_mock_adapter_discover_to_normalize_chain() -> None:
    with pytest.raises(TypeError):
        VenueAdapter()
    adapter = MockVenueAdapter()
    assert isinstance(adapter, VenueAdapter)
    assert len(adapter.metadata.capabilities) == 4
    with pytest.raises(ValueError, match="rate limits"):
        replace(adapter.metadata, rate_limits={"requests_per_second": 0})
    with pytest.raises(ValueError, match="eight"):
        replace(adapter.metadata, validation_rules=())
    discovered = adapter.discover_markets()
    assert discovered.next_cursor is None
    market = adapter.normalize_market(discovered.items[0])
    validate_record("silver.markets", market)
    assert market["market_id"] == "mock-1"
    assert pa.Table.from_pylist([market], schema=arrow_schema("silver.markets")).num_rows == 1

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    assert adapter.backfill_markets(start, end).items == discovered.items
    trade = adapter.normalize_trade(adapter.backfill_trades(start, end).items[0])
    assert trade["price"] == Decimal("0.65")
    assert pa.Table.from_pylist([trade], schema=arrow_schema("silver.trades")).num_rows == 1
    assert adapter.fetch_settlements(start, end).items == ()
    book = adapter.normalize_book_event(next(adapter.stream_market_data(["mock-1"])))
    assert book["source_sequence"] == 1
    validate_record("silver.book_deltas", book)


def test_pipeline_cli_reports_configuration_errors_and_prepares_layout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["check"], environ={}) == 2
    assert "DATA_ROOT is required" in capsys.readouterr().err
    assert main(["check"], environ={"DATA_ROOT": str(tmp_path), "DATA_MIN_FREE_GIB": "0"}) == 0
    assert "data directory ready" in capsys.readouterr().out
    assert (tmp_path / "manifests").is_dir()


def test_module_entry_point_runs_in_a_new_process(tmp_path: Path) -> None:
    environment = {**os.environ, "DATA_ROOT": str(tmp_path), "DATA_MIN_FREE_GIB": "0"}
    result = subprocess.run(
        [sys.executable, "-m", "src", "check"],
        cwd=Path(__file__).parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "pipeline data directory ready" in result.stdout
    assert (tmp_path / "bronze").is_dir()
