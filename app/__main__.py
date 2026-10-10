"""支持 `python -m app` 启动。"""
import sys

from run import main

if __name__ == "__main__":
    sys.exit(main())
