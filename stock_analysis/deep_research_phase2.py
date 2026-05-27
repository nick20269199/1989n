"""
deep_research_phase2.py — Phase2 深度研究脚本

对6个处于 solution_found 状态的缺口做第二轮深挖，
走 DeepSeek Channel 2 (research) 独立配额。

每个缺口：详细研究prompt → Ch2 深度分析 → 收集发现 → 更新状态
"""
import json
import logging
import sys
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from deepseek_multi import research as ch2_research, parallel_analyze as ch3_analyze
from knowledge_gap_registry import load_registry, update_gap, save_registry

logger = logging.getLogger("deep_research_phase2")

OUTPUT_FILE = Path("D:/1989n/stock_data/status/deep_research_report_phase2.json")

# ── 本次研究的6个缺口及其详细研究prompt ──

GAP_RESEARCH_PROMPTS = {
    "pipeline-shared-cache": {
        "prompt": """你是一位多Agent系统架构专家。请深入研究"多Agent管线中的共享缓存层设计"。

问题背景：我的量化交易系统有5个Expert（技术面/资金面/情绪面/宏观面/风控），它们独立采集数据后拼成大prompt给Grader。问题是expert1拉到的量价数据expert2要重新拉，造成重复IO和Token浪费。

搜索方向：
1. "shared cache multi-agent data pipeline" — 多Agent间共享数据缓存的最佳实践
2. "agent result cache pattern" — Agent结果缓存的架构模式
3. "data deduplication agent system" — Agent系统中的数据去重机制

请从以下维度深入分析：

A. 架构模式：
- 分布式缓存 vs 集中式缓存的取舍（Redis/内存/sqlite）
- 缓存键设计策略（基于什么特征做去重？符号+时间窗口？）
- 缓存失效策略（TTL多久？价格数据实时性要求 vs 基本面数据长有效期）
- 读通/写通/写回 三种缓存策略在交易管线中的适用性

B. 实际案例：
- LangChain/LlamaIndex 等多Agent框架如何做数据共享？
- 已知开源项目（AutoGPT/CrewAI等）的缓存设计
- 高频交易系统的共享内存设计可借鉴什么？

C. 落地设计（A股交易场景）：
- 5位Expert各自需要什么数据？（画数据依赖矩阵）
- 哪些数据是共享的（行情/基本面）vs 独占的（各自的技术指标计算）
- 建议的缓存层架构：缓存层放在哪里？（data_source_router之后？Expert之前？）
- 内存占用估算：5206只A股 x 每只多少字段 x 缓存几个时间切片？
- TTL设计：实时行情1分钟/日线数据当日/基本面数据到下次财报

D. 可验证预测：
- 引入共享缓存后，预计减少多少API调用次数？（给出计算方法）
- 预计减少多少Token消耗？（给出估算）

输出要求：结论简洁、有具体数值、区分"确定性结论"和"待验证假设"。"""
    },
    "pipeline-data-whitelist": {
        "prompt": """你是一位数据安全架构师。请深入研究"数据采集管线的多层白名单防御架构"。

问题背景：我的A股量化系统的data_source_router.py从多个数据源（新浪/腾讯/搜狐/东方财富/TDX）采集行情数据，但没有输入校验层。需要设计一个多层防御体系。

搜索方向：
1. "data validation whitelist pipeline" — 数据白名单校验管道
2. "defense in depth data ingestion" — 数据摄入的纵深防御
3. "input sanitization pipeline architecture" — 输入净化管道架构

请从以下维度深入分析：

A. 防御分层设计（五层模型）：
- L1 采集层：数据源身份验证 + 连接白名单（只允许预定义URL/IP）
- L2 净化层：对每个字段做类型/范围/格式正则校验
- L3 白名单层：定义合法数据模式，不在白名单的直接拒绝
- L4 分析层：对入库数据做统计一致性检查（如：价格不能为负、涨跌幅不超过±20%/±30%科创创业）
- L5 风控层：断路器机制——连续N条异常数据自动切断该通道

B. 字段级白名单设计（A股数据的具体约束）：
- 价格字段：>0, <10000, 精度2位小数
- 涨跌幅：主板±10%, 科创/创业±20%, ST±5%
- 成交量：正整数, 0到10^12
- 时间戳：交易时段内, 单调递增
- 代码格式：6位数字, 符合交易所编码规则（主板00/60, 创业板30, 科创板68, 北交所83/87/92）

C. 异常处理策略：
- 单字段异常 vs 整条记录异常 — 差异对待？
- 降级策略：某通道连续异常N次→自动切换到后备通道
- 告警策略：异常率超过X%触发人工审查
- 数据回补：异常期过了怎么补数据？

D. 落地设计：
- 白名单配置放在哪？（JSON/YAML配置文件）
- 校验耗时：5206只股票×每个N字段，全量校验需要多久？
- 是否做采样校验（每只股票随机抽M个字段）vs 全量校验？
- 性能优化：正则预编译、批量校验、字段类型快速路径

输出要求：给出可落地的白名单配置结构（JSON Schema）、校验函数签名、性能估算。"""
    },
    "knowledge-creator-discovery": {
        "prompt": """你是一位AI知识管理系统架构师。请深入研究"主动知识发现Agent"的设计。

问题背景：我的抖音监控系统(douyin_monitor.py)只扫描已知博主列表。知识缺口清单里有14个待研究问题，但没有机制根据缺口自动去搜索匹配的创作者/内容。需要从"被动等链接"升级为"主动勘探"。

搜索方向：
1. "knowledge discovery agent system" — 知识发现Agent系统
2. "expert finder AI" — AI专家发现机制
3. "content discovery pipeline" — 内容发现管线

请从以下维度深入分析：

A. 知识发现的闭环设计：
- 缺口清单 → 搜索查询生成 → 多源搜索 → 结果排序 → 质量过滤 → 吸收 — 这个完整链路如何设计？
- 搜索源优先级：抖音（时效性）/知乎（深度）/GitHub（代码）/论文（严谨性）如何排序？
- 搜索结果相关性评分：如何判断一个内容是否真的回答了缺口问题？

B. 批量搜索策略：
- 如何从缺口描述自动生成有效搜索关键词？（当前是人工写的search_queries）
- 多轮搜索：第一轮宽泛→第二轮精准→第三轮深度
- 去重：不同源搜到同一个创作者/内容

C. 质量评估：
- 如何评估一个创作者的"权威度"？（粉丝数/内容质量/引用情况/历史准确率）
- 如何评估单条内容对缺口的"填补度"？（部分解决/完全解决/无关）
- 误报控制：搜索结果中噪音比例通常很高，如何设计过滤层？

D. 自动化闭环：
- 发现优质内容后 → 自动触发吸收链路（转录→分析→提案）
- 提案质量反馈 → 反向更新搜索策略（哪些源/关键词效果好）
- 未覆盖缺口 → 定期重新搜索 vs 人工介入

E. 落地设计（我们的系统）：
- 搜索API选型：B站/知乎/GitHub/微信搜一搜的API可用性
- 抖音搜索的可行性（有cookie情况下能否搜索关键词？）
- 每日配额管理：每天搜索多少个缺口？每个缺口搜索多少条？
- 存储结构：发现的内容存哪里？关联到缺口ID？

输出要求：给出可落地的Pipeline流程图和数据模型设计。区分已有开源方案和需要自研的部分。"""
    },
    "arch-multi-layer-security": {
        "prompt": """你是一位AI安全架构师。请深入研究"Agent多层安全护栏架构"的设计和实现。

问题背景：我们目前的交易系统只有-7%硬止损单点防御。需要扩展为多层安全架构（参考九天Hector的五层模型：字符串拦截→正则过滤→白名单放行→独立AI审查→人工兜底）。

搜索方向：
1. "multi-layer AI safety architecture" — AI多层安全架构
2. "agent guardrails layered defense" — Agent护栏分层防御
3. "circuit breaker pattern AI system" — AI系统中的断路器模式

请从以下维度深入分析：

A. 分层防御模型设计：

L1-输入过滤层：
- 字符串/正则过滤：拦截危险指令模式
- 输入长度限制、注入检测
- 哪些指令模式应该被拦截？（如"忽略之前所有指令"、"以root身份执行"）

L2-白名单层：
- 允许的股票代码范围（A股6位数字正则）
- 允许的操作类型（查询/分析/建议，禁止直接下单）
- 允许的数值范围（仓位0-100%, 止损0-20%）

L3-行为审查层（独立AI）：
- 独立于前厅部决策Agent的安全审查Agent
- 审核决策是否符合交易纪律（风控/仓位/止损）
- 审核决策逻辑是否存在已知认知偏差（确认偏差/锚定效应/近因效应）

L4-断路器层：
- 什么条件触发断连？（连续N次高风险建议/单日建议频率超阈值/账户回撤超警戒）
- 断连后降级到什么模式？（只读模式/仅查看模式/完全锁定）
- 自动恢复条件？（时间窗口/人工确认/市场恢复）

L5-人工兜底层：
- 什么条件必须人工确认？
- 告警升级路径（警告→阻断→紧急冻结）

B. 开源方案调研：
- Guardrails-AI (guardrails-ai/guardrails) 的RAIL规范
- NVIDIA NeMo Guardrails 的对话安全设计
- Anthropic 的 Constitutional AI 在代码层的落地
- Meta 的 Llama Guard 分类器

C. A股交易特有安全约束：
- 禁止T+0当日回转建议
- 禁止融资融券裸卖空建议
- 禁止内幕信息利用
- ST/*ST股票交易限制
- 涨跌停板规则验证

D. 落地设计：
- 每个安全层分别放在管线的哪个位置？
- 性能开销评估：5层审查的总延迟（毫秒级）
- 安全层自身的错误处理：安全层挂了怎么办？fail-open还是fail-close？

输出要求：给出分层架构图、每层职责表、以及可与Guardrails-AI结合的最小可行实现方案。"""
    },
    "trading-rules-not-operationalized": {
        "prompt": """你是一位量化交易系统架构师。请深入研究"交易规则的形式化与执行引擎"设计。

问题背景：我们的 trading_rules.json 存储了交易规则（如可川科技的交易纪律），但这些规则未被任何 expert 或 grader 加载使用。规则→代码的链路断裂——规则存在但不对分析产生任何实质影响。

搜索方向：
1. "trading rules engine architecture" — 交易规则引擎架构
2. "rule-based trading agent" — 基于规则的交易Agent
3. "operationalize trading rules" — 交易规则操作化

请从以下维度深入分析：

A. 规则形式化：
- 如何将自然语言规则（如"放量突破20日均线且MACD金叉时买入"）转为机器可执行的规则表达式？
- 规则表达语言选型：JSON规则树 vs Python lambda vs 自定义DSL vs Drools风格？
- 规则优先级/冲突解决：多条规则同时触发时怎么排序？

B. 规则引擎架构模式：
- 前向链（数据驱动）vs 后向链（目标驱动）推理
- RETE算法及其现代变体在交易规则中的适用性
- 规则的生命周期管理：创建→测试→部署→监控→废弃

C. 实际案例：
- 成熟开源规则引擎：Drools(Java)/Easy Rules/CLIPS/Nools
- Python生态：business-rules/durable_rules/pyke/rule-engine
- 量化交易专用：QuantConnect的LEAN引擎规则系统、Zipline的Pipeline API

D. 与现有Expert管线的集成：
- 规则引擎应该放在哪里？（作为第6个Expert？作为Grader的前置过滤器？）
- 规则执行结果如何影响最终评分？（加分/减分/一票否决）
- 规则如何引用Expert的输出？（如 expert4 判断市场体制 → 规则根据体制选择不同阈值）
- 回溯测试：用历史数据验证规则有效性 → 规则自动优化

E. 落地设计：
- 最小可行：选一个Python规则引擎（推荐哪个？为什么？）
- 规则格式设计：一条规则包含什么字段？
- 与 trading_rules.json 的兼容：现有格式是否需要改造？
- 渐进集成路径：先让 expert5_risk 加载 → 再让 grader 加载 → 最后让 lead 编排

输出要求：给出规则引擎选型对比表、规则JSON Schema设计、以及与expert5_risk集成的代码结构。"""
    },
    "concept-position-sizing": {
        "prompt": """你是一位量化投资组合管理专家。请深入研究"A股市场的系统化仓位管理模型"。

问题背景：我们当前的仓位管理凭感觉或固定股数，没有形式化的数学模型。需要基于凯利公式/风险平价/波动率调整的系统化仓位计算方案。

搜索方向：
1. "Kelly criterion position sizing A shares" — 凯利公式在A股的仓位应用
2. "risk parity position management" — 风险平价仓位管理
3. "volatility adjusted position sizing" — 波动率调整仓位

请从以下维度深入分析：

A. 凯利公式及其改进：

标准凯利公式：
- f* = (bp - q) / b  其中 b=赔率, p=胜率, q=1-p
- 在A股的实际应用：如何估计p（胜率）？如何定义b（盈亏比）？
- 重要修正：Fractional Kelly（半凯利/1/4凯利）——为什么全凯利太激进？
- 连续下注凯利 vs 同时持有多只股票的凯利扩展

连续凯利（多资产）：
- 考虑资产间相关性的凯利公式
- 约束条件：总仓位不能超过100%、单票上限

B. 风险平价方法：
- 等风险贡献（ERC）——每只股票对组合风险的边际贡献相等
- 协方差矩阵估计：用历史收益率滚动窗口（多长？60天/120天/250天？）
- A股的特殊问题：个股波动率普遍偏高（年化30-60%）、涨跌停板导致协方差估计偏差
- 实际计算例子：6只持仓（当前持仓：大港/烽火/生益/信维/三花/创世纪）

C. 波动率调整仓位：
- 目标波动率法：确定组合目标年化波动率→反向计算每只股票的仓位
- ATR(平均真实波幅) 仓位法：stop_loss_pct / ATR_pct → 确定可买股数
- 波动率体制自适应：低波动时加仓/高波动时减仓
- VIX/中国波指(iVX)作为总仓位调节器

D. 实际约束：
- A股最小交易单位100股（一手）
- 单日涨跌停限制对止损执行的影响（流动性风险）
- T+1制度对日内调仓的限制
- 印花税/佣金对频繁调仓的摩擦成本

E. 综合方案设计：
- 建议采用哪套仓位计算体系？（单一 vs 混合）
- 输入参数：总资金/风险容忍度/持仓数量上限/单票上限
- 输出：每只股票的精确股数（向下取整到100的倍数）
- 调仓频率：多久重新计算一次仓位？
- 与现有 expert5_risk 的集成方式

F. 数值示例：
用当前持仓（6只股票，假设总资金50万）跑一遍：
- 凯利法计算出的各仓位
- 风险平价法计算出的各仓位
- 波动率调整法计算出的各仓位
- 三种方法的对比分析和推荐

输出要求：给出三种方法的公式+Python伪代码+数值示例。区分"数学上最优"和"实际可执行"的差距。"""
    },
}

