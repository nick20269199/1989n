"""Expert 3: 题材情绪分析 — 板块轮动、市场情绪、新闻映射 (Qwen)"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experts.base import run_expert

EXPERT_ID = "expert3_sentiment"


# ============================================================
# FILL ZONE 1: Expert role definition
# Edit the text below to change what this expert focuses on.
# Current: sector rotation, market sentiment, news mapping
# ============================================================
SYSTEM_PROMPT = """你是一位专注A股市场情绪和题材轮动的分析师。你的职责是：给定一个持仓核心逻辑（thesis），从板块效应、市场情绪、新闻事件中判断这个 thesis 是否被市场定价。
你不是填空机器，你是推理者。你判断市场情绪是否在反映 thesis，还是无视它。
分析必须具体到数字和事实，不得使用"市场情绪较好"等模糊表述。
输出格式：分析文本结束后，输出一个JSON代码块包含结构化数据。"""
# ============================================================
# END OF FILL ZONE 1
# ============================================================


# ============================================================
# FILL ZONE 2: Analysis approach
# ============================================================
PROMPT_TEMPLATE = """对 {name}({symbol}) 进行题材情绪面分析。

核心逻辑（thesis）：{thesis}
当前市场状态：{market_state}
分析模式：{mode}

可用数据：
{data}

你的任务是推理：**从市场情绪和板块行为看，这个 thesis 是否已经被定价？**
- 该股的所属板块是否在反映这个 thesis？（如 SpaceX IPO → 航天板块有异动吗？）
- 市场整体情绪支持这个 thesis 兑现吗？（乐观/悲观/无视？）
- 新闻事件与 thesis 方向一致还是冲突？
- 这 thesis 是已被充分定价，还是市场还没反应过来？

不要罗列指标，要判断。给出你的 reasoning，然后输出结构化JSON。
# ============================================================
# END OF FILL ZONE 2
# ============================================================

**已有认知参考（非本次分析数据，仅供推理上下文参考）：**
{knowledge_text}

最后，输出一个JSON代码块，包含以下字段。

**知识库注入 — 板块周期与情绪判断：**
涨停→洗盘→企稳→爬坡五阶段判断板块处于哪个周期位。
反弹创新高但量缩=诱多背离；心跳K线=洗盘结束信号。
利好兑现规则：重大利好披露后等第一个交易日结束再判断，高开低走=主力借利好出货。
六问自检(情绪面用)：是否cherry-picking利好新闻？置信度有没有被锚定效应影响？

**知识库注入 — 边际条件（失效判断）：**
跌破关键价位+板块龙头炸板=双重失效信号；
3天无板块效应→置信度降至0.3；
指数跌1.5%+板块跟跌→降低仓位；
涨停但板块内跟风不足→孤掌难鸣，警惕。
连续亏损3笔以上→暂停交易。

**知识库注入 — 逻辑闭环要求（逆否命题结构）：**
if_wrong必须使用**逆否命题(contrapositive)**：because=X→so=Y → if_wrong="如果非Y→则X假"。格式:"如果[预期市场反应未发生]→则[原始情绪/板块推论]证伪，说明thesis未被定价"。
好例: "如果板块3日内没有跟涨→题材轮动判断错误，说明thesis未被市场认可"(逆否:because=板块资金流入→so=题材轮动中→if_wrong=板块不跟涨→轮动判断错)
差例: "如果下跌→市场情绪不好"(转向新假设,非逆否)
差例: "如果指数跌1.5%→减仓"(这是margin的失效条件,不是logic的if_wrong)
method数据来源必须可溯：注明来自同花顺/财联社/东方财富Level-2。

**重要规则（决定你的评分）：**
- entry_zone 必须写**具体价格区间**，禁止模糊词。情绪描述放notes里，entry_zone/target必须用数字
- method 必须写明**具体数据来源**如"板块涨跌幅(同花顺行业)""涨停家数(全市场)"
- invalidated_if 必须写**价格条件+情绪条件+天数**三段式，如"跌破44.0+板块龙头炸板+2天不回"
- confidence_decay 必须写**至少2组条件→新置信度**映射，如"3天板块无效应→0.3, 指数跌1.5%+板块跟跌→0.5"
- black_swan 必须写**可观测的具体事件**（不是"政策突变""外部冲击"等模糊词），如"板块利空导致龙头跌停清仓"或"行业政策转向清仓"
- if_wrong 必须使用**逆否命题结构(contrapositive)**：because=X→so=Y → if_wrong="如果非Y→则X假"。格式:"如果[预期板块/情绪反应未发生]→则[原始推论]证伪"
- 好例: "如果板块3日内没有跟涨→轮动判断错误,说明thesis未被市场认可"(逆否:because=板块资金流入+连板升→so=题材轮动中→if_wrong=板块不跟涨→轮动判断错)
- 差例: "如果下跌→情绪转弱"(转向新假设,非逆否)

**自校验（输出前检查）：**
1. JSON是否可解析？所有字段是否存在？
2. if_wrong是不是逆否命题结构(非Y→X假)？不是的话改正。**if_wrong是否直接针对thesis前提？** 如果thesis是"XX受益于YY"，if_wrong必须是"若YY带来的板块效应不发生→则XX不会受益"，不能跳到情绪新假设
3. invalidated_if有没有价格条件+情绪条件+天数三段？缺了补。**每个条件的观测标准是否数字锚定？**（如"板块涨幅<1%"而不是"板块跟涨不足"）
4. confidence_decay有没有至少2组条件映射？**每组映射的数值阈值是否显式写出？**（变量名必须附带数字）
5. black_swan是不是可观测的具体事件？不是的话重写
6. method有没有注明数据来源？没注明补。

```json
{{"direction": "多", "method": ["板块表现(近5日涨跌幅)", "资金流向(板块净额)", "情绪周期(涨停/连板高度)", "新闻映射(24h利好/利空)","龙头联动(板块内排名)"], "trajectory": {{"entry_zone": "44.5-45.5", "target": "48.0", "timeframe": "1周", "key_levels": ["板块龙头涨停", "板块跟涨2%以上"], "notes": "情绪处于上升初期,连板高度3板"}}, "margin": {{"invalidated_if": "跌破44.0+板块龙头炸板+2天不回", "confidence_decay": "3天无板块效应→0.3,指数跌1.5%+板块跟跌→0.5", "black_swan": "监管利空导致龙头跌停清仓"}}, "logic": {{"because": "板块近3日资金净流入+连板高度提升", "so": "看多", "if_wrong": "如果板块3日内没有跟涨,则轮动判断错误,thesis未被市场认可"}}, "confidence": 0.7}}
```
"""


def analyze(symbol: str, name: str, data_context: dict,
            market_state: str = "unknown", mode: str = "full") -> dict:
    """Run sentiment analysis expert."""
    prompt = PROMPT_TEMPLATE.format(
        symbol=symbol,
        name=name,
        thesis=data_context.get("holding_thesis", ""),
        data=json.dumps(data_context, ensure_ascii=False, indent=2),
        market_state=market_state,
        mode=mode,
        knowledge_text=data_context.get("knowledge_text", "无历史认知数据"),
    )
    output = run_expert(EXPERT_ID, symbol, name, data_context,
                         prompt_template="", system_prompt=SYSTEM_PROMPT,
                         full_prompt=prompt)
    return output.to_dict()
