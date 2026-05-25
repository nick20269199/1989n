#!D:/Python314/python
"""
Morning Brief v2.0 — 08:30前产出高质量盘前晨报
==============================================
数据源: CLS新闻(8:00采集) + akshare美股 + 全市场股票名称标注
输出: stock_data/morning_brief_latest.md (.json)
触发: cron 8:27

质量要求:
- 每条新闻标注受益A股标的
- 导读4-5条核心摘要，30秒掌握重点
- 地雷阵/解禁/异动完整覆盖
- 达不到可交易标准不发
"""

from error_capture import trap; trap()

import json
import logging
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import akshare as ak
import requests

from config import STOCK_DATA_DIR, HEADERS, PORTFOLIO_FILE

STOCK_DATA = Path(STOCK_DATA_DIR)
CONCEPT_MAP_FILE = STOCK_DATA / "concept_mapping.json"
STOCK_LOOKUP_FILE = STOCK_DATA / "stock_name_lookup.json"
CONCEPT_STOCKS_FILE = STOCK_DATA / "concept_stocks.json"
OUTPUT_MD = STOCK_DATA / "morning_brief_latest.md"
OUTPUT_JSON = STOCK_DATA / "morning_brief_latest.json"

CST = timezone(timedelta(hours=8))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("morning_brief")


# ═══════════════════════════════════════════════════════════════
# 1. DATA COLLECTION
# ═══════════════════════════════════════════════════════════════

def load_latest_news() -> list[dict]:
    """加载今日8:00 CLS新闻。"""
    today = datetime.now(CST).strftime("%Y%m%d")
    pattern = f"news_manual_{today}_*.json"
    files = sorted(STOCK_DATA.glob(pattern))
    if not files:
        yesterday = (datetime.now(CST) - timedelta(days=1)).strftime("%Y%m%d")
        files = sorted(STOCK_DATA.glob(f"news_manual_{yesterday}_*.json"))
    if not files:
        logger.warning("No CLS news file found")
        return []
    latest = files[-1]
    data = json.loads(latest.read_text(encoding="utf-8"))
    items = data.get("data", [])
    logger.info(f"Loaded {len(items)} news from {latest.name}")
    return items


def fetch_us_market() -> dict:
    """获取美股收盘数据+板块龙头。"""
    result = {"indices": [], "sector_leaders": [], "timestamp": ""}

    # 美股指数
    symbols = [
        ("道琼斯", ".DJI"),
        ("纳斯达克", ".IXIC"),
        ("标普500", ".INX"),
    ]
    for name, symbol in symbols:
        try:
            df = ak.index_us_stock_sina(symbol=symbol)
            if df is not None and len(df) >= 2:
                last = df.iloc[-1]
                prev = float(df.iloc[-2].get("close", 0))
                curr = float(last["close"])
                chg = round((curr - prev) / prev * 100, 2) if prev else 0.0
                result["indices"].append({
                    "name": name, "price": round(curr, 0),
                    "change_pct": chg,
                })
        except Exception as e:
            logger.warning(f"US {name} fetch failed: {e}")

    # 美股板块龙头
    leaders = [
        ("AMD", "105.AMD", "半导体封测"),
        ("英特尔", "105.INTC", "半导体/CPU"),
        ("英伟达", "105.NVDA", "AI算力/GPU"),
        ("美光科技", "105.MU", "存储芯片"),
        ("阿斯麦", "105.ASML", "光刻机/设备"),
        ("特斯拉", "105.TSLA", "新能源车/机器人"),
        ("苹果", "105.AAPL", "消费电子"),
        ("谷歌", "105.GOOGL", "AI/云计算"),
        ("微软", "105.MSFT", "AI/软件"),
        ("台积电", "105.TSM", "半导体代工"),
    ]
    for name, ticker, concept in leaders:
        for attempt in range(3):
            try:
                df = ak.stock_us_hist(symbol=ticker, period="daily", start_date="20260101", end_date="20501231")
                if df is not None and len(df) >= 1:
                    last = df.iloc[-1]
                    result["sector_leaders"].append({
                        "name": name, "concept": concept,
                        "price": round(float(last.get("收盘", 0)), 2),
                        "change_pct": round(float(last.get("涨跌幅", 0)), 2),
                    })
                break
            except Exception:
                time.sleep(0.5)
    if result["indices"]:
        result["timestamp"] = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    logger.info(f"US indices: {len(result['indices'])} | leaders: {len(result['sector_leaders'])}")
    return result


