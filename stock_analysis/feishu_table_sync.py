"""
Feishu (Lark) Table Sync
飞书表格同步 - 通过 Feishu Sheets API 同步持仓/报告/新闻到飞书表格

使用飞书开放平台 API:
- Tenant Access Token (2小时过期，自动刷新)
- Sheets v2 API (https://open.feishu.cn/open-apis/sheets/v2/...)

需要环境变量:
- FEISHU_APP_ID: 飞书应用 ID
- FEISHU_APP_SECRET: 飞书应用密钥
"""
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from config import (
    FEISHU_APP_ID,
    FEISHU_APP_SECRET,
    FEISHU_NEWS_SHEET_ID,
    FEISHU_PORTFOLIO_SHEET_ID,
    FEISHU_REPORT_SHEET_ID,
    FEISHU_SPREADSHEET_TOKEN,
    HEADERS,
    PORTFOLIO_FILE,
    STOCK_DATA_DIR,
)

logger = logging.getLogger("feishu_table_sync")

# API 端点
_TOKEN_URL = (
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
)
_SHEETS_BASE = "https://open.feishu.cn/open-apis/sheets/v2"
_SPREADSHEETS_URL = f"{_SHEETS_BASE}/spreadsheets"

# === Token 管理 ===
_token_cache: dict[str, Any] = {
    "token": "",
    "expires_at": 0.0,
}
_TOKEN_LOCK = __import__("threading").Lock()


