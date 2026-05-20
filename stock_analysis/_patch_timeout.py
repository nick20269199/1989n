"""
全局 requests 超时补丁 — 给所有未设置 timeout 的 HTTP 请求加默认超时。

在所有 akshare 调用（不暴露 timeout 参数）和遗忘的 requests 调用上生效。
导入即生效：from _patch_timeout import apply; apply()
"""

import logging

_logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15  # 秒，连接 + 读取总超时

_ORIGINAL_REQUEST = None


def _patch_session_request():
    """Monkey-patch requests.Session.request 注入默认 timeout。"""
    import requests

    global _ORIGINAL_REQUEST
    if _ORIGINAL_REQUEST is not None:
        return  # 防止重复打补丁

    _ORIGINAL_REQUEST = requests.Session.request

    def _patched_request(self, method, url, **kwargs):
        if "timeout" not in kwargs:
            kwargs["timeout"] = DEFAULT_TIMEOUT
        return _ORIGINAL_REQUEST(self, method, url, **kwargs)

    requests.Session.request = _patched_request
    _logger.debug(
        f"requests.Session.request patched — "
        f"default timeout={DEFAULT_TIMEOUT}s"
    )


def apply():
    _patch_session_request()
