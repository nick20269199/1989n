"""
ai_news_pipeline.py — AI 新闻 → 题材 → 个股 穿透管线

对标 XyStock AI资讯 + 个股模式:
  新闻 → 识别题材/板块 → 板块内个股筛选 (基本面+估值) → 排序输出

数据流:
  news_scheduler 08:00 JSON → 题材识别 → 个股穿透 (XyStock PE + 代码名称) → 结构输出

用法:
  from ai_news_pipeline import drill_news_to_stocks
  result = drill_news_to_stocks()  # 自动读最新新闻
  # 或指定文件:
  result = drill_news_to_stocks(news_file="news_manual_20260526_0800.json")
"""

import json
import logging
import re
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from xy_stock_bridge import XyStockBridge

logger = logging.getLogger("ai_news_pipeline")

CST = timezone(timedelta(hours=8))
STOCK_DATA = Path("D:/1989n/stock_data")
CONCEPT_STOCKS_FILE = STOCK_DATA / "concept_stocks.json"

# ── 题材关键词映射（扩展版，来源: XyStock block_list 列 + 市场常见题材） ──

THEME_KEYWORDS: dict[str, list[str]] = {
    # 大科技
    "半导体/芯片": ["半导体", "芯片", "晶圆", "封测", "光刻", "集成电路", "IC设计", "存储芯片", "Chiplet"],
    "AI/算力": ["AI", "算力", "大模型", "人工智能", "Token", "智能体", "AIGC", "多模态", "GPT", "DeepSeek",
                "训练", "推理", "算力租赁"],
    "通信/5G/6G": ["5G", "6G", "通信", "光模块", "光纤", "CPO", "硅光", "卫星通信"],
    "机器人": ["机器人", "人形机器人", "灵巧手", "减速器", "关节模组", "滚柱丝杠", "空心杯电机"],
    "低空经济/航天": ["低空经济", "eVTOL", "飞行汽车", "商业航天", "卫星互联", "航天", "军工"],
    # 新能源
    "新能源车": ["新能源车", "电动车", "锂电", "充电桩", "固态电池", "碳酸锂", "整车"],
    "光伏/储能": ["光伏", "太阳能", "储能", "虚拟电厂", "微逆", "逆变器", "HJT", "TopCon"],
    "电力/电网": ["电力", "电网", "特高压", "变压器", "电力改革"],
    # 金融
    "券商/金融": ["券商", "证券", "保险", "银行", "金融科技", "数字货币", "跨境支付"],
    # 消费
    "消费": ["消费", "白酒", "食品饮料", "免税", "零售", "旅游", "家电", "地产"],
    # 医药
    "医药": ["医药", "创新药", "CXO", "生物医药", "中药", "医疗器械"],
    # 周期/资源
    "资源/有色": ["有色", "黄金", "铜", "铝", "锂矿", "稀土", "钢铁", "煤炭"],
    # 新题材
    "鸿蒙/信创": ["鸿蒙", "信创", "国产替代", "自主可控", "操作系统", "数据库", "数字中国"],
    "数据要素": ["数据要素", "数据资产", "大数据", "数据交易"],
}


# 题材 → concept_stocks.json 名称映射（因为两者命名不完全一致）
THEME_TO_CONCEPT_MAP: dict[str, list[str]] = {
    "半导体/芯片": ["半导体"],
    "AI/算力": ["AI/算力"],
    "通信/5G/6G": ["通信/5G"],
    "机器人": ["机器人"],
    "新能源车": ["新能源车"],
    "光伏/储能": ["光伏/新能源"],
    "券商/金融": ["金融"],
    "消费": ["消费/白酒"],
    "医药": ["医药"],
    "军工/航天": ["军工/航天"],     # 可能没有
    "低空经济/航天": ["军工/航天"],  # fallback 到军工/航天
    "电力/电网": [],
    "资源/有色": [],
    "鸿蒙/信创": [],
    "数据要素": [],
}


