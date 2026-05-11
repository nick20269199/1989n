"""
Feishu Bridge Service
飞书桥接服务 - 连接 NLP 分析到飞书消息推送

作为后台服务运行，将分析报告和告警实时发送到飞书。
启动方式: python feishu_bridge.py 或通过 start_bridge.bat
"""
import json
import logging
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from config import STOCK_DATA_DIR, FEISHU_WEBHOOK_URL
from feishu_sender import (
    send_feishu_alert,
    send_feishu_card,
    send_feishu_message,
)

logger = logging.getLogger("feishu_bridge")

# === 可选模块: bridge_nlp, bridge_sender ===
# 这些模块可能尚未创建，bridge 在缺失时降级运行
_NLP_AVAILABLE = False
_SENDER_AVAILABLE = False
_bridge_nlp = None
_bridge_sender = None

try:
    import bridge_nlp as _bridge_nlp  # type: ignore[import-untyped]

    _NLP_AVAILABLE = True
    logger.info("[桥接] bridge_nlp 已加载")
except ImportError:
    logger.info("[桥接] bridge_nlp 未找到，NLP 分析功能不可用")

try:
    import bridge_sender as _bridge_sender  # type: ignore[import-untyped]

    _SENDER_AVAILABLE = True
    logger.info("[桥接] bridge_sender 已加载")
except ImportError:
    logger.info("[桥接] bridge_sender 未找到，使用 feishu_sender 直接发送")


class FeishuBridge:
    """
    飞书桥接服务。

    功能:
    - 接收分析报告并格式化发送
    - 处理各类告警
    - 管理 Webhook 连接状态
    """

    def __init__(self) -> None:
        self._running = False
        self._thread: threading.Thread | None = None
        self._start_time: datetime | None = None

        # 统计
        self._messages_sent = 0
        self._alerts_sent = 0
        self._errors = 0

        logger.info("[桥接] FeishuBridge 已初始化")

    # === 生命周期 ===

    def start(self) -> None:
        """启动桥接服务 (异步后台线程)。"""
        if self._running:
            logger.warning("[桥接] 服务已在运行中")
            return

        self._running = True
        self._start_time = datetime.now()

        self._thread = threading.Thread(
            target=self._run, name="feishu-bridge", daemon=True
        )
        self._thread.start()

        logger.info("[桥接] 桥接服务已启动")

        # 发送启动通知
        self._send_startup_notification()

    def stop(self) -> None:
        """停止桥接服务。"""
        if not self._running:
            return

        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

        uptime = datetime.now() - self._start_time if self._start_time else None
        uptime_str = str(uptime).split(".")[0] if uptime else "N/A"

        logger.info(
            f"[桥接] 服务已停止 - "
            f"发送: {self._messages_sent}条消息, "
            f"{self._alerts_sent}条告警, "
            f"{self._errors}次错误, "
            f"运行时间: {uptime_str}"
        )

    def _run(self) -> None:
        """后台线程主循环。维护心跳和文件监控。"""
        heartbeat_interval = 300  # 5 分钟心跳
        last_heartbeat = time.time()

        while self._running:
            try:
                now = time.time()
                if now - last_heartbeat >= heartbeat_interval:
                    logger.debug("[桥接] 心跳正常")
                    last_heartbeat = now
                time.sleep(10)
            except Exception as e:
                logger.error(f"[桥接] 主循环异常: {e}")
                time.sleep(30)

    # === 启动通知 ===

    def _send_startup_notification(self) -> None:
        """发送桥接服务启动通知。"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        features = []
        if _NLP_AVAILABLE:
            features.append("NLP 分析")
        if _SENDER_AVAILABLE:
            features.append("Bridge Sender")
        if not features:
            features.append("仅基础消息推送")

        status = f"""**Feishu Bridge 已启动**