# ═══════════════════════════════════════════════════════════════
# 2. STOCK LOOKUP & NEWS ANNOTATION
# ═══════════════════════════════════════════════════════════════

def load_stock_lookup() -> dict:
    """加载全市场股票名称→代码 + 代码→名称 查表。"""
    if not STOCK_LOOKUP_FILE.exists():
        logger.warning("stock_name_lookup.json not found")
        return {}
    data = json.loads(STOCK_LOOKUP_FILE.read_text(encoding="utf-8"))
    name_to_code = data.get("name_to_code", {})

    # 构建反向映射：代码→名称
    code_to_name = {}
    for name, code in name_to_code.items():
        clean_name = name.replace(" ", "")
        if code not in code_to_name or len(clean_name) < len(code_to_name[code]):
            code_to_name[code] = clean_name

    # 构建名称匹配索引：清洗后名称 → (原始名称, code)，按长度降序
    cleaned_index = {}
    for name, code in name_to_code.items():
        clean = re.sub(r"[*\s]", "", name)
        if len(clean) >= 2 and clean not in cleaned_index:
            cleaned_index[clean] = (name.replace(" ", ""), code)

    sorted_names = sorted(cleaned_index.keys(), key=len, reverse=True)

    # 常见误匹配词（在新闻中频繁出现但不是股票指向）
    false_positive = {
        "中国", "上涨", "下跌", "涨停", "跌停", "反弹", "回落", "震荡",
        "公布", "报道", "发布", "消息", "记者", "编辑", "作者",
        "今日", "周一", "周二", "周三", "周四", "周五", "周六", "周日",
        "上午", "下午", "盘中", "尾盘", "开盘", "收盘",
        "国际", "国内", "美国", "欧洲", "亚太", "全球",
        "期货", "现货", "合约", "主力", "国债", "汇率",
        "创始人", "董事长", "总裁", "总经理",
        "同比", "环比", "预期", "实际", "前值",
    }

    return {
        "name_to_code": name_to_code,
        "code_to_name": code_to_name,
        "name_index": (cleaned_index, sorted_names, false_positive),
    }


def _match_stock_names_in_text(text: str, name_index: tuple) -> list[dict]:
    """在文本中匹配股票名称，返回 [{"code":, "name":}, ...]。

    用清洗后的名称查表，按长度降序匹配（长名优先），
    同一位置不会被短名覆盖。
    """
    cleaned_index, sorted_names, false_positive = name_index
    clean_text = re.sub(r"[*\s]", "", text)

    matched = []
    matched_positions = set()

    for clean_name in sorted_names:
        if clean_name in false_positive:
            continue

        idx = clean_text.find(clean_name)
        if idx == -1:
            continue

        # 检查是否与已有匹配重叠
        pos_range = set(range(idx, idx + len(clean_name)))
        if pos_range & matched_positions:
            continue  # 被更长名称覆盖了

        _, code = cleaned_index[clean_name]
        matched.append({"code": code, "name": clean_name})
        matched_positions |= pos_range

    return matched


def load_concept_map() -> dict:
    """加载概念→持仓映射表。"""
    if CONCEPT_MAP_FILE.exists():
        return json.loads(CONCEPT_MAP_FILE.read_text(encoding="utf-8"))
    return {"keyword_to_holdings": {}, "holdings": {}}


def load_concept_stocks() -> dict:
    """加载行业→代表股票映射（用于概念匹配回退）。"""
    if CONCEPT_STOCKS_FILE.exists():
        return json.loads(CONCEPT_STOCKS_FILE.read_text(encoding="utf-8"))
    return {}


def load_holdings() -> dict:
    """从 portfolio.json 加载当前持仓（唯一权威来源）。"""
    try:
        data = json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
        return {h["code"]: {"name": h["name"], "sector": h.get("sector", "")} for h in data.get("holdings", [])}
    except Exception as e:
        logger.warning(f"持仓加载失败: {e}")
        return {}


