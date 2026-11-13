"""Configuration loading and preflight failure-path tests."""

from __future__ import annotations

import json
import traceback
from pathlib import Path
from typing import Annotated, Literal, Union
from unittest.mock import patch

import pytest
from pydantic import Field, field_validator

from src.config import ConfigError, PipelineConfig
from src.config.loader import load_environment
from src.config.validation import ConfigModel, NonnegativeInteger


def make_config(root: Path) -> PipelineConfig:
    return PipelineConfig(data_root=root, min_free_gib=0, log_level="INFO", config_dir=root.parent)


def test_validation_traceback_does_not_expose_input(tmp_path: Path) -> None:
    marker = "EXAMPLE_PRIVATE_VALUE"
    with pytest.raises(ConfigError) as caught:
        PipelineConfig(data_root=tmp_path, min_free_gib=marker, log_level="INFO", config_dir=tmp_path)
    rendered = "".join(traceback.format_exception(type(caught.value), caught.value, caught.value.__traceback__))
    assert "DATA_MIN_FREE_GIB" in rendered
    assert marker not in rendered
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_config_model_public_validation_and_nesting_hide_input() -> None:
    class Nested(ConfigModel):
        quantity: NonnegativeInteger

    class Outer(ConfigModel):
        nested: Nested

    marker = "EXAMPLE_INVALID_PRIVATE_VALUE"
    calls = (
        (lambda: Nested.model_validate({"quantity": marker}), "quantity"),
        (lambda: Nested.model_validate_json(json.dumps({"quantity": marker})), "quantity"),
        (lambda: Nested.model_validate_strings({"quantity": marker}), "quantity"),
        (lambda: Nested.model_validate(marker), "valid dictionary"),
        (lambda: Outer(nested={"quantity": marker}), "nested"),
        (lambda: Outer(nested=marker), "nested"),
        (lambda: Outer.model_validate({"nested": {"quantity": marker}}), "nested"),
        (lambda: Outer.model_validate_json(json.dumps({"nested": {"quantity": marker}})), "nested"),
    )
    for call, expected_location in calls:
        with pytest.raises(ConfigError) as caught:
            call()
        formatted = "".join(traceback.format_exception(type(caught.value), caught.value, caught.value.__traceback__))
        assert marker not in formatted
        assert expected_location in str(caught.value)
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None


def test_unknown_config_field_name_is_not_exposed() -> None:
    class Example(ConfigModel):
        quantity: NonnegativeInteger

    marker = "EXAMPLE_PRIVATE_FIELD_NAME"
    data = {"quantity": 1, marker: "value"}
    for call in (
        lambda: Example(**data),
        lambda: Example.model_validate(data),
        lambda: Example.model_validate_json(json.dumps(data)),
    ):
        with pytest.raises(ConfigError, match="unknown configuration field") as caught:
            call()
        formatted = "".join(traceback.format_exception(type(caught.value), caught.value, caught.value.__traceback__))
        assert marker not in formatted


@pytest.mark.parametrize("invalid_field", ["first", "second"])
@pytest.mark.parametrize("use_model_validate", [False, True])
def test_nested_config_error_names_outer_field(invalid_field: str, use_model_validate: bool) -> None:
    class Inner(ConfigModel):
        number: NonnegativeInteger

    class Outer(ConfigModel):
        first: Inner
        second: Inner

    data = {"first": {"number": 1}, "second": {"number": 1}}
    data[invalid_field] = {"number": -1}
    with pytest.raises(ConfigError) as caught:
        Outer.model_validate(data) if use_model_validate else Outer(**data)
    assert invalid_field in str(caught.value)


def test_config_mapping_key_is_not_exposed() -> None:
    class Example(ConfigModel):
        settings: dict[str, int]

    marker = "EXAMPLE_PRIVATE_MAPPING_KEY"
    data = {"settings": {marker: "invalid"}}
    for call in (
        lambda: Example(**data),
        lambda: Example.model_validate(data),
        lambda: Example.model_validate_json(json.dumps(data)),
    ):
        with pytest.raises(ConfigError, match="settings") as caught:
            call()
        formatted = "".join(traceback.format_exception(type(caught.value), caught.value, caught.value.__traceback__))
        assert marker not in formatted