时间: {now}
可用功能: {", ".join(features)}
Webhook: {"已配置" if FEISHU_WEBHOOK_URL else "未配置"}
"""
        send_feishu_message(title="Bridge 服务启动", content=status)

    # === 分析报告 ===

    def send_analysis_report(self, report: dict[str, Any]) -> bool:
        """
        格式化并发送分析报告。

        支持的 report 字段:
        - report_type: "daily", "intraday", "closing", "morning", "weekly"
        - title: 报告标题
        - summary: 摘要文本
        - sections: 详细区块列表 (每个 dict 有 title + content)
        - alerts: 告警列表
        - data: 原始数据 (保留)

        Args:
            report: 分析报告字典

        Returns:
            bool: 发送是否成功
        """
        try:
            report_type = report.get("report_type", "unknown")
            title = report.get("title", f"{report_type} 分析报告")
            summary = report.get("summary", "")
            sections = report.get("sections", [])
            alerts = report.get("alerts", [])

            # 构建卡片区块
            card_sections: list[dict] = []

            # 摘要区块
            if summary:
                card_sections.append({
                    "tag": "markdown",
                    "content": f"**摘要**\n\n{summary}",
                })

            # 详细区块
            for sec in sections:
                sec_title = sec.get("title", "")
                sec_content = sec.get("content", "")
                card_sections.append({
                    "tag": "markdown",
                    "content": f"**{sec_title}**\n\n{sec_content}",
                })

            # 时间戳
            timestamp = report.get(
                "timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            card_sections.append({
                "tag": "markdown",
                "content": f"---\n报告时间: {timestamp} | 类型: {report_type}",
            })

            ok = send_feishu_card(title=title, sections=card_sections)
            if ok:
                self._messages_sent += 1
            else:
                self._errors += 1

            # 发送关联告警
            for alert in alerts:
                self.send_alert(
                    alert_type=alert.get("type", "分析告警"),
                    data=alert.get("data", {}),
                )

            return ok

        except Exception as e:
            logger.error(f"[桥接] 报告发送异常: {e}")
            self._errors += 1
            return False

    # === 告警 ===

    def send_alert(self, alert_type: str, data: dict[str, Any]) -> bool:
        """
        发送告警消息。

        支持的 alert_type:
        - "price_break": 价格突破告警
        - "volume_surge": 放量告警
        - "technical": 技术指标告警
        - "risk": 风险告警
        - "system": 系统告警
        - "news": 新闻告警

        Args:
            alert_type: 告警类型
            data: 告警数据 (symbol, price, message 等)

        Returns:
            bool: 发送是否成功
        """
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 根据类型构建消息
            symbol = data.get("symbol", "---")
            stock_name = data.get("name", "")
            stock_info = f"{stock_name}({symbol})" if stock_name else symbol

            alert_title = f"{alert_type} - {stock_info}"

            # 构建告警内容
            lines = []
            if "price" in data:
                lines.append(f"价格: ¥{data['price']}")
            if "change_pct" in data:
                direction = "涨" if data.get("change_pct", 0) >= 0 else "跌"
                lines.append(f"涨跌幅: {direction}{abs(data['change_pct']):.2f}%")
            if "volume" in data:
                lines.append(f"成交量: {data['volume']}")
            if "message" in data:
                lines.append(f"\n{data['message']}")
            if "reason" in data:
                lines.append(f"\n触发原因: {data['reason']}")
            if "action" in data:
                lines.append(f"\n建议操作: {data['action']}")

            lines.append(f"\n告警时间: {now}")

            content = "\n".join(lines)

            ok = send_feishu_alert(title=alert_title, content=content)
            if ok:
                self._alerts_sent += 1
            else:
                self._errors += 1

            return ok

        except Exception as e:
            logger.error(f"[桥接] 告警发送异常: {e}")
            self._errors += 1
            return False

    # === 状态查询 ===

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def stats(self) -> dict[str, int | str | None]:
        return {
            "messages_sent": self._messages_sent,
            "alerts_sent": self._alerts_sent,
            "errors": self._errors,
            "start_time": (
                self._start_time.strftime("%Y-%m-%d %H:%M:%S")
                if self._start_time
                else None
            ),
            "nlp_available": _NLP_AVAILABLE,
            "sender_available": _SENDER_AVAILABLE,
        }


# === 入口 ===

def _handle_shutdown(signum: int, frame: Any) -> None:
    """信号处理: 优雅关闭。"""
    logger.info(f"[桥接] 收到信号 {signum}，正在关闭...")
    if _global_bridge:
        _global_bridge.stop()
    sys.exit(0)


_global_bridge: FeishuBridge | None = None


def main() -> None:
    """主入口: 启动 Feishu Bridge。"""
    global _global_bridge

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("=" * 50)
    logger.info("[桥接] Feishu Bridge Service 启动中...")
    logger.info(f"[桥接] Python 版本: {sys.version}")
    logger.info(f"[桥接] 数据目录: {STOCK_DATA_DIR}")
    logger.info("=" * 50)

    bridge = FeishuBridge()
    _global_bridge = bridge

    # 注册信号处理
    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    bridge.start()

    try:
        while bridge.is_running:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("[桥接] KeyboardInterrupt 收到")
    finally:
        bridge.stop()

    logger.info("[桥接] 退出")


if __name__ == "__main__":
    main()
