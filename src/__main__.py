"""Run the pipeline startup command with ``python -m src``."""

from src.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
    
    
    
#提供更短的启动方式，eg src check not src.cli chekc, 无实际意义 
