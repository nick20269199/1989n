"""Expert 2: 资金面分析 — 主力资金流向、大单分布 (DeepSeek)"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experts.base import run_expert

EXPERT_ID = "expert2_money"


# ============================================================
# FILL ZONE 1: Expert role definition
# Edit the text below to change what this expert focuses on.
# Current: capital flow, large orders,筹码 concentration
# ============================================================
SYSTEM_PROMPT = """你是一位专注A股资金面的分析师。你的职责是：给定一个持仓核心逻辑（thesis），从资金流和筹码变化中判断聪明钱是否在按这个逻辑布局。
你不是填空机器，你是推理者。你判断资金行为与 thesis 一致还是背离。
分析必须具体到数字，不得使用"资金有所流入"等模糊表述。
输出格式：分析文本结束后，输出一个JSON代码块包含结构化数据。"""
# ============================================================
# END OF FILL ZONE 1
# ============================================================


# ============================================================
# FILL ZONE 2: Analysis approach
# ============================================================
PROMPT_TEMPLATE = """对 {name}({symbol}) 进行资金面分析。

核心逻辑（thesis）：{thesis}
当前市场状态：{market_state}
分析模式：{mode}

可用数据：
{data}

你的任务是推理：**从资金行为看，这个 thesis 有没有聪明钱在布局？**
- 主力资金流动方向与 thesis 预期的方向一致吗？
- 是否有异常的大单/超大单活动？是埋伏还是出货？
- 筹码在集中还是分散？谁在买谁在卖？
- 资金行为是提前反应 thesis，还是无视 thesis 在跑？

不要罗列指标，要判断。给出你的 reasoning，然后输出结构化JSON。
# ============================================================
# END OF FILL ZONE 2
# ============================================================

**已有认知参考（非本次分析数据，仅供推理上下文参考）：**
{knowledge_text}

最后，输出一个JSON代码块，包含以下字段。

**知识库注入 — R7超大单领先指标（置信度80%）：**
超大单方向是领先指标，非参考信号。四条子规则：
①涨停质量：涨停日超大单>+10%=真实拉升；<0%=假拉真出
②趋势出货：连续3日超大单<-5%=趋势性出货，应减仓
③价量背离：涨≥1%但超大单<-3%=诱多嫌疑，不追
④确认信号：涨停次日超大单>-3%=持有；<-10%=离场

**知识库注入 — 资金面边际条件：**
主力由流入转流出超2日=趋势可能反转；
连续3日净流出→置信度降至0.3；
缩量横盘5日→置信度降至0.5；
放量暴跌+超大单大幅流出=趋势确认结束。

**知识库注入 — 交易纪律（逻辑闭环）：**
六问自检：这个结论的反面证据是什么？是否cherry-picking资金数据？
数据来源可溯：超大单、主力资金、L2数据必须标注来源。
结论必须带置信度+反面可能性+触发修正条件，无标注=不可采信。

**重要规则（决定你的评分）：**
- entry_zone 必须是**数字区间**如"44.5-45.5"，禁止模糊词。没有价格数字时根据量价关系推算并注明推算依据
- invalidated_if 必须写**资金面条件+天数+价格确认**三段式，如"主力由流入转流出超2日+跌破支撑"
- confidence_decay 必须写**至少2组条件→新置信度**映射，如"连续3日流出→0.3, 缩量横盘5日→0.5"
- black_swan 必须写**可观测的具体事件**（不是"大盘不好""政策突变"等模糊词），如"大盘放量跌2%以上减仓避险"或"个股突发利空跌停清仓"
- method 必须写明**具体指标+参数**如"超大单净额(逐单L2)""主力资金(5日累计)"
- if_wrong 必须使用**逆否命题结构(contrapositive)**：because=X→so=Y 的逆否命题是"若非Y→则X假"。if_wrong必须写"如果[预期价格行为未发生]→则[原始资金面推论]不成立"，不得转向新假设。
- 好例: because="超大单连续3日净流入+中单无跟风"→so="看多"→if_wrong="如果3日内股价不涨反跌,则超大单净流入是对倒出货而非真实布局,资金面看多逻辑证伪"
- 差例: "如果大盘暴跌→减仓"(这是margin的black_swan,不是logic的if_wrong)
- 差例: "如果情绪转弱→观望"(转向新假设,非逆否)

**自校验（输出前检查）：**
1. JSON是否可解析？所有字段是否存在？
2. if_wrong是不是逆否命题结构(非Y→X假)？不是的话改正。**if_wrong是否直接针对thesis前提？** 如果thesis是"XX受益于YY"，if_wrong必须是"若YY不成立→则XX不会受益"，不能跳到资金面新假设
3. invalidated_if有没有资金面条件+天数+价格确认三段？缺了补。**是否有明确的资金流数字阈值？**（如"单日主力净流出>成交额8%"而不是"主力净流出较大"）
4. confidence_decay有没有至少2组条件映射？**每组映射的数值阈值是否显式写出？**（变量名必须附带数字）
5. black_swan是不是可观测的具体事件？不是的话重写
6. method有没有注明数据来源？没注明补

```json
{{"direction": "多", "method": ["主力资金(5日累计净额)", "超大单(L2逐单)", "大中小单分布(四象限)", "成交量结构(主动买/卖比)"], "trajectory": {{"entry_zone": "44.5-45.5", "target": "48.0", "timeframe": "1周", "key_levels": ["43.0支撑", "46.0阻力"]}}, "margin": {{"invalidated_if": "主力由流入转流出超2日+跌破支撑位", "confidence_decay": "连续3日流出→0.3,缩量横盘5日→0.5,放量跌3%+超大单流出→0.1", "black_swan": "大盘放量跌2%以上减仓避险"}}, "logic": {{"because": "超大单连续3日净流入+中单无跟风", "so": "看多", "if_wrong": "如果3日内股价不涨反跌,则超大单净流入为对倒出货而非真实布局,资金面看多逻辑证伪"}}, "confidence": 0.7}}
```"""


def analyze(symbol: str, name: str, data_context: dict,
            market_state: str = "unknown", mode: str = "full") -> dict:
    """Run money flow analysis expert."""
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