# 概念关键词→查表名称映射
CONCEPT_TRIGGERS = {
    "半导体": ["半导体", "芯片", "晶圆", "封测", "光刻", "存储"],
    "AI/算力": ["AI", "算力", "大模型", "人工智能", "Token", "智能体"],
    "光伏/新能源": ["光伏", "太阳能", "风电", "风能", "储能", "新能源"],
    "新能源车": ["新能源车", "电动车", "电动汽车", "锂电", "充电桩"],
    "机器人": ["机器人", "人形机器人", "自动化", "智能制造"],
    "军工/航天": ["军工", "航天", "航空", "国防", "船舶"],
    "通信/5G": ["5G", "6G", "通信", "光模块", "光纤"],
    "消费/白酒": ["白酒", "消费升级", "消费市场", "消费板块", "消费品", "消费电子",
                    "食品", "饮料", "免税", "零售"],
    "金融": ["银行", "券商", "证券", "保险", "降息", "降准"],
    "医药": ["医药", "医疗", "创新药", "CXO", "生物", "药企"],
}

# 不应触发概念匹配的关键词（在标题中匹配到这些词就不触发对应概念）
CONCEPT_TRIGGER_EXCLUDES = {
    "消费/白酒": ["消费基金"],
    "金融": ["非银"],
}


def _match_concept_stocks(title: str, concept_stocks: dict) -> list[dict]:
    """从标题匹配行业概念，返回对应代表股票。"""
    matched = []
    seen = set()
    for concept, trigger_kws in CONCEPT_TRIGGERS.items():
        # 先检查排除词
        excludes = CONCEPT_TRIGGER_EXCLUDES.get(concept, [])
        if any(ex in title for ex in excludes):
            continue
        if any(kw in title for kw in trigger_kws):
            stocks = concept_stocks.get(concept, [])
            for s in stocks:
                if s["code"] not in seen:
                    matched.append(s)
                    seen.add(s["code"])
    return matched[:6]  # 最多6只


def annotate_news_with_stocks(news_items: list[dict], lookup: dict) -> list[dict]:
    """对每条新闻标注受益A股标的。

    优先级：
    1. CLS API自带的 related_stocks（支持CSV格式和dict-string格式）
    2. 股票名称匹配回退（使用全市场股票名称查表）
    3. 行业概念回退（新闻标题匹配→行业代表股）

    返回增强后的新闻列表，每条增加 'matched_stocks' 字段:
    [{"code": "000001", "name": "平安银行"}, ...]
    """
    code_to_name = lookup.get("code_to_name", {})
    name_index = lookup.get("name_index")
    concept_stocks_data = load_concept_stocks()
    annotated = []

    for item in news_items:
        title = item.get("title", "")
        matched = []
        seen = set()

        # 1) CLS自带标注
        cls_stocks_raw = item.get("related_stocks", "")
        if cls_stocks_raw:
            codes = _parse_cls_stocks(cls_stocks_raw)
            for code in codes:
                if code in seen:
                    continue
                if len(code) == 6 and code[0] in ("0", "3", "6"):
                    if code.startswith("399"):
                        continue  # 指数代码
                    sname = code_to_name.get(code, "")
                    matched.append({"code": code, "name": sname or code})
                    seen.add(code)

        # 2) 名称匹配回退
        if not matched and name_index:
            name_matches = _match_stock_names_in_text(title, name_index)
            for m in name_matches:
                if m["code"] not in seen:
                    matched.append(m)
                    seen.add(m["code"])

        # 3) 行业概念回退（标题有行业关键词但没提到具体股票时用）
        if not matched and concept_stocks_data:
            concept_matches = _match_concept_stocks(title, concept_stocks_data)
            for m in concept_matches:
                if m["code"] not in seen:
                    matched.append(m)
                    seen.add(m["code"])

        annotated.append({**item, "matched_stocks": matched})

    return annotated

    annotated_count = sum(1 for n in annotated if n["matched_stocks"])
    logger.info(f"Annotated {annotated_count}/{len(annotated)} news items "
                f"({sum(1 for n in annotated if n.get('related_stocks'))} from CLS, "
                f"{annotated_count - sum(1 for n in annotated if n.get('related_stocks'))} from name match)")
    return annotated


def _parse_cls_stocks(raw: str) -> list[str]:
    """解析CLS相关股票字段。

    支持两种格式：
    - CSV: "002031,002181,603986"
    - dict-string: "{'StockID': 'sz002031', ...}, {...}"
    """
    if not raw or not isinstance(raw, str):
        return []

    # dict-string 格式：包含 StockID 字段
    if "StockID" in raw or "stock_id" in raw.lower():
        codes = []
        # 提取所有 StockID 值
        for m in re.finditer(r"'StockID':\s*'([^']+)'", raw):
            sid = m.group(1)
            # 去掉 sz/sh/bj 前缀
            code = sid[2:] if sid.startswith(("sz", "sh", "bj")) else sid
            if code.isdigit() and len(code) == 6:
                codes.append(code)
        return codes

    # CSV格式：纯逗号分隔
    codes = [c.strip() for c in raw.split(",") if c.strip()]
    return [c for c in codes if c.isdigit() and len(c) == 6]