def _get_tenant_access_token() -> str:
    """获取/刷新 Tenant Access Token。Token 有效期为 2 小时。"""
    with _TOKEN_LOCK:
        now = time.time()
        # 提前 5 分钟刷新
        if _token_cache["token"] and now < _token_cache["expires_at"] - 300:
            return _token_cache["token"]

        if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
            logger.error("[飞书表格] FEISHU_APP_ID 或 FEISHU_APP_SECRET 未配置")
            return ""

        try:
            resp = requests.post(
                _TOKEN_URL,
                json={
                    "app_id": FEISHU_APP_ID,
                    "app_secret": FEISHU_APP_SECRET,
                },
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            code = data.get("code", -1)
            if code != 0:
                logger.error(f"[飞书表格] Token 获取失败: {data.get('msg')}")
                return ""

            token = data.get("tenant_access_token", "")
            expire = data.get("expire", 7200)  # 默认 2 小时
            _token_cache["token"] = token
            _token_cache["expires_at"] = now + expire

            logger.info(f"[飞书表格] Token 已刷新, 有效期 {expire}s")
            return token

        except Exception as e:
            logger.error(f"[飞书表格] Token 获取异常: {e}")
            return ""


def _feishu_api(
    method: str,
    path: str,
    body: dict | None = None,
    params: dict | None = None,
) -> dict[str, Any] | None:
    """调用飞书开放 API 的通用封装。

    Args:
        method: HTTP 方法 (GET, POST, PUT, DELETE)
        path: API 路径 (如 /spreadsheets/{token}/values)
        body: 请求体
        params: 查询参数

    Returns:
        API 响应数据或 None
    """
    token = _get_tenant_access_token()
    if not token:
        return None

    url = f"https://open.feishu.cn/open-apis{path}"
    api_headers = {
        **HEADERS,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    try:
        resp = requests.request(
            method=method,
            url=url,
            headers=api_headers,
            json=body,
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        code = data.get("code", -1)
        if code != 0:
            logger.error(
                f"[飞书表格] API 错误: {method} {path} -> "
                f"code={code}, msg={data.get('msg')}"
            )
            return None

        return data.get("data")

    except requests.exceptions.Timeout:
        logger.error(f"[飞书表格] API 超时: {method} {path}")
        return None
    except Exception as e:
        logger.error(f"[飞书表格] API 异常: {method} {path}: {e}")
        return None


# === 表格操作工具 ===

def _ensure_header_row(
    spreadsheet_token: str, sheet_id: str, headers: list[str]
) -> bool:
    """确保表格有标题行。如果第一行为空则写入标题。"""
    result = _feishu_api(
        "GET",
        f"{_SHEETS_BASE}/spreadsheets/{spreadsheet_token}"
        f"/values/{sheet_id}!A1:{_col_letter(len(headers))}1",
    )

    if result is None:
        return False

    value_range = result.get("valueRange", {})
    existing = value_range.get("values", [])

    if existing and existing[0] and any(v for v in existing[0]):
        logger.info("[飞书表格] 标题行已存在，跳过写入")
        return True

    # 写入标题行
    return _write_cells(
        spreadsheet_token,
        sheet_id,
        start_row=0,
        start_col=0,
        values=[headers],
    )


def _write_cells(
    spreadsheet_token: str,
    sheet_id: str,
    start_row: int,
    start_col: int,
    values: list[list[Any]],
) -> bool:
    """写入单元格数据到指定范围。"""
    range_end_col = max(len(row) for row in values) + start_col
    range_end_row = len(values) + start_row

    range_str = (
        f"{sheet_id}!"
        f"{_col_letter(start_col + 1)}{start_row + 1}:"
        f"{_col_letter(range_end_col)}{range_end_row}"
    )

    result = _feishu_api(
        "PUT",
        f"{_SHEETS_BASE}/spreadsheets/{spreadsheet_token}/values",
        body={"valueRange": {"range": range_str, "values": values}},
    )

    return result is not None


def _col_letter(n: int) -> str:
    """将列号(1-based)转换为 Excel 列字母。例如: 1->A, 27->AA。"""
    result = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _make_value_range(
    sheet_id: str, start_row: int, start_col: int, end_row: int, end_col: int
) -> str:
    """构建 sheet range 字符串，如 'sht12!A1:D10'。"""
    return (
        f"{sheet_id}!"
        f"{_col_letter(start_col + 1)}{start_row + 1}:"
        f"{_col_letter(end_col)}{end_row}"
    )


def _clear_sheet_data(
    spreadsheet_token: str, sheet_id: str, keep_header: bool = True
) -> bool:
    """清除表格数据，可选择保留标题行。"""
    if keep_header:
        # 获取当前行数
        result = _feishu_api(
            "GET",
            f"{_SHEETS_BASE}/spreadsheets/{spreadsheet_token}"
            f"/values/{sheet_id}",
        )
        if result:
            values = result.get("valueRange", {}).get("values", [])
            if len(values) <= 1:
                return True  # 只有标题或无数据
            # 清除第2行开始的所有行 (但飞书 API 似乎没有直接清空的方法)
            # 用写入空值的方式
            empty_rows = [[""] * len(values[0]) for _ in range(len(values) - 1)]
            return _write_cells(
                spreadsheet_token, sheet_id, start_row=1, start_col=0, values=empty_rows
            )
    return True


# === 对外同步函数 ===

def sync_portfolio_to_feishu() -> bool:
    """
    同步当前持仓数据到飞书表格。

    读取 portfolio.json 并写入飞书电子表格。
    表头: 代码, 名称, 持仓成本, 当前价, 盈亏%, 持仓占比%, 更新时间

    Returns:
        bool: 同步是否成功
    """
    if not _check_config():
        return False

    try:
        # 读取持仓数据
        portfolio = _load_portfolio()
        if not portfolio:
            logger.warning("[飞书表格] 持仓文件为空或不存在")
            return False

        holdings = portfolio.get("holdings", [])
        if not holdings:
            logger.info("[飞书表格] 无持仓数据")
            return True

        # 准备表头和数据
        headers = [
            "代码", "名称", "持仓成本", "当前价",
            "盈亏%", "持仓占比%", "股数", "更新时间",
        ]

        # 确保标题行
        _ensure_header_row(
            FEISHU_SPREADSHEET_TOKEN, FEISHU_PORTFOLIO_SHEET_ID, headers
        )

        # 清除旧数据 (保留标题)
        _clear_sheet_data(FEISHU_SPREADSHEET_TOKEN, FEISHU_PORTFOLIO_SHEET_ID)

        # 构建数据行
        rows = []
        for h in holdings:
            rows.append([
                h.get("symbol", ""),
                h.get("name", ""),
                str(h.get("cost_price", "")),
                str(h.get("current_price", "")),
                str(h.get("profit_pct", "")),
                str(h.get("weight_pct", "")),
                str(h.get("shares", "")),
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            ])

        # 写入数据
        ok = _write_cells(
            FEISHU_SPREADSHEET_TOKEN,
            FEISHU_PORTFOLIO_SHEET_ID,
            start_row=1,
            start_col=0,
            values=rows,
        )

        if ok:
            logger.info(f"[飞书表格] 持仓同步成功: {len(rows)} 条记录")

        return ok

    except Exception as e:
        logger.error(f"[飞书表格] 持仓同步异常: {e}")
        return False


def sync_daily_report_to_feishu(date: str | None = None) -> bool:
    """
    同步每日分析报告数据到飞书表格。

    Args:
        date: 日期字符串 (YYYY-MM-DD)，默认今天

    Returns:
        bool: 同步是否成功
    """
    if not _check_config():
        return False

    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    try:
        # 尝试加载当日报告数据
        report_data = _load_daily_report(date)
        if report_data is None:
            logger.info(f"[飞书表格] 无 {date} 的报告数据")
            return True

        headers = [
            "日期", "标的代码", "标的名称", "评级",
            "关键指标", "技术信号", "风险等级", "备注",
        ]

        _ensure_header_row(FEISHU_SPREADSHEET_TOKEN, FEISHU_REPORT_SHEET_ID, headers)
        _clear_sheet_data(FEISHU_SPREADSHEET_TOKEN, FEISHU_REPORT_SHEET_ID)

        # 从报告数据提取行
        rows = _extract_report_rows(report_data, date)

        ok = _write_cells(
            FEISHU_SPREADSHEET_TOKEN,
            FEISHU_REPORT_SHEET_ID,
            start_row=1,
            start_col=0,
            values=rows,
        )

        if ok:
            logger.info(f"[飞书表格] 报告同步成功: {date}, {len(rows)} 条")

        return ok

    except Exception as e:
        logger.error(f"[飞书表格] 报告同步异常: {e}")
        return False


def sync_news_to_feishu(news_items: list[dict[str, Any]]) -> bool:
    """
    同步新闻列表到飞书表格。

    Args:
        news_items: 新闻条目列表，每条包含 title, source, time, summary, url

    Returns:
        bool: 同步是否成功
    """
    if not _check_config():
        return False

    if not news_items:
        logger.info("[飞书表格] 无新闻数据")
        return True

    try:
        headers = ["标题", "来源", "时间", "摘要", "链接", "相关标的", "同步时间"]

        _ensure_header_row(FEISHU_SPREADSHEET_TOKEN, FEISHU_NEWS_SHEET_ID, headers)
        _clear_sheet_data(FEISHU_SPREADSHEET_TOKEN, FEISHU_NEWS_SHEET_ID)

        sync_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows = []
        for item in news_items:
            rows.append([
                item.get("title", ""),
                item.get("source", ""),
                item.get("time", ""),
                item.get("summary", ""),
                item.get("url", ""),
                item.get("related_symbols", ""),
                sync_time,
            ])

        ok = _write_cells(
            FEISHU_SPREADSHEET_TOKEN,
            FEISHU_NEWS_SHEET_ID,
            start_row=1,
            start_col=0,
            values=rows,
        )

        if ok:
            logger.info(f"[飞书表格] 新闻同步成功: {len(rows)} 条")

        return ok

    except Exception as e:
        logger.error(f"[飞书表格] 新闻同步异常: {e}")
        return False


# === 内部辅助函数 ===

def _check_config() -> bool:
    """检查必要的配置是否就绪。"""
    missing = []
    if not FEISHU_APP_ID:
        missing.append("FEISHU_APP_ID")
    if not FEISHU_APP_SECRET:
        missing.append("FEISHU_APP_SECRET")
    if not FEISHU_SPREADSHEET_TOKEN:
        missing.append("FEISHU_SPREADSHEET_TOKEN")

    if missing:
        logger.error(
            f"[飞书表格] 缺少配置: {', '.join(missing)}"
            f" — 请在 .env 中设置"
        )
        return False
    return True


def _load_portfolio() -> dict[str, Any] | None:
    """加载持仓文件。"""
    portfolio_path = PORTFOLIO_FILE
    if not portfolio_path.exists():
        # 尝试 STOCK_DATA_DIR 下的 portfolio.json
        alt_path = STOCK_DATA_DIR / "portfolio.json"
        if alt_path.exists():
            portfolio_path = alt_path
        else:
            return None

    try:
        with open(portfolio_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"[飞书表格] 持仓文件读取失败: {e}")
        return None


def _load_daily_report(date: str) -> dict[str, Any] | None:
    """加载指定日期的报告数据。"""
    # 搜索顺序: STOCK_DATA_DIR/reports/, STOCK_DATA_DIR/
    report_paths = [
        STOCK_DATA_DIR / "reports" / f"daily_report_{date}.json",
        STOCK_DATA_DIR / f"daily_report_{date}.json",
        STOCK_DATA_DIR / "reports" / f"report_{date}.json",
    ]
    for rp in report_paths:
        if rp.exists():
            try:
                with open(rp, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"[飞书表格] 报告文件读取失败: {rp}: {e}")
                return None
    return None


def _extract_report_rows(
    report: dict[str, Any], date: str
) -> list[list[Any]]:
    """从报告数据中提取行。"""
    rows = []
    analyses = report.get("analyses", report.get("stocks", []))
    if not analyses:
        # 尝试将整体报告作为单行
        rows.append([
            date,
            report.get("symbol", "---"),
            report.get("name", report.get("title", "---")),
            report.get("rating", report.get("grade", "---")),
            report.get("key_metrics", report.get("indicators", "---")),
            report.get("signal", report.get("technical", "---")),
            report.get("risk", "---"),
            report.get("note", report.get("remark", "---")),
        ])
    else:
        for a in analyses:
            rows.append([
                a.get("date", date),
                a.get("symbol", "---"),
                a.get("name", "---"),
                a.get("rating", a.get("grade", "---")),
                a.get("key_metrics", str(a.get("indicators", "---"))),
                a.get("signal", str(a.get("technical", "---"))),
                a.get("risk", "---"),
                a.get("note", a.get("remark", "---")),
            ])
    return rows


# === 自测 ===

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("飞书表格同步器自测...")

    if not _check_config():
        logger.warning(
            "飞书表格配置不完整。请在 .env 中设置:\n"
            "  FEISHU_APP_ID\n"
            "  FEISHU_APP_SECRET\n"
            "  FEISHU_SPREADSHEET_TOKEN\n"
            "  FEISHU_PORTFOLIO_SHEET_ID  (可选)\n"
            "  FEISHU_REPORT_SHEET_ID     (可选)\n"
            "  FEISHU_NEWS_SHEET_ID       (可选)"
        )
    else:
        # 测试 Token 获取
        token = _get_tenant_access_token()
        if token:
            logger.info("[飞书表格] Tenant Token 获取成功")
        else:
            logger.warning("[飞书表格] Tenant Token 获取失败")

        # 测试持仓同步
        sync_portfolio_to_feishu()