def test_validation_messages_do_not_expose_discriminator_or_custom_validator_input() -> None:
    class ChoiceA(ConfigModel):
        kind: Literal["a"]

    class ChoiceB(ConfigModel):
        kind: Literal["b"]

    class Outer(ConfigModel):
        choice: Annotated[Union[ChoiceA, ChoiceB], Field(discriminator="kind")]  # noqa: UP007

    class Custom(ConfigModel):
        value: str

        @field_validator("value")
        @classmethod
        def reject_value(cls, value: str) -> str:
            raise ValueError(f"bad input: {value}")

    marker = "EXAMPLE_PRIVATE_INPUT"
    data = {"choice": {"kind": marker}}
    calls = (
        (lambda: Outer(**data), "choice"),
        (lambda: Outer.model_validate(data), "choice"),
        (lambda: Outer.model_validate_json(json.dumps(data)), "choice"),
        (lambda: Outer.model_validate_strings(data), "choice"),
        (lambda: Custom(value=marker), "value"),
    )
    for call, field in calls:
        with pytest.raises(ConfigError, match=field) as caught:
            call()
        formatted = "".join(traceback.format_exception(type(caught.value), caught.value, caught.value.__traceback__))
        assert marker not in formatted
        assert caught.value.__cause__ is None
        assert caught.value.__context__ is None


def test_missing_default_env_and_empty_env_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.config.loader.DEFAULT_ENV_FILE", tmp_path / "missing")
    monkeypatch.setattr("src.config.loader.os.environ", {"PROCESS": "value"})
    assert load_environment(None, None) == {"PROCESS": "value"}
    env = tmp_path / "settings.env"
    env.write_text("NO_VALUE\nEMPTY=\nPRESENT=hello\n", encoding="utf-8")
    assert load_environment({}, env) == {"EMPTY": "", "PRESENT": "hello"}


def test_invalid_utf8_env(tmp_path: Path) -> None:
    env = tmp_path / "settings.env"
    env.write_bytes(b"\xff")
    with pytest.raises(ConfigError, match="Cannot read environment file"):
        load_environment({}, env)


@pytest.mark.parametrize("kind", ["directory", "dangling", "unreadable"])
def test_default_environment_only_ignores_absent_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    env = tmp_path / ".env"
    if kind == "directory":
        env.mkdir()
    elif kind == "dangling":
        env.symlink_to(tmp_path / "missing")
    else:
        env.write_text("A=1", encoding="utf-8")
        original = Path.open

        def deny_file(path: Path, *args: object, **kwargs: object):
            if path == env:
                raise PermissionError("denied")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", deny_file)
    monkeypatch.setattr("src.config.loader.DEFAULT_ENV_FILE", env)
    with pytest.raises(ConfigError, match="Cannot read environment file"):
        load_environment(None, None)


@pytest.mark.parametrize("contents", [b"[1]", b"2", b"{}", b"\xff", b'{"min_free_gib": true}'])
def test_invalid_defaults_are_rejected(tmp_path: Path, contents: bytes) -> None:
    (tmp_path / "storage.json").write_bytes(contents)
    (tmp_path / "runtime.json").write_text('{"log_level": "INFO"}', encoding="utf-8")
    with pytest.raises(ConfigError):
        PipelineConfig.load(config_dir=tmp_path, environ={"DATA_ROOT": str(tmp_path)})


@pytest.mark.parametrize("value", ["+4", "4_000", "-1", "4.0", "４", "١"])
def test_environment_integer_rejects_non_ascii_decimal(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigError, match="DATA_MIN_FREE_GIB"):
        PipelineConfig.load(environ={"DATA_ROOT": str(tmp_path), "DATA_MIN_FREE_GIB": value})


def test_environment_integer_and_tilde_expansion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    defaults = tmp_path / "settings"
    defaults.mkdir()
    (defaults / "storage.json").write_text(json.dumps({"min_free_gib": 1}), encoding="utf-8")
    (defaults / "runtime.json").write_text(json.dumps({"log_level": "INFO"}), encoding="utf-8")
    config = PipelineConfig.load(
        environ={"DATA_ROOT": "~/data", "PIPELINE_CONFIG_DIR": "~/settings", "DATA_MIN_FREE_GIB": "004"}
    )
    assert config.data_root == tmp_path / "data"
    assert config.config_dir == defaults
    assert config.min_free_gib == 4


def test_preflight_disk_and_mkdir_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = make_config(tmp_path / "new")
    monkeypatch.setattr(
        "src.config.models.pipeline.shutil.disk_usage", lambda _: (_ for _ in ()).throw(OSError("disk"))
    )
    with pytest.raises(ConfigError, match="Cannot check free disk space"):
        config.validate_for_write()
    monkeypatch.undo()
    monkeypatch.setattr(Path, "mkdir", lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("denied")))
    with pytest.raises(ConfigError, match="DATA_ROOT is not writable"):
        config.validate_for_write()


def test_write_preflight_syncs_each_new_directory_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config.models import pipeline

    root = tmp_path / "one" / "two"
    seen = []
    sync = pipeline._sync_directory

    def track(path: Path) -> None:
        seen.append(path)
        sync(path)

    monkeypatch.setattr(pipeline, "_sync_directory", track)
    make_config(root).validate_for_write()
    assert seen == [tmp_path, tmp_path / "one"]


