"""Tests for the command dispatcher and structured pipeline logging."""

import json
import logging
from pathlib import Path

import pytest

from src.cli import main
from src.config import PipelineConfig
from src.logging_config import pipeline_logging


def test_unknown_command_returns_exit_code(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["bogus"], environ={}) == 2
    assert "invalid choice" in capsys.readouterr().err


def test_check_reports_os_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(_: PipelineConfig) -> Path:
        raise OSError("check failed")

    monkeypatch.setattr(PipelineConfig, "check_configured_root", fail)
    assert main(["check"], environ={"DATA_ROOT": str(tmp_path)}) == 2
    assert "pipeline startup failed: check failed" in capsys.readouterr().err


@pytest.mark.parametrize(("level", "logged"), [("INFO", False), ("DEBUG", True)])
def test_check_uses_configured_logging_level(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], level: str, logged: bool
) -> None:
    def check_with_debug(_: PipelineConfig) -> Path:
        logging.getLogger("src.test").debug("preflight", extra={"event": "config.preflight"})
        return tmp_path

    monkeypatch.setattr(PipelineConfig, "check_configured_root", check_with_debug)
    assert main(["check"], environ={"DATA_ROOT": str(tmp_path), "PIPELINE_LOG_LEVEL": level}) == 0
    captured = capsys.readouterr()
    assert "configuration valid" in captured.out
    events = [json.loads(line)["event"] for line in captured.err.splitlines()]
    assert events == (["config.effective", "config.preflight"] if logged else ["config.effective"])


def test_check_logs_effective_settings_sources_and_hash(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    environ = {"DATA_ROOT": str(tmp_path), "DATA_MIN_FREE_GIB": "0", "UNRELATED_API_KEY": "sensitive-value"}
    assert main(["check"], environ=environ) == 0
    output = capsys.readouterr().err
    assert "sensitive-value" not in output
    (event,) = [json.loads(line) for line in output.splitlines()]
    assert event["event"] == "config.effective"
    settings = event["details"]["settings"]
    assert set(settings) == {"data_root", "min_free_gib", "log_level", "config_dir"}
    assert settings["data_root"] == {"value": str(tmp_path), "source": "environment:DATA_ROOT"}
    assert settings["min_free_gib"] == {"value": "0", "source": "environment:DATA_MIN_FREE_GIB"}
    assert settings["log_level"] == {"value": "INFO", "source": "default:runtime.json"}
    assert settings["config_dir"]["source"] == "default:src/config/defaults"
    expected = PipelineConfig.load(environ=environ).effective_settings()
    assert event["details"]["sha256"] == expected["sha256"]


def test_effective_settings_hash_depends_on_values_not_sources(tmp_path: Path) -> None:
    loaded = PipelineConfig.load(environ={"DATA_ROOT": str(tmp_path)})
    direct = PipelineConfig(
        data_root=loaded.data_root,
        min_free_gib=loaded.min_free_gib,
        log_level=loaded.log_level,
        config_dir=loaded.config_dir,
    )
    assert {s["source"] for s in direct.effective_settings()["settings"].values()} == {"direct"}
    assert direct.effective_settings()["sha256"] == loaded.effective_settings()["sha256"]
    changed = PipelineConfig.load(environ={"DATA_ROOT": str(tmp_path), "PIPELINE_LOG_LEVEL": "DEBUG"})
    assert changed.effective_settings()["settings"]["log_level"]["source"] == "environment:PIPELINE_LOG_LEVEL"
    assert changed.effective_settings()["sha256"] != loaded.effective_settings()["sha256"]


def test_logging_level_json_and_run_id(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("PIPELINE_SECRET", "sensitive-value")
    logger = logging.getLogger("src.test")
    with pipeline_logging("INFO"):
        logger.debug("hidden")
        logger.info("visible", extra={"event": "job.started", "run_id": "run-1"})
    output = capsys.readouterr().err
    event = json.loads(output)
    assert event["level"] == "INFO"
    assert event["event"] == "job.started"
    assert event["message"] == "visible"
    assert event["run_id"] == "run-1"
    assert event["time"].endswith("+00:00")
    assert "sensitive-value" not in output

    with pipeline_logging("DEBUG"):
        logger.debug("now visible")
    assert json.loads(capsys.readouterr().err)["message"] == "now visible"


def test_logging_restores_previous_configuration_on_failure() -> None:
    logger = logging.getLogger("src")
    before = (logger.handlers[:], logger.level, logger.propagate)
    with pytest.raises(RuntimeError, match="failed"):
        with pipeline_logging("DEBUG"):
            raise RuntimeError("failed")
    assert (logger.handlers, logger.level, logger.propagate) == before


@pytest.mark.parametrize("how", ["argument", "environment", "default"])
def test_effective_settings_record_config_dir_and_default_sources(tmp_path: Path, how: str) -> None:
    from src.config.loader import DEFAULT_CONFIG_DIR

    environ = {"DATA_ROOT": str(tmp_path)}
    kwargs = {}
    if how == "argument":
        kwargs["config_dir"] = DEFAULT_CONFIG_DIR
    elif how == "environment":
        environ["PIPELINE_CONFIG_DIR"] = str(DEFAULT_CONFIG_DIR)
    settings = PipelineConfig.load(environ=environ, **kwargs).effective_settings()["settings"]
    expected = {
        "argument": "argument:config_dir",
        "environment": "environment:PIPELINE_CONFIG_DIR",
        "default": "default:src/config/defaults",
    }[how]
    assert settings["config_dir"]["source"] == expected
    assert settings["min_free_gib"]["source"] == "default:storage.json"


def test_loaded_config_survives_pickle_and_deepcopy_with_sources(tmp_path: Path) -> None:
    import copy
    import pickle

    loaded = PipelineConfig.load(environ={"DATA_ROOT": str(tmp_path), "PIPELINE_LOG_LEVEL": "DEBUG"})
    expected = loaded.effective_settings()
    for clone in (pickle.loads(pickle.dumps(loaded)), copy.deepcopy(loaded), loaded.model_copy(deep=True)):
        assert clone.effective_settings() == expected
        assert clone == loaded
