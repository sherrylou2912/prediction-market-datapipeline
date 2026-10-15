"""Acceptance tests for the first v1 architecture PR."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pytest

from src.v1.__main__ import main
from src.v1.adapter import VenueAdapter
from src.v1.config import ConfigError, PipelineConfig
from src.v1.contracts import (
    SCHEMA_REGISTRY,
    SCHEMA_VERSION,
    ContractError,
    arrow_schema,
    validate_record,
)
from src.v1.layout import DataLayout, WriteBoundaryError, WriterRole
from src.v1.mock_adapter import MockVenueAdapter


def test_config_requires_absolute_data_root_and_reports_unwritable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ConfigError, match="DATA_ROOT is required"):
        PipelineConfig.from_env({})
    with pytest.raises(ConfigError, match="absolute path"):
        PipelineConfig.from_env({"DATA_ROOT": "relative/data"})

    def deny_write(**kwargs: object) -> None:
        raise PermissionError("test denial")

    monkeypatch.setattr("src.v1.config.tempfile.TemporaryFile", deny_write)
    config = PipelineConfig.from_env({"DATA_ROOT": str(tmp_path), "DATA_MIN_FREE_GIB": "0"})
    with pytest.raises(ConfigError, match="DATA_ROOT is not writable.*test denial"):
        config.validate_startup()


def test_config_checks_disk_space_and_environment_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    disk = type("Disk", (), {"free": 3 * 1024**3})()
    monkeypatch.setattr("src.v1.config.shutil.disk_usage", lambda path: disk)
    config = PipelineConfig.from_env(
        {"DATA_ROOT": str(tmp_path), "DATA_MIN_FREE_GIB": "4", "PIPELINE_LOG_LEVEL": "debug"}
    )
    assert config.log_level == "DEBUG"
    with pytest.raises(ConfigError, match="DATA_MIN_FREE_GIB requires 4 GiB"):
        config.validate_startup()
    assert (
        PipelineConfig.from_env({"DATA_ROOT": str(tmp_path), "DATA_MIN_FREE_GIB": "0"}).validate_startup() == tmp_path
    )
    with pytest.raises(ConfigError, match="nonnegative integer"):
        PipelineConfig.from_env({"DATA_ROOT": str(tmp_path), "DATA_MIN_FREE_GIB": "-1"})


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
    adapter = MockVenueAdapter()
    assert isinstance(adapter, VenueAdapter)
    assert len(adapter.metadata.capabilities) == 4
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


def test_v1_cli_reports_configuration_errors_and_prepares_layout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["check"], environ={}) == 2
    assert "DATA_ROOT is required" in capsys.readouterr().err
    assert main(["check"], environ={"DATA_ROOT": str(tmp_path), "DATA_MIN_FREE_GIB": "0"}) == 0
    assert "data directory ready" in capsys.readouterr().out
    assert (tmp_path / "manifests").is_dir()