def test_write_preflight_sync_failure_cleans_created_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.config.models import pipeline

    root = tmp_path / "one" / "two"
    seen = []
    sync = pipeline._sync_directory

    def fail_once(path: Path) -> None:
        seen.append(path)
        if path == tmp_path / "one" and len(seen) == 2:
            raise OSError("directory sync failed")
        sync(path)

    monkeypatch.setattr(pipeline, "_sync_directory", fail_once)
    with pytest.raises(ConfigError, match="directory sync failed"):
        make_config(root).validate_for_write()
    assert seen == [tmp_path, tmp_path / "one", tmp_path / "one", tmp_path]
    assert tmp_path.is_dir() and not (tmp_path / "one").exists()


def test_failed_write_probe_removes_only_created_empty_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "src.config.models.pipeline.tempfile.TemporaryFile",
        lambda **kwargs: (_ for _ in ()).throw(PermissionError("denied")),
    )
    root = tmp_path / "a" / "b"
    with pytest.raises(ConfigError, match="not writable"):
        make_config(root).validate_for_write()
    assert tmp_path.is_dir()
    assert not (tmp_path / "a").exists()
    root.mkdir(parents=True)
    with pytest.raises(ConfigError, match="not writable"):
        make_config(root).validate_for_write()
    assert root.is_dir()


def test_preflight_resolves_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    config = make_config(link)
    assert config.check_configured_root() == target
    assert config.validate_for_read() == target
    assert config.validate_for_write() == target


def test_hard_link_failure_cleans_new_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "new" / "data"
    monkeypatch.setattr(
        "src.config.models.pipeline.os.link", lambda *args: (_ for _ in ()).throw(OSError("unsupported"))
    )
    with pytest.raises(ConfigError, match="does not support hard links"):
        make_config(root).validate_for_write()
    assert not (tmp_path / "new").exists()


def test_missing_volume_fails_before_disk_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.config.models.pipeline.sys.platform", "darwin")
    config = make_config(Path("/Volumes/definitely-unmounted-config-test/data"))
    with patch("src.config.models.pipeline.shutil.disk_usage") as probe:
        with pytest.raises(ConfigError, match="volume is not mounted"):
            config.validate_for_write()
        probe.assert_not_called()


def test_root_not_directory_after_mkdir_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "new"
    original_is_dir = Path.is_dir

    def is_dir(path: Path) -> bool:
        return False if path == root else original_is_dir(path)

    monkeypatch.setattr(Path, "is_dir", is_dir)
    with pytest.raises(ConfigError, match="DATA_ROOT is not writable"):
        make_config(root).validate_for_write()
    assert not root.exists()


