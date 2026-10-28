"""Configuration errors exposed to command-line and task entry points."""


class ConfigError(ValueError):
    """A configuration value, file, reference, or startup check is invalid."""