# ═══════════════════════════════════════════════════════════════
# 3. ANALYSIS
# ═══════════════════════════════════════════════════════════════

def detect_topics(news_items: list[dict]) -> list[dict]:
    """检测热点主题，返回按主题聚合的列表。

    每个主题: {
        "topic": "SpaceX上市",
        "keywords": ["SpaceX", "商业航天", "星舰"],
        "news": [...],
        "stocks": [...],
        "importance": 0-10
    }
    """
    # 预定义热点主题关键词
    topic_keywords = {
        "SpaceX/商业航天": ["SpaceX", "星舰", "商业航天", "太空", "卫星", "火箭"],
        "半导体": ["半导体", "芯片", "晶圆", "封测", "存储", "光刻", "昇腾"],
        "AI/算力": ["AI", "人工智能", "大模型", "算力", "Token", "智能体"],
        "新能源车": ["新能源车", "电动车", "锂电", "充电", "固态电池"],
        "白酒/消费": ["茅台", "白酒", "消费", "零售", "免税"],
        "房地产/基建": ["房地产", "楼市", "基建", "城市更新", "土拍"],
        "医药/医疗": ["医药", "医疗", "创新药", "CXO", "生物"],
        "金融/政策": ["央行", "证监会", "降息", "降准", "利率"],
        "机器人": ["机器人", "人形机器人", "灵巧手", "自动化"],
        "光伏/新能源": ["光伏", "风电", "储能", "新能源"],
        "军工": ["军工", "航天", "国防", "装备"],
        "外贸/关税": ["关税", "贸易", "出口", "制裁", "反制"],
    }

    # 每条新闻匹配主题
    topic_items = defaultdict(list)
    for item in news_items:
        title = (item.get("title") or "") + " " + (item.get("content") or "")
        matched = False
        for topic, keywords in topic_keywords.items():
            if any(kw in title for kw in keywords):
                topic_items[topic].append(item)
                matched = True
        if not matched:
            topic_items["其他"].append(item)

    # 计算主题重要性（新闻数+匹配强度）
    topics = []
    for topic, items in topic_items.items():
        if topic == "其他":
            continue
        if len(items) < 2:
            continue  # 只聚2条以上的主题

        # 收集该主题涉及的所有股票
        all_stocks = []
        seen = set()
        for item in items:
            for s in item.get("matched_stocks", []):
                key = s["code"]
                if key not in seen:
                    all_stocks.append(s)
                    seen.add(key)

        topics.append({
            "topic": topic,
            "news": items,
            "stocks": all_stocks,
            "importance": len(items) * 2 + min(len(all_stocks), 10),
        })

    topics.sort(key=lambda t: t["importance"], reverse=True)
    logger.info(f"Detected {len(topics)} topics")
    return topics


def _is_research_article(title: str) -> bool:
    """判断是否为研报/投教/付费内容类文章，非公告。"""
    research_prefixes = [
        "【研选", "【风口研报", "【盘中宝", "【点金互动易",
        "【九点特供", "【电报解读", "【狙击龙虎榜",
        "【财联社早知道", "【公告全知道", "【机会挖掘",
        "【研报", "【数据复盘",
    ]
    return any(title.startswith(p) for p in research_prefixes)


def _is_company_announcement(title: str, stocks: list) -> bool:
    """判断是否为公司公告，而非泛行业新闻。

    公司公告特征：
    - 明确提到公司具体动作（合同/中标/减持/收购等）
    - 公司名来自CLS标注或名称匹配（非概念匹配），
      或者标题明显是公司公告格式
    """
    deal_kws = ["减持", "解禁", "合同", "中标", "收购", "签约",
                "投产", "交付", "扩产", "投资"]
    if not any(kw in title for kw in deal_kws):
        return False

    # 必须提到具体公司（有 matched_stocks）
    if not stocks:
        return False

    # 不允许泛指的行业新闻出现在公告中
    # 如果标题不含"："或公告关键词，更可能是行业新闻
    if not any(kw in title for kw in deal_kws):
        return False

    # 如果是泛行业报道（"A股掀起扩产潮"），不是公告
    broad_patterns = ["A股", "板块", "行业", "概念", "产业链"]
    if any(kw in title for kw in broad_patterns):
        return False

    return True