def research_single_gap(gap_id: str) -> dict:
    """对单个缺口执行 Ch2 深度研究。"""
    info = GAP_RESEARCH_PROMPTS.get(gap_id)
    if not info:
        logger.warning("未找到缺口研究配置: %s", gap_id)
        return {"gap_id": gap_id, "findings": ["无研究配置"], "error": "missing_config"}

    prompt = info["prompt"]
    logger.info("开始研究 [%s]...", gap_id)

    try:
        result = ch2_research(prompt, max_tokens=8192)
        logger.info("研究完成 [%s], 长度=%d", gap_id, len(result))
        return {
            "gap_id": gap_id,
            "findings_raw": result,
            "channel": "Ch2",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error("研究失败 [%s]: %s", gap_id, e)
        return {"gap_id": gap_id, "findings_raw": f"[研究失败: {e}]", "error": str(e)}


def extract_findings(result_raw: str) -> list[str]:
    """从原始研究结果中提取关键发现（每段第一句/核心结论）。"""
    lines = result_raw.strip().split("\n")
    findings = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 取以数字/字母/破折号开头的关键句
        if (line.startswith(("1", "2", "3", "4", "5", "A", "B", "C", "D", "E", "F",
                             "-", "*", "**", ">", "•", "核心", "关键", "建议", "结论"))
            or len(line) > 30):
            if len(findings) < 15:  # 最多15条
                findings.append(line[:200])  # 每条截取200字符
    return findings


def determine_new_status(findings_raw: str) -> str:
    """根据研究结果判断缺口新状态。

    - 有具体实现方案/代码/数值 → "absorbed"
    - 有方向性参考但缺乏可落地细节 → "insight_enriched"
    - 答案空泛或无实质内容 → "solution_found"
    """
    raw = findings_raw.lower()
    # absorbed 信号：提到具体代码/实现方案/数值/package名/配置
    absorbed_signals = [
        "pip install", "import ", "class ", "def ",
        "```python", "```json", "具体的实现", "建议采用",
        "redis", "sqlite", "ttl", "guardrails-ai",
        "business-rules", "durable_rules", "kelly",
        "年化", "股数", "计算得出", "示例",
    ]
    # insight_enriched 信号：有方向性分析但缺代码
    insight_signals = [
        "可以考虑", "参考", "设计模式", "架构",
        "原则", "最佳实践", "建议", "推荐",
        "落地", "集成",
    ]

    absorbed_count = sum(1 for s in absorbed_signals if s in raw)
    insight_count = sum(1 for s in insight_signals if s in raw)

    if absorbed_count >= 3:
        return "absorbed"
    elif insight_count >= 2:
        return "insight_enriched"
    else:
        return "solution_found"


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )

    gap_ids = list(GAP_RESEARCH_PROMPTS.keys())
    print(f"Phase2 深度研究开始: {len(gap_ids)} 个缺口")
    print(f"使用 Channel 2 (research) 独立配额")
    print("=" * 60)

    # 获取当前状态
    registry = load_registry()
    gap_statuses = {}
    for g in registry:
        if g["gap_id"] in gap_ids:
            gap_statuses[g["gap_id"]] = g.get("status", "unknown")

    results = []

    # 逐个研究（串行，避免API限流）
    for i, gap_id in enumerate(gap_ids):
        prev_status = gap_statuses.get(gap_id, "unknown")
        print(f"\n[{i+1}/{len(gap_ids)}] 研究: {gap_id} (上轮状态: {prev_status})")

        result = research_single_gap(gap_id)
        findings_raw = result.get("findings_raw", "")

        if result.get("error"):
            print(f"  ✗ 失败: {result['error']}")
            results.append({
                "gap_id": gap_id,
                "previous_status": prev_status,
                "new_status": prev_status,  # 保持原状态
                "findings": ["研究失败"],
                "actionable_plan": "",
                "error": result["error"],
            })
            continue

        # 提取发现
        findings = extract_findings(findings_raw)
        new_status = determine_new_status(findings_raw)

        # 打印摘要
        print(f"  状态变更: {prev_status} → {new_status}")
        print(f"  发现数量: {len(findings)}")
        for f in findings[:5]:
            print(f"    - {f[:120]}")

        # 构建可落地计划
        if new_status == "absorbed":
            actionable = "已获取具体实现方案，可进入吸收阶段（创建提案→实施→验证）"
        elif new_status == "insight_enriched":
            actionable = "已充实方向性指导，下一步需要针对性搜索补充实现细节"
        else:
            actionable = "方案仍停留在理论层面，建议改为人工搜索或等待新工具支持"

        results.append({
            "gap_id": gap_id,
            "previous_status": prev_status,
            "new_status": new_status,
            "findings": findings,
            "findings_full": findings_raw,
            "actionable_plan": actionable,
            "channel": result.get("channel", "Ch2"),
            "research_time": result.get("timestamp", ""),
        })

        # 更新缺口状态（只升级，不降级）
        status_order = {"open": 0, "investigating": 1, "solution_found": 2,
                       "insight_enriched": 3, "absorbed": 4, "verified": 5}
        if status_order.get(new_status, 0) > status_order.get(prev_status, 0):
            update_gap(gap_id, {
                "status": new_status,
                "research_phase2_at": datetime.now().isoformat(),
            })
            print(f"  缺口状态已更新: {gap_id} → {new_status}")

    # 汇总建议
    recommendations = []
    absorbed = [r for r in results if r["new_status"] == "absorbed"]
    enriched = [r for r in results if r["new_status"] == "insight_enriched"]
    unchanged = [r for r in results if r["new_status"] == "solution_found"]

    if absorbed:
        recommendations.append(f"立即吸收 {len(absorbed)} 个缺口: {[r['gap_id'] for r in absorbed]}")
    if enriched:
        recommendations.append(f"针对 {len(enriched)} 个缺口做第三轮定向搜索: {[r['gap_id'] for r in enriched]}")
    if unchanged:
        recommendations.append(f"{len(unchanged)} 个缺口需要人工搜索或新工具: {[r['gap_id'] for r in unchanged]}")

    # 构建最终报告
    report = {
        "phase": 2,
        "generated_at": datetime.now().isoformat(),
        "channel_used": "Ch2 (research, 独立配额)",
        "gaps_researched": [
            {
                "gap_id": r["gap_id"],
                "previous_status": r["previous_status"],
                "new_status": r["new_status"],
                "findings": r["findings"],
                "actionable_plan": r["actionable_plan"],
            }
            for r in results
        ],
        "recommendations": recommendations,
        "stats": {
            "total": len(results),
            "absorbed": len(absorbed),
            "insight_enriched": len(enriched),
            "solution_found": len(unchanged),
            "failed": len([r for r in results if r.get("error")]),
        },
    }

    # 写入输出文件
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    # 清理findings_full以减小文件体积（不写入完整原始回答）
    for r in report["gaps_researched"]:
        # 保留findings_full到一个单独的details文件
        pass

    OUTPUT_FILE.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 写入详细原始回答到单独文件
    details_file = Path("D:/1989n/stock_data/status/deep_research_phase2_details.json")
    details = {
        "phase": 2,
        "generated_at": datetime.now().isoformat(),
        "results": [
            {
                "gap_id": r["gap_id"],
                "findings_full": r.get("findings_full", ""),
            }
            for r in results
        ],
    }
    details_file.write_text(
        json.dumps(details, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n{'='*60}")
    print(f"Phase2 研究完成!")
    print(f"  报告: {OUTPUT_FILE}")
    print(f"  详情: {details_file}")
    print(f"  统计: {report['stats']}")
    print(f"  建议: {recommendations}")

    return report


if __name__ == "__main__":
    main()
