"""Run the pipeline startup command with ``python -m src``."""

from src.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

# 提供更短的启动方式，例如 src check 而不是 src.cli check，无实际意义。