def test_cleanup_preserves_files_created_concurrently(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "new" / "data"

    def failed_probe(**kwargs: object) -> None:
        (root / "other-file").write_text("keep", encoding="utf-8")
        raise PermissionError("denied")

    monkeypatch.setattr("src.config.models.pipeline.tempfile.TemporaryFile", failed_probe)
    with pytest.raises(ConfigError, match="cannot remove newly created directories"):
        make_config(root).validate_for_write()
    assert (root / "other-file").read_text(encoding="utf-8") == "keep"


def test_duplicate_json_settings_are_rejected_even_with_override(tmp_path: Path) -> None:
    (tmp_path / "storage.json").write_text('{"min_free_gib":250,"min_free_gib":0}', encoding="utf-8")
    (tmp_path / "runtime.json").write_text('{"log_level":"INFO"}', encoding="utf-8")
    with pytest.raises(ConfigError, match="duplicate JSON key.*min_free_gib"):
        PipelineConfig.load(config_dir=tmp_path, environ={"DATA_ROOT": str(tmp_path), "DATA_MIN_FREE_GIB": "0"})


def test_dotenv_interpolation_uses_only_selected_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / "settings.env"
    env_file.write_text(
        "LEVEL=INFO\nPIPELINE_LOG_LEVEL=${LEVEL}\nHOST_ONLY=${HOST_SECRET:-fallback}\nEMPTY_VALUE=${UNSET}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("LEVEL", "ERROR")
    monkeypatch.setenv("HOST_SECRET", "host-secret")
    for key in ("PIPELINE_LOG_LEVEL", "HOST_ONLY", "EMPTY_VALUE", "UNSET"):
        monkeypatch.delenv(key, raising=False)
    isolated = load_environment({"LEVEL": "DEBUG"}, env_file)
    assert isolated["PIPELINE_LOG_LEVEL"] == "DEBUG"
    assert isolated["HOST_ONLY"] == "fallback"
    assert isolated["EMPTY_VALUE"] == ""
    without_override = load_environment({}, env_file)
    assert without_override["PIPELINE_LOG_LEVEL"] == "INFO"
    assert without_override["HOST_ONLY"] == "fallback"
    actual = load_environment(None, env_file)
    assert actual["PIPELINE_LOG_LEVEL"] == "ERROR"
    assert actual["HOST_ONLY"] == "host-secret"


@pytest.mark.parametrize("environ", [{}, {"A": "override"}])
def test_duplicate_dotenv_keys_rejected_before_or_after_interpolation(tmp_path: Path, environ: dict[str, str]) -> None:
    env_file = tmp_path / "settings.env"
    env_file.write_text("A=first\nB=${A}\nA=second\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="Duplicate environment key.*A"):
        load_environment(environ, env_file)
    env_file.write_text("A\nA=second\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="Duplicate environment key.*A"):
        load_environment(environ, env_file)


def test_dotenv_interpolation_uses_earlier_file_values_and_environment_override(tmp_path: Path) -> None:
    env_file = tmp_path / "settings.env"
    env_file.write_text("A=first\nB=${A}\n", encoding="utf-8")
    assert load_environment({}, env_file)["B"] == "first"
    assert load_environment({"A": "override"}, env_file)["B"] == "override"


def test_macos_volume_requires_actual_mount(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config.models import pipeline

    volume = Path("/Volumes/fake-drive")
    root = volume / "data"
    original_exists = Path.exists
    original_resolve = Path.resolve
    monkeypatch.setattr(pipeline.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "exists", lambda path: True if path == volume else original_exists(path))
    monkeypatch.setattr(
        Path, "resolve", lambda path, strict=False: volume if path == volume else original_resolve(path, strict=strict)
    )
    monkeypatch.setattr(pipeline.os.path, "ismount", lambda path: False)
    with patch("src.config.models.pipeline.shutil.disk_usage") as probe:
        with pytest.raises(ConfigError, match="volume is not mounted"):
            make_config(root).validate_for_write()
        probe.assert_not_called()
    monkeypatch.setattr(pipeline.os.path, "ismount", lambda path: path == volume)
    monkeypatch.setattr(pipeline, "_nearest_existing_directory", lambda path: tmp_path)
    with patch("src.config.models.pipeline.shutil.disk_usage", side_effect=OSError("probe reached")):
        with pytest.raises(ConfigError, match="probe reached"):
            make_config(root).validate_for_write()


def test_volume_path_with_parent_segments_is_rejected_on_macos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.config.models.pipeline.sys.platform", "darwin")
    with pytest.raises(ConfigError, match="must not contain"):
        make_config(Path("/Volumes/a/../b/data")).validate_for_write()


def test_volumes_path_is_not_special_on_non_macos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config.models import pipeline

    monkeypatch.setattr(pipeline.sys, "platform", "linux")
    monkeypatch.setattr(pipeline, "_nearest_existing_directory", lambda path: tmp_path)
    with patch("src.config.models.pipeline.shutil.disk_usage", side_effect=OSError("probe reached")):
        with pytest.raises(ConfigError, match="probe reached"):
            make_config(Path("/Volumes/ordinary/data")).validate_for_write()


def test_macos_volume_symlink_to_system_root_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    volume = Path("/Volumes/system-alias")
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr("src.config.models.pipeline.sys.platform", "darwin")
    monkeypatch.setattr(Path, "is_symlink", lambda path: True if path == volume else original_is_symlink(path))
    with patch("src.config.models.pipeline.os.path.ismount") as probe:
        with pytest.raises(ConfigError, match="volume is not mounted"):
            make_config(volume / "data").validate_for_write()
        probe.assert_not_called()


def test_macos_case_variant_cannot_bypass_volume_symlink_check(monkeypatch: pytest.MonkeyPatch) -> None:
    volume = Path("/volumes/system-alias")
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr("src.config.models.pipeline.sys.platform", "darwin")
    monkeypatch.setattr(Path, "is_symlink", lambda path: True if path == volume else original_is_symlink(path))
    with pytest.raises(ConfigError, match="volume is not mounted"):
        make_config(volume / "data").validate_for_write()


def test_macos_symlink_alias_to_unmounted_volume_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.config.models.pipeline.sys.platform", "darwin")
    alias = tmp_path / "alias"
    alias.symlink_to("/Volumes/missing-external-drive/data")
    outer = tmp_path / "outer"
    outer.symlink_to(alias)
    with patch("src.config.models.pipeline.shutil.disk_usage") as disk_probe:
        with pytest.raises(ConfigError, match="volume is not mounted"):
            make_config(outer / "child").validate_for_write()
        disk_probe.assert_not_called()


def test_macos_ordinary_data_root_symlink_is_still_supported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.config.models.pipeline.sys.platform", "darwin")
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    assert make_config(alias).validate_for_write() == target
