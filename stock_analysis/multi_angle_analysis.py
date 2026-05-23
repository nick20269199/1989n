"""
multi_angle_analysis.py — 同批会话数据 → 10个DeepSeek分析方向 → 10份独立报告

用法:
  cd D:/1989n/stock_analysis && /d/Python314/python multi_angle_analysis.py

依赖:
  - conversation_miner.py 的会话提取逻辑
  - deepseek_multi.py (Channel 3 parallel)
"""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DATA = Path("D:/1989n/stock_data/interaction")
STOCK_ANALYSIS = Path("D:/1989n/stock_analysis")
sys.path.insert(0, str(STOCK_ANALYSIS))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("multi_angle")

# ── 复用 conversation_miner 的会话提取 ──
from conversation_miner import (
    C_JSONL_DIRS,
    scan_jsonl_files,
    extract_session_from_jsonl,
    summarize_session,
    build_analysis_prompt,
    validate_jsonl_dir,
    load_state,
)

# ── 复用 DeepSeek 通道 ──
from deepseek_multi import parallel_analyze

OUT_DIR = BASE_DATA / "multi_angle"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════
# 10个分析方向 — 每个方向一个系统提示
# ═══════════════════════════════════════════════════════════════

ANGLES = [
    {
        "id": "01_market_correlation",
        "title": "市场关联分析",
        "prompt": """你是一位用户行为与市场联动分析师。

分析以下对话记录，关注 **交易决策质量与交互质量的相关性**：

1. 用户交易赚钱/亏钱后，交互行为模式是否不同？（指令长度、耐心程度、纠错频率）
2. 用户在特定市场环境（大盘涨/跌/震荡）下的交互模式差异
3. AI输出的质量是否随用户情绪状态变化？用户不耐烦时错误率是否更高？
4. 找出"交易决策-交互质量"的反馈循环：交易好坏 → 情绪 → 交互质量 → 交易决策

输出要求：
- 每个结论标注置信度 [high/medium/low]
- 给出具体证据（引用会话中的可观测信号）
- 如果有"相关性"请标注是否可能有"因果性"
""",
    },
    {
        "id": "02_information_density",
        "title": "信息密度分析",
        "prompt": """你是一位信息论和沟通效率分析师。

分析以下对话记录，关注 **信息密度与沟通效率**：

1. 用户每条消息的信息熵：平均一条用户消息包含多少个独立意图/指令？
2. 信息密度与任务完成率的关系：高密度指令（一条消息多个要求）的完成率 vs 低密度指令
3. 哪类任务需要最多的对话轮次才能完成？哪类最少？
4. 冗余度分析：用户需要重复/澄清多少次？什么话题循环率最高？
5. 估算每轮对话的"信息压缩率"：用户输入的字符数 vs AI实际产出的有用信息量

输出要求：
- 用具体数字说话（平均轮次、重复率等）
- 标注结论置信度
""",
    },
    {
        "id": "03_error_cascade",
        "title": "错误传染链分析",
        "prompt": """你是一位系统故障分析专家。

分析以下对话记录，关注 **错误如何在一个会话中传播和扩大**：

1. 一处数据错误（如B读成S）之后，后续分析被连带影响的比例是多少？
2. 错误发现时间：用户一般是在第几轮交互后发现第一个错误的？
3. "错误半衰期"：一个错误从发生到被纠正，平均经过多少轮对话？
4. 传染模式：一个错误发生后，后续多少个动作/决策会被污染？
5. 有没有"错误免疫"的典型案例——一个错误发生后被及时拦截的？
6. 估算错误传染的"基本再生数R0"：一个错误平均导致多少个后续错误？

输出要求：
- 用具体数字估算，标注置信度
- 区分"用户发现的错误"和"AI自纠的错误"
""",
    },
    {
        "id": "04_efficiency_boundary",
        "title": "效率边界分析",
        "prompt": """你是一位生产力分析师。

分析以下对话记录，关注 **AI协助的效率边界**：

1. 什么类型的任务AI完成效率 >= 用户自己做？（如数据读取、格式整理）
2. 什么类型的任务AI效率低于用户自己做？（如需要交易直觉、判断力、上下文理解）
3. 什么情况下用户选择"算了我自己来"？这些场景有什么共同特征？
4. 任务的复杂度与AI完成质量的非线性关系：简单任务表现、中等任务、复杂任务各如何？
5. 估算各类任务的"净效率"：AI完成需要的时间 vs 用户纠正需要的时间

输出要求：
- 尝试给不同类型任务做"效率评级"
- 标注每个判断的置信度
""",
    },
    {
        "id": "05_expectation_gap",
        "title": "预期误差分析",
        "prompt": """你是一位认知心理学家，专攻人机交互中的预期误差。

分析以下对话记录，关注 **用户预期与实际表现之间的差距**：

1. 用户对AI能力的预期模型：从对话中可以推断出用户认为"AI应该能做什么"？
2. 预期误差的具体类型：
   - 能力误估：用户认为AI能做但实际上不能的
   - 速度误估：用户认为AI应该多快完成
   - 准确率误估：用户认为AI应该多准
3. 预期误差第一次出现到用户调整预期的过程：用户是怎么修正对AI的能力认知的？
4. 预期误差与信任的量化关系：一次预期误差对应多少信任损失？
5. 反向预期：用户是否有时低估了AI的能力？（即AI做到了用户认为做不了的）

输出要求：
- 标注置信度
- 用具体对话片段作为证据
""",
    },
    {
        "id": "06_attention_roi",
        "title": "注意力ROI分析",
        "prompt": """你是一位注意力经济学分析师。

分析以下对话记录，关注 **用户注意力的投入产出比**：

1. 用户在哪类任务上投入的注意力最多（对话轮次、纠错频率、追问深度）？回报是什么？
2. 哪类任务的"注意力ROI"最高？即用户投入少量注意力但获得了高价值产出
3. 哪类任务的"注意力ROI"最低？即用户反复投入注意力但产出低
4. 用户注意力的衰减模式：在一个长会话中，用户注意力如何变化？
5. 有没有"注意力陷阱"——用户投入大量注意力但没有实质产出的任务？

输出要求：
- 用对话轮次、字符数等量化指标
- 标注置信度
""",
    },
    {
        "id": "07_compression_ratio",
        "title": "沟通压缩率分析",
        "prompt": """你是一位通信工程师，专攻人机对话的压缩效率。

分析以下对话记录，关注 **沟通压缩率**：

1. 定义"问题单元"并统计：每个独立的问题/指令算一个单元
2. 每轮对话解决了多少"问题单元"？是1:1、1:N还是N:1？
3. 压缩瓶颈：什么场景下1个问题需要N轮才能解决？N的分布是什么？
4. 用户指令越来越短是"压缩成功"还是"信任下降"的表现？（即用户因为不信任而减少指令复杂度）
5. 估算对话的"香农效率"：实际传递的信息量 / 理论最大信息量
6. 有没有"最佳压缩点"？即多少轮对话完成后，用户获得的信息量最大？

输出要求：
- 量化估算，标注置信度
""",
    },
    {
        "id": "08_pattern_resilience",
        "title": "模式韧性分析",
        "prompt": """你是一位行为模式分析师。

分析以下对话记录，关注 **错误模式在被纠正后的存活时间**：

1. 用户指出一个具体错误后，同样的错误在多少轮/多少会话后再次出现？
2. 错误模式的"半衰期"：从被纠正到再犯的平均间隔
3. 什么类型的错误更容易复发？（数据类 vs 理解类 vs 执行类）
4. 用户纠正的"格式"（详细解释 vs 简短指出 vs 情绪化批评）与纠正效果的关系
5. 有没有经过一次纠正就永久消除的错误？有什么共同特征？
6. 模式韧性曲线：是逐步改善（每次复发间隔变长）还是稳定不变？

输出要求：
- 用时间线数据说话
- 标注置信度
""",
    },
    {
        "id": "09_safety_net_analysis",
        "title": "安全网冗余分析",
        "prompt": """你是一位系统安全工程师。

分析以下对话记录，关注 **系统的安全网层级和每层拦截率**：

1. 识别系统中的"安全网层级"：
   - L0: AI自我检查（AI自己发现并纠正错误）
   - L1: 系统机制（hooks、校验程序）
   - L2: 用户即时纠正
   - L3: 用户后续验证（复盘检查）
   - L4: 未被发现/到达的错误（沉默错误）
2. 每层安全网拦截了多大比例的错误？
3. "安全盲区"：哪些错误穿过了所有安全网？
4. 安全网的延迟：从错误发生到被拦截，每层平均需要多少时间/轮次？
5. 有没有"安全网幻觉"——即用户以为某层安全网存在但实际上不存在？

输出要求：
- 给出每层拦截率的估算
- 标注置信度
""",
    },
    {
        "id": "10_cross_angle_synthesis",
        "title": "跨角度综合交叉分析",
        "prompt": """你是一位多维度交叉分析师。

你现在拥有前面9个角度各自的分析结果（不一定真实存在），请直接从原始数据出发，进行 **跨角度交叉验证**：

1. 寻找多个角度之间的"共振点"——至少有3个不同角度指向同一个核心问题的
2. 寻找角度之间的矛盾点——不同角度得出矛盾结论的地方，分析为什么
3. 构建"因果环"：用前面9个分析方向找到的元素，画出一个完整的因果循环图
4. 识别"高杠杆干预点"——同时在多个角度维度上有正面影响的单一改变点
5. 预测：如果这些干预点被实施，系统状态会如何演化？
6. 给出一个"跨角度优先级排序"：在10个方向的交汇处，什么最值得先做？

输出要求：
- 标注每个结论的置信度
- 明确指出哪些是"从多个角度交叉验证"的结论
""",
    },
]