def extract_announcements_v2(news_items: list[dict]) -> dict:
    """提取公告类新闻：日常公告/地雷阵/解禁/异动。

    返回: {
        "contracts": [...],    # 合同/中标/投资
        "decreases": [...],    # 地雷阵（减持）
        "lockup": [...],       # 解禁
        "unusual": [...],      # 异动公告/澄清
        "restart": [...],      # 停复牌
    }
    """
    result = {"contracts": [], "decreases": [], "lockup": [],
              "unusual": [], "restart": []}

    for item in news_items:
        title = item.get("title", "")

        # 跳过研报/投教类文章
        if _is_research_article(title):
            continue

        stocks = item.get("matched_stocks", [])

        # 公告必须有具体公司指向
        if not _is_company_announcement(title, stocks):
            continue

        annotated = {**item, "stocks_summary": ",".join(s["name"] for s in stocks[:3]) if stocks else ""}

        if any(kw in title for kw in ["减持", "减持计划", "减持比例"]):
            result["decreases"].append(annotated)
        elif "解禁" in title:
            result["lockup"].append(annotated)
        elif any(kw in title for kw in ["停牌", "复牌", "摘帽", "ST"]):
            result["restart"].append(annotated)
        elif any(kw in title for kw in ["异动", "澄清", "说明", "未生产", "不存在"]):
            result["unusual"].append(annotated)
        elif any(kw in title for kw in ["合同", "中标", "收购", "投资", "项目", "订单", "签约",
                                          "投产", "扩产", "交付", "合作"]):
            result["contracts"].append(annotated)

    logger.info(f"Extracted: contracts={len(result['contracts'])} decreases={len(result['decreases'])} "
                f"lockup={len(result['lockup'])} unusual={len(result['unusual'])} restart={len(result['restart'])}")
    return result


def assess_holding_impact_v2(news_items: list[dict], us_data: dict, holdings: dict) -> list[dict]:
    """评估每只持仓的今日影响，基于硬规则。

    Returns: [{"code":, "name":, "direction":, "action":, "reason":, ...}]
    """
    # 收集每只持仓的相关新闻
    stock_news = defaultdict(list)
    for item in news_items:
        for s in item.get("matched_stocks", []):
            if s["code"] in holdings:
                stock_news[s["code"]].append(item)

    # 美股龙头→持仓映射
    leader_map = {
        "AMD": "002156", "英特尔": "002156", "英伟达": "002156",
        "美光科技": "002156", "阿斯麦": "300480", "特斯拉": "002050",
        "苹果": "300792", "台积电": "002156",
    }
    leader_hits = defaultdict(list)
    for leader in us_data.get("sector_leaders", []):
        code = leader_map.get(leader["name"])
        if code and abs(leader["change_pct"]) > 1:
            leader_hits[code].append(f"{leader['name']}({leader['change_pct']:+.1f}%)")

    results = []
    for code, info in holdings.items():
        news = stock_news.get(code, [])
        leaders = leader_hits.get(code, [])

        # 算分
        score = 0
        reasons = []

        # 美股龙头信号（change_pct负=美股跌=利空A股，正=美股涨=利好A股）
        for l in leaders:
            m = re.search(r'([+-]\d+\.?\d*)%', l)
            if m:
                pct = float(m.group(1))
                if pct < -3:  # 美股大跌>3% → 利空
                    score -= 2
                    reasons.append(f"美股龙头{l}大跌")
                elif pct < -1:
                    score -= 1
                    reasons.append(f"美股龙头{l}下跌")
                elif pct > 3:  # 美股大涨>3% → 利好
                    score += 2
                    reasons.append(f"美股龙头{l}大涨")
                elif pct > 1:
                    score += 1
                    reasons.append(f"美股龙头{l}上涨")

        # 新闻信号
        if len(news) >= 3:
            score += 1
            reasons.append(f"{len(news)}条相关新闻")
        elif len(news) >= 1:
            score += 0.5

        # 纳斯达克大方向
        for idx in us_data.get("indices", []):
            if idx["name"] == "纳斯达克":
                if idx["change_pct"] < -2:
                    score -= 1
                    reasons.append("纳斯达克大跌")
                elif idx["change_pct"] > 1:
                    score += 0.5

        # 方向判定
        if score >= 1.5:
            direction = "偏多"
        elif score >= 0.5:
            direction = "略多"
        elif score <= -1.5:
            direction = "偏空"
        elif score <= -0.5:
            direction = "略空"
        else:
            direction = "中性"

        results.append({
            "code": code,
            "name": info.get("name", code),
            "direction": direction,
            "score": score,
            "reason": "; ".join(reasons[:3]) if reasons else "无直接关联",
            "news_count": len(news),
            "leader_signals": leaders,
        })

    results.sort(key=lambda r: abs(r["score"]), reverse=True)
    return results


