"""Expert 1: 技术面分析 — 量价关系、均线系统、R7信号 (DeepSeek)"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from experts.base import run_expert

EXPERT_ID = "expert1_tech"


# ============================================================
# FILL ZONE 1: Expert role definition
# Edit the text below to change what this expert focuses on.
# Current: volume-price, moving averages, patterns, R7 signal
# ============================================================
SYSTEM_PROMPT = """你是一位专注A股技术面的分析师。你的职责是：给定一个持仓核心逻辑（thesis），从量价关系中判断该逻辑是否正在被市场验证。
你不是填空机器，你是推理者。你必须基于数据对这 thesis 做出判断——支持它、反驳它、还是无法判断。
分析必须具体到数字，不得使用"走势尚可""表现不错"等模糊表述。
输出格式：分析文本结束后，输出一个JSON代码块包含结构化数据。"""
# ============================================================
# END OF FILL ZONE 1
# ============================================================


# ============================================================
# FILL ZONE 2: Analysis approach
# ============================================================
PROMPT_TEMPLATE = """对 {name}({symbol}) 进行技术面分析。

核心逻辑（thesis）：{thesis}
当前市场状态：{market_state}
分析模式：{mode}

可用数据：
{data}

你的任务是推理：**从量价数据看，这个 thesis 是否站得住？**
- 如果 thesis 是"星舰供应商，6/18 IPO"——价格是在提前反映这个预期，还是完全没反应？
- 如果 thesis 是"华为鸿蒙生态"——量价是否显示有资金在布局？
- 不管 thesis 是什么——数据支持它还是否定它？

不要罗列指标，要判断。给出你的 reasoning，然后输出结构化JSON。
# ============================================================
# END OF FILL ZONE 2
# ============================================================

**已有认知参考（非本次分析数据，仅供推理上下文参考）：**
{knowledge_text}

最后，输出一个JSON代码块，包含以下字段。

**知识库注入 — 量价周期模式（实证）：**
涨停→洗盘→企稳→爬坡五阶段：洗盘期量缩至峰值50%以下+下影线探底=企稳信号；
反弹创新高但量缩=诱多背离，不是真反转；
心跳K线：振幅收窄+下影线长+量缩至峰值的40-50%=洗盘结束。

**知识库注入 — 三倍量策略（入场）：**
放量3倍→缩量回MA5/MA10→突破均线=上车点；
止损:跌破均线-3%或入场价-5%；止盈:前高或+8~15%。

**知识库注入 — 交易纪律（边际/逻辑）：**
R7四条：涨停日超大单>+10%=真实拉升，<0%=假拉真出；连续3日超大单<-5%=趋势性出货；
涨≥1%但超大单<-3%=诱多嫌疑；
利好兑现：重大利好披露后等第一个交易日结束再判断，高开低走=主力出货。
六问自检(逻辑闭环)：结论的反面证据是什么？是否在cherry-picking？止损位合理吗？

**重要规则（决定你的评分）：**
- entry_zone 必须是**数字区间**如"44.5-45.5"，不能写"待确认""等待信号"等模糊词。数据不足以精确推算时，给出估算并注明"基于XX推算"
- invalidated_if 必须写**价格+天数+附加条件**三段式组合，如"跌破43.0且2天收不回+板块跟跌/缩量"
- confidence_decay 必须写**至少2组条件→新置信度**映射，如"持有5天不涨→0.4, 跌破44→0.2"
- black_swan 必须写**可观测的具体事件**（不是"政策突变""大盘不好"等模糊词），如"大盘单日跌3%以上减半仓"或"板块利空导致龙头跌停清仓"
- method 必须写明**具体参数**如"MA5/MA20(收盘价,前复权)""量价比(5日均量/20日均量)"
- method 数量不少于3个分析方法
- if_wrong 必须使用**逆否命题结构(contrapositive)**：because=X→so=Y 的逆否命题是"若非Y→则X假"。if_wrong必须写"如果[预期结果未发生]→则[原始because中的推论失效]"，不得转向新假设。
- 好例: because="MA5上穿MA20+量比1.5"→so="看多"→if_wrong="如果5日内价格未到45.0,则MA5金叉+放量的看多信号失效,说明thesis中的上涨预期未被市场验证"
- 差例: "如果下跌→情绪转弱"(转向新假设,非逆否)
- 差例: "如果市场不好→止损"(这是margin不是logic)

**自校验（输出前检查）：**
1. JSON是否可解析？所有字段是否存在？
2. if_wrong是不是逆否命题结构(非Y→X假)？不是的话改正
3. invalidated_if有没有价格+天数+条件三段？缺了补
4. confidence_decay有没有至少2组条件映射？**每组条件的数值阈值是否显式写出数字？**（"10日均量"这种变量名必须附带数字，如"10日均量=7亿手"）
5. black_swan是不是可观测的具体事件？不是的话重写
6. method数量是否>=3？不够补
7. 边际中的每个条件是否都有明确的数字/可观测锚点？含糊的补数字

```json
{{"direction": "多", "method": ["趋势判断(MA5/MA20收盘价前复权)", "量价分析(5日均量/20日均量比)", "支撑阻力(前高前低)","RSI(14)"], "trajectory": {{"entry_zone": "44.5-45.5", "target": "48.0", "timeframe": "1周", "key_levels": ["43.0支撑", "46.0阻力", "48.0目标"]}}, "margin": {{"invalidated_if": "跌破43.0且2天收不回+板块跟跌", "confidence_decay": "持有5天不涨→0.4,跌破44→0.2,放量跌3%→0.1", "black_swan": "大盘单日跌3%以上减半仓"}}, "logic": {{"because": "MA5上穿MA20+量比1.5", "so": "看多", "if_wrong": "如果5日内价格未到45.0,则MA5金叉+放量看多信号失效,上涨预期未被市场验证"}}, "confidence": 0.7}}
```"""


def analyze(symbol: str, name: str, data_context: dict,
            market_state: str = "unknown", mode: str = "full") -> dict:
    """Run technical analysis expert."""
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
