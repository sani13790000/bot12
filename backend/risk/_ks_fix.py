"""Patch kill_switch module to use standard logging API (no structlog kwargs)."""

import logging


def patch_kill_switch():
    import backend.risk.kill_switch as m

    std_logger = logging.getLogger("risk.kill_switch")

    class _CompatLogger:
        def critical(self, msg, *args, **kwargs):
            kw_str = " ".join(f"{k}={v}" for k, v in kwargs.items())
            std_logger.critical(f"{msg} {kw_str}".strip(), *args)

        def warning(self, msg, *args, **kwargs):
            kw_str = " ".join(f"{k}={v}" for k, v in kwargs.items())
            std_logger.warning(f"{msg} {kw_str}".strip(), *args)

        def info(self, msg, *args, **kwargs):
            kw_str = " ".join(f"{k}={v}" for k, v in kwargs.items())
            std_logger.info(f"{msg} {kw_str}".strip(), *args)

        def debug(self, msg, *args, **kwargs):
            kw_str = " ".join(f"{k}={v}" for k, v in kwargs.items())
            std_logger.debug(f"{msg} {kw_str}".strip(), *args)

        def error(self, msg, *args, **kwargs):
            kw_str = " ".join(f"{k}={v}" for k, v in kwargs.items())
            std_logger.error(f"{msg} {kw_str}".strip(), *args)

    m.logger = _CompatLogger()