# ═══════════════════════════════════════════════════════════════
# 4. OUTPUT GENERATION
# ═══════════════════════════════════════════════════════════════

def pick_headlines(news_items: list[dict], topics: list[dict]) -> list[dict]:
    """选取4-5条今日导读。

    优先选：
    - 有受益标的的（体现决策价值）
    - 有主题聚合的（市场主线）
    - 重磅政策/龙头动态
    """
    # 构建主题→关键词映射
    topic_keywords_map = {}
    for t in topics:
        for item in t["news"]:
            topic_keywords_map[item.get("title", "")] = t["topic"]

    scored = []
    for item in news_items:
        title = item.get("title", "")
        stocks = item.get("matched_stocks", [])
        s = len(stocks) * 4  # 有标的的优先
        # 重磅/政策加分
        if any(kw in title for kw in ["SpaceX", "茅台", "华为", "国务院", "央行", "证监会"]):
            s += 8
        if any(kw in title for kw in ["政策", "白宫", "关税", "降息", "加息"]):
            s += 5
        # 有主题聚合的加分
        if title in topic_keywords_map:
            s += 3
        # 有数字/数据的加分（具体信息）
        if re.search(r'\d+', title):
            s += 1
        scored.append((s, item))

    scored.sort(key=lambda x: x[0], reverse=True)

    # 精选：同一主题只选一条，优先选有标的的
    seen_topics = set()
    picks = []
    for _, item in scored:
        title = item.get("title", "")
        stocks = item.get("matched_stocks", [])

        # 跳过噪音
        if _is_noise_news(title):
            continue

        # 至少要有标的或重磅重要性才入选
        if not stocks and _ < 10:
            continue

        topic = topic_keywords_map.get(title, title[:15])
        if topic not in seen_topics:
            picks.append(item)
            seen_topics.add(topic)
        if len(picks) >= 5:
            break

    return picks


def _clean_cls_prefix(title: str) -> str:
    """去除CLS新闻的通用前缀。"""
    return re.sub(r"财联社\d+月\d+日电，", "", title)


NOISE_GENERAL = [
    "人民日报", "新华社", "和音", "述评", "钟声",
    "科学家", "研究", "发现", "基因编辑",
    "粮食", "防汛", "抗旱", "应急",
    "出入境", "签证", "护照",
    "篮球", "足球", "体育", "奥运",
    "电影", "票房", "综艺", "娱乐",
]


def _is_noise_news(title: str) -> bool:
    """判断是否为噪音新闻，不列入行业要闻。"""
    noise_keywords = [
        "地震", "暴雨", "台风", "洪水", "灾害", "应急响应",
        "杀人", "犯罪", "违法", "非法", "拘留", "抓捕", "判刑",
        "火灾", "爆炸", "事故", "伤亡",
        "龙卷风", "海啸", "寒潮",
    ]
    political_noise = [
        "金正恩", "特朗普称", "以色列", "巴勒斯坦", "哈马斯",
        "航母", "战机相撞", "军事行动", "逮捕令",
        "古巴", "秘鲁", "乌兹别克斯坦", "格陵兰",
        "国际刑事法院", "以黎冲突", "麻疹",
        "汉坦病毒", "无人机袭击", "美特使",
        "阿联酋外长", "国际原子能", "卡塔尔首相",
    ]
    if any(kw in title for kw in noise_keywords):
        return True
    if any(kw in title for kw in political_noise):
        return True
    if any(kw in title for kw in NOISE_GENERAL):
        return True
    return False