def load_all_sessions() -> list[dict]:
    """加载所有会话摘要（全量模式）。"""
    if not validate_jsonl_dir():
        logger.error("JSONL 目录不可用")
        return []

    to_process = scan_jsonl_files(full_scan=True)
    if not to_process:
        logger.info("无会话文件")
        return []

    all_sessions = []
    for fp, offset in to_process:
        sessions = extract_session_from_jsonl(fp, start_line=0)
        all_sessions.extend(sessions)

    return [summarize_session(s) for s in all_sessions]


def run():
    # 阶段1: 加载数据
    logger.info("=" * 60)
    logger.info("阶段1: 加载全部会话数据...")
    summaries = load_all_sessions()
    if not summaries:
        logger.error("无会话数据，退出")
        return
    logger.info(f"成功加载 {len(summaries)} 个会话摘要")

    # 构建基础会话 prompt（复用 conversation_miner 的格式）
    base_prompt = build_analysis_prompt(summaries)

    # 阶段2: 逐个方向跑 DeepSeek
    state = load_state()
    total = state.get("total_sessions_processed", 0) or len(summaries)

    for i, angle in enumerate(ANGLES, 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"[{i}/10] 方向: {angle['title']} ({angle['id']})")
        logger.info(f"{'='*60}")

        full_prompt = f"""分析以下 {total} 个会话的数据。

{angle['prompt']}

---

会话数据：
{base_prompt}
"""

        logger.info("发送到 DeepSeek Channel 3 (parallel)...")
        t0 = time.time()

        try:
            result = parallel_analyze(
                full_prompt,
                system=angle['prompt'],
                temperature=0.3,
                max_tokens=4096,
            )
            elapsed = time.time() - t0
            logger.info(f"DeepSeek 返回 ({elapsed:.1f}s), 长度: {len(result)} 字符")

        except Exception as e:
            logger.error(f"DeepSeek 调用失败: {e}")
            result = f"[分析失败] {e}"

        # 写文件
        out_file = OUT_DIR / f"{angle['id']}.md"
        content = [
            f"# 多角度分析 | {angle['title']}",
            f"",
            f"> 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"> 分析会话数: {len(summaries)}",
            f"> 分析引擎: DeepSeek Channel 3 (parallel)",
            f"> 角度编号: {i}/10",
            f"",
            f"## 分析方向",
            f"",
            f"{angle['prompt']}",
            f"",
            f"---",
            f"",
            f"## 分析结果",
            f"",
            result,
        ]
        out_file.write_text("\n".join(content), encoding="utf-8")
        logger.info(f"写入: {out_file}")

        # 节流——避免 DeepSeek 速率限制
        if i < len(ANGLES):
            wait = 5
            logger.info(f"等待 {wait}s 控制速率...")
            time.sleep(wait)

    # 总结
    logger.info(f"\n{'='*60}")
    logger.info("全部 10 次分析完成")
    logger.info(f"输出目录: {OUT_DIR}")
    for angle in ANGLES:
        f = OUT_DIR / f"{angle['id']}.md"
        size = f.stat().st_size if f.exists() else 0
        logger.info(f"  {angle['id']}: {size} 字节")


if __name__ == "__main__":
    run()