class NewsThemeDriller:
    """新闻 → 题材 → 个股 穿透引擎"""

    def __init__(self, bridge: Optional[XyStockBridge] = None):
        self.bridge = bridge or XyStockBridge()
        self.concept_stocks = self._load_concept_stocks()

    # ── 加载 ─────────────────────────────────────────────

    def _load_concept_stocks(self) -> dict:
        if CONCEPT_STOCKS_FILE.exists():
            try:
                return json.loads(CONCEPT_STOCKS_FILE.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("concept_stocks.json 加载失败: %s", e)
        return {}

    def load_latest_news(self, news_file: Optional[str] = None) -> list[dict]:
        """加载最新一期新闻（默认自动找最新的 news_manual_ 或 news_intraday_）。"""
        if news_file:
            fp = STOCK_DATA / news_file
            if fp.exists():
                data = json.loads(fp.read_text(encoding="utf-8"))
                items = data.get("data", [])
                logger.info("加载新闻: %s (%d条)", fp.name, len(items))
                return items
            logger.warning("指定的新闻文件不存在: %s", news_file)
            return []

        # 自动找最新
        today = datetime.now(CST).strftime("%Y%m%d")
        patterns = [
            f"news_manual_{today}_*.json",
            f"news_manual_*_{today}_*.json",
            "news_intraday_*.json",
            f"news_evening_{today}_*.json",
        ]
        for pat in patterns:
            files = sorted(STOCK_DATA.glob(pat))
            if files:
                data = json.loads(files[-1].read_text(encoding="utf-8"))
                items = data.get("data", [])
                if items:
                    logger.info("自动加载新闻: %s (%d条)", files[-1].name, len(items))
                    return items

        logger.warning("未找到今日新闻文件")
        return []

    # ── 题材识别 ─────────────────────────────────────────

    def identify_themes(self, news_items: list[dict]) -> dict[str, dict]:
        """从新闻标题识别覆盖的题材，返回 {题材名: {count, news_titles, stocks_direct}}。"""
        theme_hits: dict[str, list[str]] = defaultdict(list)
        direct_codes: dict[str, set] = defaultdict(set)

        for item in news_items:
            title = item.get("title", "")
            if not title:
                continue

            # 1) 通过题材关键词匹配
            for theme, kws in THEME_KEYWORDS.items():
                if any(kw in title for kw in kws):
                    theme_hits[theme].append(title)

            # 2) 直接标注的股票代码 (CLS API 自带的 related_stocks)
            related_raw = item.get("related_stocks", "")
            if related_raw:
                codes = [c.strip() for c in related_raw.split(",") if c.strip().isdigit()]
                # 把 code 归到题材 — 我们通过概念映射表回查
                for theme_ck, stock_list in self.concept_stocks.items():
                    for s in stock_list:
                        if s["code"] in codes:
                            direct_codes[theme_ck].add(s["code"])

        result = {}
        for theme, titles in theme_hits.items():
            result[theme] = {
                "count": len(titles),
                "news_titles": titles[:8],  # 最多保留8条标题
                "direct_codes": list(direct_codes.get(theme, set())),
            }
        return result

    # ── 个股穿透 ─────────────────────────────────────────

    # 非A股个股代码前缀（ETF/指数/分级基金/转债等，需过滤）
    _NON_STOCK_PREFIXES = ("15", "159", "51", "511", "512", "513", "514", "515", "516", "517", "518",
                           "520", "56", "58", "588", "1599", "16", "9200")

    @staticmethod
    def _is_stock_code(code: str) -> bool:
        """判断是否为A股正股代码（非ETF/指数/分级基金/转债）。"""
        if not code.isdigit() or len(code) != 6:
            return False
        if code.startswith(NewsThemeDriller._NON_STOCK_PREFIXES):
            return False
        # 399xxx/899xxx 等为指数代码
        if code.startswith("399") or code.startswith("899"):
            return False
        return True

    def _get_theme_candidates(self, theme: str) -> list[dict]:
        """通过多级映射获取题材的成分股候选。"""
        # 1) 直接匹配 concept_stocks.json
        candidates = self.concept_stocks.get(theme, [])
        if candidates:
            return list(candidates)

        # 2) 通过题材→概念映射表查询
        for mapped_name in THEME_TO_CONCEPT_MAP.get(theme, []):
            candidates = self.concept_stocks.get(mapped_name, [])
            if candidates:
                return list(candidates)

        # 3) 兜底: 通过 XyStock 名称搜索
        logger.info("题材 '%s' 无预配置成分股，尝试名称搜索", theme)
        keywords = THEME_KEYWORDS.get(theme, [theme])
        for kw in keywords[:3]:
            matches = self.bridge.reader.search_by_name(kw)
            for m in matches[:10]:
                if self._is_stock_code(m.code):
                    candidates.append({"code": m.code, "name": m.cn_name_simplified or m.en_name})
            if candidates:
                break

        return candidates

    def drill_stocks(self, theme: str) -> list[dict]:
        """对单个题材做个股穿透，返回带基本面数据的筛选结果。"""
        candidates = self._get_theme_candidates(theme)

        if not candidates:
            return []

        # 对每个候选股做基本面穿透
        results = []
        for stock in candidates:
            code = stock["code"]
            name = stock.get("name", "")

            # 从 XyStock .fnc 获取 PE
            pe = self.bridge.get_pe_ratio(code)
            info = self.bridge.get_stock_info(code)

            stock_data = {
                "code": code,
                "name": name or (info.get("name", "") if info else ""),
                "pe": round(pe, 2) if pe and abs(pe) < 1e6 else None,
                "market": info.get("market", "") if info else "",
            }
            results.append(stock_data)

        # 按 PE 升序排列（低估值优先），None 排最后
        results.sort(key=lambda x: (x["pe"] is None, x["pe"] if x["pe"] else 99999))
        return results

    # ── 管线入口 ─────────────────────────────────────────

    def run(self, news_file: Optional[str] = None, top_n: int = 5) -> dict:
        """执行完整的 新闻→题材→个股 穿透。

        Args:
            news_file: 指定新闻文件，None=自动找最新
            top_n: 每题材最多保留几只个股

        Returns:
            {
                "generated_at": "2026-05-26 08:00",
                "news_source": "...",
                "themes": {
                    "题材名": {
                        "count": 新闻数,
                        "news_titles": [...],
                        "stocks": [
                            {"code": "600000", "name": "浦发银行", "pe": 5.2, "market": "SH"},
                        ]
                    }
                },
                "total_themes": 5,
                "total_news": 100,
            }
        """
        news = self.load_latest_news(news_file)
        if not news:
            return {"error": "无新闻数据", "themes": {}, "total_themes": 0, "total_news": 0}

        # 1) 识别题材
        themes_raw = self.identify_themes(news)

        # 2) 个股穿透
        themes_output = {}
        for theme_name in sorted(themes_raw.keys(), key=lambda t: themes_raw[t]["count"], reverse=True):
            meta = themes_raw[theme_name]
            stocks = self.drill_stocks(theme_name)
            themes_output[theme_name] = {
                "count": meta["count"],
                "news_titles": meta["news_titles"],
                "stocks": stocks[:top_n],
            }

        # 3) 统计
        news_file_used = ""
        if news_file:
            news_file_used = news_file
        else:
            today = datetime.now(CST).strftime("%Y%m%d")
            for pat in [f"news_manual_{today}_*.json", "news_intraday_*.json"]:
                files = sorted(STOCK_DATA.glob(pat))
                if files:
                    news_file_used = files[-1].name
                    break

        return {
            "generated_at": datetime.now(CST).strftime("%Y-%m-%d %H:%M"),
            "news_source": news_file_used,
            "themes": themes_output,
            "total_themes": len(themes_output),
            "total_news": len(news),
        }


# ── 快捷入口 ─────────────────────────────────────────────

def drill_news_to_stocks(news_file: Optional[str] = None, top_n: int = 5) -> dict:
    """快捷入口: 执行新闻→题材→个股穿透"""
    driller = NewsThemeDriller()
    return driller.run(news_file=news_file, top_n=top_n)


def format_brief_section(result: dict) -> str:
    """将穿透结果格式化为晨报可嵌入的文本块"""
    if not result or "themes" not in result or not result["themes"]:
        return "（AI新闻穿透: 今日无显著题材信号）"

    lines = []
    lines.append("## AI新闻穿透 — 题材→个股精选")
    lines.append(f"> 基于 {result.get('news_source', '最新新闻')} 自动识别题材并穿透到个股，含 PE 估值参考。")
    lines.append("")

    for theme_name, meta in result["themes"].items():
        count = meta["count"]
        lines.append(f"### {theme_name} ({count}条新闻)")

        # 新闻标题摘要
        for t in meta["news_titles"][:3]:
            short = t[:60] + "..." if len(t) > 60 else t
            lines.append(f"  - {short}")

        # 个股穿透结果
        stocks = meta.get("stocks", [])
        if stocks:
            lines.append("")
            lines.append("| 代码 | 名称 | PE | 市场 |")
            lines.append("|------|------|-----|------|")
            for s in stocks:
                pe_str = f"{s['pe']:.1f}" if s["pe"] else "N/A"
                lines.append(f"| {s['code']} | {s['name']} | {pe_str} | {s['market']} |")
        lines.append("")

    lines.append(f"---\n*AI穿透 {datetime.now(CST).strftime('%H:%M')} 生成，{result['total_news']}条新闻覆盖{result['total_themes']}个题材*")
    return "\n".join(lines)


# ── 自检 ──
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("=" * 60)
    print("AI 新闻穿透管线 — 测试")
    print("=" * 60)

    result = drill_news_to_stocks()

    if "error" in result:
        print(f"\n错误: {result['error']}")
    else:
        print(f"\n新闻来源: {result.get('news_source', '?')}")
        print(f"新闻总数: {result['total_news']}")
        print(f"识别题材: {result['total_themes']} 个\n")

        for theme_name, meta in result["themes"].items():
            print(f"\n{'=' * 50}")
            print(f"【{theme_name}】({meta['count']}条)")
            for t in meta["news_titles"][:2]:
                print(f"  新闻: {t[:80]}")
            stocks = meta.get("stocks", [])
            if stocks:
                print(f"  穿透个股 ({len(stocks)}只):")
                for s in stocks:
                    pe = f"PE={s['pe']}" if s['pe'] else "PE=N/A"
                    print(f"    {s['code']} {s['name']} | {pe} | {s['market']}")
            else:
                print(f"  无匹配个股 (需补充 concept_stocks.json)")