def generate_markdown_v2(us_data: dict, annotated_news: list[dict], topics: list[dict],
                          announcements: dict, holding_impact: list, holdings: dict) -> str:
    """生成对标PDF质量的晨报。"""
    today = datetime.now(CST)
    date_str = today.strftime("%Y-%m-%d")
    month_day = today.strftime("%m月%d日")
    weekday = ["周一","周二","周三","周四","周五","周六","周日"][today.weekday()]

    lines = [
        f"# 盘前晨报 | {date_str} {weekday}",
        f"**生成时间**: {today.strftime('%H:%M')} | 数据来源: CLS+akshare",
        "",
    ]

    # ── 【今日导读】 ──
    headlines = pick_headlines(annotated_news, topics)
    lines.append("## 【今日导读】")
    for i, item in enumerate(headlines, 1):
        title = _clean_cls_prefix(item.get("title", ""))
        stocks = item.get("matched_stocks", [])
        stock_str = "、".join(s["name"] for s in stocks[:4]) if stocks else ""
        out = title[:57] + "..." if len(title) > 60 else title
        if stock_str:
            lines.append(f"{i}. {out} → **{stock_str}**")
        else:
            lines.append(f"{i}. {out}")
    lines.append("")

    # ── 一、持仓影响评估 ──
    lines.append("## 一、持仓影响")
    if holding_impact:
        lines.append("| 代码 | 名称 | 方向 | 理由 |")
        lines.append("|------|------|------|------|")
        arrow_map = {"偏多": "🟢", "略多": "🟡", "中性": "⚪", "略空": "🟠", "偏空": "🔴"}
        for h in holding_impact:
            arrow = arrow_map.get(h["direction"], "⚪")
            lines.append(f"| {h['code']} | {h['name']} | {arrow} {h['direction']} | {h['reason']} |")
    else:
        lines.append("- 无活跃持仓或数据获取失败")
    lines.append("")

    # ── 二、专题聚焦 ──
    lines.append("## 二、专题聚焦")
    if topics:
        for t in topics[:3]:
            lines.append(f"### {t['topic']}")
            for item in t["news"][:3]:
                title = _clean_cls_prefix(item.get("title", ""))
                lines.append(f"- {title[:120]}")
            if t["stocks"]:
                sstr = "、".join(f"{s['name']}({s['code']})" for s in t["stocks"][:8])
                lines.append(f"  **受益标的**: {sstr}")
            lines.append("")
    else:
        lines.append("- 今日无显著主题")
        lines.append("")

    # ── 三、行业要闻 ──
    lines.append("## 三、行业要闻")
    topic_news_titles = set()
    for t in topics:
        for item in t["news"]:
            topic_news_titles.add(item.get("title", ""))

    news_count = 0
    for item in annotated_news:
        title = item.get("title", "")
        if title in topic_news_titles:
            continue
        if _is_noise_news(title):
            continue
        clean = _clean_cls_prefix(title)
        stocks = item.get("matched_stocks", [])
        sstr = "、".join(s["name"] for s in stocks[:3]) if stocks else ""
        out = clean[:100]
        if sstr:
            lines.append(f"- {out} → **{sstr}**")
        elif news_count < 10:  # 无标的的新闻限数量
            lines.append(f"- {out}")
        news_count += 1
        if news_count >= 15:
            break
    if news_count == 0:
        lines.append("- 无更多重要新闻")
    lines.append("")

    # ── 四、公告精选 ──
    lines.append("## 四、公告精选")
    # 4a 日常公告
    if announcements["contracts"]:
        lines.append("**📋 日常公告**")
        for item in announcements["contracts"][:8]:
            title = _clean_cls_prefix(item.get("title", ""))
            line = f"- {title[:100]}"
            if item.get("stocks_summary"):
                line += f" → {item['stocks_summary']}"
            lines.append(line)
        lines.append("")

    # 4b 地雷阵
    if announcements["decreases"]:
        lines.append("**💣 地雷阵（减持预警）**")
        for item in announcements["decreases"][:10]:
            title = item.get("title", "")
            m = re.search(r'拟减持([\d.]+)%', title)
            pct = m.group(1) if m else "?"
            stock_str = item.get("stocks_summary", "")
            # 提取公司名
            name_part = _clean_cls_prefix(title).split("：")[0].strip()
            lines.append(f"- {name_part} → 拟减持 {pct}%{' | ' + stock_str if stock_str else ''}")
        if len(announcements["decreases"]) > 10:
            lines.append(f"  ...等共{len(announcements['decreases'])}条减持公告")
        lines.append("")

    # 4c 解禁
    if announcements["lockup"]:
        lines.append("**🔓 解禁提醒**")
        for item in announcements["lockup"][:3]:
            title = _clean_cls_prefix(item.get("title", ""))
            lines.append(f"- {title[:100]}")
        lines.append("")

    # 4d 异动澄清
    if announcements["unusual"]:
        lines.append("**⚠️ 异动澄清**")
        for item in announcements["unusual"][:5]:
            title = _clean_cls_prefix(item.get("title", ""))
            lines.append(f"- {title[:100]}")
        lines.append("")

    # 4e 停复牌
    if announcements["restart"]:
        lines.append("**⏸ 停复牌**")
        for item in announcements["restart"][:3]:
            title = _clean_cls_prefix(item.get("title", ""))
            lines.append(f"- {title[:100]}")
        lines.append("")

    if not any(announcements.values()):
        lines.append("- 无重要公告")
        lines.append("")

    # ── 五、全球市场 ──
    lines.append("## 五、全球市场")
    if us_data["indices"]:
        for idx in us_data["indices"]:
            chg = idx["change_pct"]
            arrow = "🔴" if chg < 0 else "🟢" if chg > 0 else "⚪"
            lines.append(f"- {arrow} **{idx['name']}**: {idx['price']:,.0f} ({chg:+.2f}%)")
    else:
        lines.append("- 美股数据获取失败")
    lines.append("")

    if us_data.get("sector_leaders"):
        big_movers = [l for l in us_data["sector_leaders"] if abs(l["change_pct"]) > 0.5]
        if big_movers:
            lines.append("**龙头股表现**:")
            for l in big_movers[:8]:
                chg = l["change_pct"]
                arrow = "🔴" if chg < 0 else "🟢"
                lines.append(f"- {arrow} {l['name']} ({l['concept']}): {chg:+.1f}%")
            lines.append("")

    # ── 六、今日关注 ──
    lines.append("## 六、今日关注")
    lines.append("- **集合竞价**: 9:15-9:25 关注持仓股竞价量能")
    # 从新闻中提取今日重要日程
    calendar_items = [item for item in annotated_news
                      if any(kw in item.get("title", "") for kw in ["今日", "国新办", "发布会", "15:00", "14:00"])]
    for item in calendar_items[:3]:
        title = _clean_cls_prefix(item.get("title", ""))
        lines.append(f"- {title[:80]}")
    lines.append("")
    lines.append("---")
    lines.append(f"*自动生成于 {datetime.now(CST).strftime('%Y-%m-%d %H:%M')} | morning_brief v2.0*")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 5. MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    start = time.time()
    logger.info("Morning Brief v2.0 starting...")

    # 加载数据
    news = load_latest_news()
    if not news:
        logger.warning("无新闻数据，跳过产出")
        print("无新闻数据，不生成晨报")
        return

    us_data = fetch_us_market()
    lookup = load_stock_lookup()
    concept_map = load_concept_map()
    holdings = load_holdings()

    # 新闻标注
    annotated = annotate_news_with_stocks(news, lookup)

    # 主题检测
    topics = detect_topics(annotated)

    # 公告提取
    announcements = extract_announcements_v2(annotated)

    # 持仓影响
    holding_impact = assess_holding_impact_v2(annotated, us_data, holdings)

    # 生成
    md = generate_markdown_v2(us_data, annotated, topics, announcements, holding_impact, holdings)

    # 保存
    OUTPUT_MD.write_text(md, encoding="utf-8")
    OUTPUT_JSON.write_text(json.dumps({
        "date": datetime.now(CST).strftime("%Y-%m-%d"),
        "time": datetime.now(CST).strftime("%H:%M:%S"),
        "news_total": len(annotated),
        "news_annotated": sum(1 for n in annotated if n["matched_stocks"]),
        "topics_found": len(topics),
        "holding_impact": [{"code": h["code"], "direction": h["direction"], "score": h["score"]}
                          for h in holding_impact],
        "announcement_counts": {k: len(v) for k, v in announcements.items()},
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    elapsed = time.time() - start
    annotated_count = sum(1 for n in annotated if n["matched_stocks"])
    logger.info(f"Done in {elapsed:.1f}s | {len(annotated)} news ({annotated_count} annotated) | "
                f"{len(topics)} topics | {len(holding_impact)} holdings")

    # 质量检查：如果没有标注任何股票，产出质量不够，警告
    if annotated_count < 3:
        logger.warning(f"仅{annotated_count}条新闻有标的标注，质量偏低")

    print(md)


if __name__ == "__main__":
    main()
