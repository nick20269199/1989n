"""Expert 3: 题材情绪分析 — 板块轮动、市场情绪、新闻映射 (Qwen)"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experts.base import run_expert

EXPERT_ID = "expert3_sentiment"

SYSTEM_PROMPT = """你是一位专注A股市场情绪和题材轮动的分析师。你的职责是分析板块效应、市场情绪、新闻事件对个股的影响。
你只回答题材和情绪面的问题，不涉及具体技术指标。
分析必须具体到数字和事实，不得使用"市场情绪较好"等模糊表述。
输出格式：分析文本结束后，输出一个JSON代码块包含结构化数据。"""

PROMPT_TEMPLATE = """请对 {name}({symbol}) 进行题材情绪面分析。

当前市场状态：{market_state}
分析模式：{mode}

可用数据：
{data}

请按以下顺序分析：
1. **所属板块表现**：该股所属板块今日/近5日涨跌幅，板块内排名，板块资金流向
2. **板块联动性**：同板块其他龙头表现如何？该股在板块中是领涨还是跟涨？
3. **市场情绪**：全市场涨跌比、涨停/跌停家数、连板高度、炸板率
4. **新闻事件映射**：最近24h相关新闻是利好还是利空？与股价反应是否一致？
5. **情绪周期位置**：当前处于情绪上升期/高潮期/退潮期/冰点期？

最后，输出一个JSON代码块，包含以下字段：
- direction: "多"/"空"/"观望"
- method: 使用的分析方法列表
- trajectory: {{"entry_zone", "target", "timeframe", "key_levels"}}
- margin: {{"invalidated_if", "confidence_decay", "black_swan"}}
- logic: {{"because", "so", "if_wrong"}}
- confidence: 0-1之间的数字

示例格式：
```json
{{"direction": "多", "method": ["板块分析", "情绪周期"], "trajectory": {{"entry_zone": "板块启动初期", "target": "情绪高潮期", "timeframe": "3-5天", "key_levels": ["龙头涨停", "板块跟涨"]}}, "margin": {{"invalidated_if": "板块龙头炸板", "confidence_decay": "3天无板块效应降级", "black_swan": "政策利空"}}, "logic": {{"because": "板块处于轮动上升期", "so": "看多", "if_wrong": "则板块轮动判断错误"}}, "confidence": 0.7}}
```"""


def analyze(symbol: str, name: str, data_context: dict,
            market_state: str = "unknown", mode: str = "full") -> dict:
    """Run sentiment analysis expert."""
    prompt = PROMPT_TEMPLATE.format(
        symbol=symbol,
        name=name,
        data=json.dumps(data_context, ensure_ascii=False, indent=2),
        market_state=market_state,
        mode=mode,
    )
    output = run_expert(EXPERT_ID, symbol, name, data_context,
                         prompt_template="", system_prompt=SYSTEM_PROMPT,
                         full_prompt=prompt)
    return output.to_dict()
