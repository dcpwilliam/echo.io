"""日志：控制台 + 滚动文件（标准库 logging，无第三方依赖）。

    from .logging import setup, log_path
    setup(level="INFO", log_dir=config.LOG_DIR)

输出格式：
    2026-10-04 20:55:01.123 INFO  [aiservice.access] → #a1b2c3d4 POST /api/prompt/analyze
    2026-10-04 20:55:01.140 INFO  [aiservice.access] ← #a1b2c3d4 200 17.2ms
每个请求带一个 8 位 request id，同一次调用的前后日志能串起来。
"""
import logging
import os
from logging.handlers import RotatingFileHandler

_FMT = "%(asctime)s.%(msecs)03d %(levelname)-5s [%(name)-16s] %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"
_FILENAME = "aiservice.log"
_MAX_BYTES = 2 * 1024 * 1024   # 单个文件 2MB
_BACKUPS = 3

_configured = False
_file_path = None


def setup(level="INFO", log_dir=None, console=True):
    """重复调用安全：会清掉旧 handler 再装新的。"""
    global _configured, _file_path

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter(_FMT, datefmt=_DATEFMT)
    text_level = getattr(logging, str(level).upper(), logging.INFO)

    if console:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        sh.setLevel(text_level)
        root.addHandler(sh)

    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
        _file_path = os.path.join(log_dir, _FILENAME)
        fh = RotatingFileHandler(_file_path, maxBytes=_MAX_BYTES,
                                 backupCount=_BACKUPS, encoding="utf-8")
        fh.setFormatter(fmt)
        fh.setLevel(logging.DEBUG)   # 文件里记全，控制台按级别
        root.addHandler(fh)

    _configured = True
    return root


def log_path():
    return _file_path


def tail(lines=100):
    """读最近 N 行日志，给 /api/logs 用。"""
    if not _file_path or not os.path.exists(_file_path):
        return []
    try:
        with open(_file_path, "r", encoding="utf-8") as f:
            content = f.read().splitlines()
        return content[-max(1, min(lines, 2000)):]
    except OSError:
        return []
