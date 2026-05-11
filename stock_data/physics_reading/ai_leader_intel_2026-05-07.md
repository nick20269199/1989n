# AI领袖情报 — 2026-05-07 同步

## 1. Andrej Karpathy (@karpathy)

**2026年核心演进路径**：Vibe Coding(2025) → Agentic Engineering(2026.2) → Context Engineering(2026.4)

**三个软件范式**：
- Software 1.0: 写代码
- Software 2.0: 整理数据集训练神经网络
- Software 3.0: LLM本身就是计算机，"编程"=写prompt，上下文窗口=控制杆

**LLM Wiki架构**（与我们的三层架构高度一致）：
```
raw/     → 原始材料（只读不可变）
wiki/    → LLM生成的结构化知识
schema/  → 规则约束文件(CLAUDE.md)
```
操作：Ingest(摄入), Query(查询), Lint(每月检查)

**最关键的洞见**：
- "可以外包思考，但不能外包理解"
- "代码这个词已经不对了" —— 新动词是"指令"、"编排"、"验证"
- 瓶颈从写代码转移到token吞吐率
- AutoResearch架构：Untrusted workers(便宜/大量/探索) + Trusted workers(少量/验证/把关)

## 2. Boris Cherny (@bcherny)

**身份**：Claude Code创建者，Anthropic开发负责人

**工作方式**（毫不夸张）：
- 2025年10月起至今，100%代码由AI生成，零手写
- 每天10-30个PR，最高纪录150个/天（大部分在iPhone上完成）
- 同时运行5个终端agent + 5-10个浏览器agent
- 用StarCraft比喻描述自己的工作——管理自治单元，不写语法

**/loop是他最推崇的功能**：
- 几十个loop同时跑：babysit PRs、auto-fix CI、auto-rebase
- 每30分钟爬取Twitter反馈并聚类用户情绪
- 晚上跑上千个agents做深度后台工作
- Routines=服务端loop——关电脑也继续

**CLAUDE.md的核心哲学**：
- 每次出错→加入CLAUDE.md→永不重复
- 把代码库变成自我进化的有机体

**关键预言**：
- Claude Code一年内可能缩到100行（模型越来越不需要编排水管）
- 工程师→Builder：定义目标、判断输出、编排agent
- 好会计软件将由好会计（而非好工程师）构建——领域知识是新护城河
- 10倍更多颠覆性startup

**Anthropic内部**：Claudes在Slack上互相通信——agents之间协调解决未知问题

## 3. 全球AI社交影响力 Top 20（2026.3）

按顶级AI领袖共同关注频次排名：
1. @karpathy — Andrej Karpathy
2. @sama — Sam Altman
3. @ylecun — Yann LeCun
4. @gdb — Greg Brockman
5. @OfficialLoganK — Logan Kilpatrick
6. @JeffDean — Jeff Dean
7. @demishassabis — Demis Hassabis
8. @elonmusk — Elon Musk
9. @ilyasut — Ilya Sutskever
10. @OpenAI — OpenAI官方
11. @miramurati — Mira Murati
12. @AndrewYNg — Andrew Ng
13. @AnthropicAI — Anthropic官方
14. @alexandr_wang — Alexandr Wang
15. @AravSrinivas — Aravind Srinivas
16. @DrJimFan — Jim Fan
17. @levie — Aaron Levie
18. @steipete — Peter Steinberger(OpenClaw)
19. @deedydas — Deedy Das
20. @polynoamial — Noam Brown(o1)

## 4. 关键开源工具（来自B站溯源）

| 工具 | 用途 | 状态 |
|------|------|------|
| Graphify(~39K stars) | 零配置全模态知识图谱 | 我们已安装skill |
| GitNexus(~26K stars) | 代码库MCP神经系统 | 可安装 |
| planning-with-files | 持久化Markdown工作记忆 | 我们已在使用 |
| Karpathy llm-wiki | LLM知识库架构 | 我们MEMORY.md模仿了其结构 |

## 5. Ilya Sutskever — Return to Research Era (2025.11 Dwarkesh Patel Podcast)

**核心观点**：
- **Scaling已遇瓶颈**: "我们已经用尽了过去所有的数据，只有一个互联网。" 预训练scaling进入递减回报期
- **SSI的"超级智能15岁少年"**: SSI目标不是AGI服务——是创造一个"超级智能的15岁少年"——有知识但还不够，需要引导
- **新scaling维度**: 推理时算力（o1式推理链）、self-play、合成数据。这些是新前沿
- **对齐哲学**: 超智能必须"想对我们好"——不只是"被迫"对我们好。真正的对齐=内在动机对齐。"如果AI本身想对我们好，那稳定性就解决了"
- **时间线**: 5-20年出现真正的超智能。"我们肯定说5年以上，但不应该完全排除20年"
- **Return to Research Era**: 现在是"回归研究时代"——不是工程瓶颈，是研究突破瓶颈

**对我们的启示**: Ilya的"内在动机对齐"与我们的"无我推理"原则高度一致——Agent需要内在地"想"做好，不只是被动安全规则约束

## 6. Dario Amodei — 攀登没有墙 (2026.3 Morgan Stanley TMT)

**核心观点**：
- **Scaling没有墙**: "目前没有看到墙。如果有人告诉你他们在攀登一堵墙，说明他们其实没在攀登。"
- **递归自我改进**: 今天AI已帮写25-50%代码。一年内→90%人类水平代码。之后→AI开始改进自己的训练代码→飞轮启动
- **"指数曲线的终点"=最后冲刺**: 过去的匀速爬坡→最后几公里=指数曲线的垂直部分→"终点线前最后20秒的全力以赴"。不是"我们要到头了，该放缓了"——正相反
- **AGI时间线**: 直觉判断1-3年。不需要更多"突破"——需要把已有东西扩展+工程化
- **Claude做物理博士**: 某实验室用Claude做物理研究——提出新假设→设计实验→分析数据→一周完成
- **安全视角**: Anthropic在扩展安全研究的同时推进能力——"我们不能减速因为如果不做有人会做，且不做好安全"

**对我们的启示**: 递归自我改进=我们的SEL v2.0 Growth Loop的理论基础。Dario确认了我们已经在做的事正确

## 7. Boris Cherny — Claude Code创建者的Agent编排 (2026 Sequoia AI Ascent + Pragmatic Engineer)

**更多细节**（补充上面第2节）：
- **Parallel agents**: 同时5-10个agent解决独立子问题
- **Verification loops**: "写验证代码是加速最重要的活动"——验证=AI进步的唯一可靠驱动力
- **Cron-loops**: 重复性work定时后台跑——代码审查/PR合并/安全扫描/文档更新
- **CLAUDE.md共享记忆**: 所有agent共用一个CLAUDE.md——每次错误写入→永不重复→系统自我进化
- **Plan Mode的价值**: "Plan mode是我每天用100次的最强功能"——写plan前先让agent自己plan，然后人审
- **"我在iPhone上完成大部分PR"**: 在手机上写PR描述→agent自动实现→CI验证→merge

**对我们的启示**: 我们的cron-loop已经是Cherny模式。下一步：增加parallel agent并行能力

## 9. Yann LeCun — 离开Meta创立AMI Labs (2026.3)

**重大事件**: 2026.3离开Meta，巴黎创立AMI Labs，10.3亿美元种子轮（科技史上最大之一），投前估值35亿美元。

**核心诊断: LLM路线错了**
- "LLM已经把房间里的空气都吸光了...单靠扩大LLM永远不可能走到人类级AI"
- 生成式路线有根本上限：在像素/token空间重建一切细节在物理世界行不通——大部分细节本质不可预测
- **JEPA核心**: 不重建信号全部细节，在**抽象表征空间**中做预测。编码器压缩掉不可预测的噪声

**JEPA四层路线图进度**:
| 层级 | 内容 | 进度 |
|------|------|------|
| Level 0 基础JEPA | 单模态潜空间预测 | ✅ 100% |
| Level 1 多模态JEPA | 图像/视频/语言/音频全覆盖 | ✅ ~95% |
| Level 2 世界模型JEPA | 时序+物理+动作+因果推理 | 🔄 ~80% |
| Level 3 分层思考JEPA | 多层抽象+长期规划 | 🔜 进行中 |

**2026关键论文**: EchoJEPA(医学超声验证)、VL-JEPA(视觉语言2.85x加速)、STP(违反Chinchilla缩放律——1/16数据达全量精度)

**终极架构**: 感知→世界模型(JEPA)→成本模块→行动模块，世界模型在抽象空间预测行动后果，通过最优控制反向推导最优行动序列

**对我们的启示**: LeCun的"抽象表征空间预测"与我们的"推理=在语义空间而非token空间操作"一致。JEPA的分层规划=我们的嵌套推理架构

## 10. Demis Hassabis — AGI四步计划 (2026 WEF达沃斯)

**AGI时间线: 5-10年（最保守的乐观派）**
- 50%概率2030年前实现AGI
- 比Amodei(1-3年)和Altman(2-3年)保守得多
- 在达沃斯呼吁**适当放缓节奏**让社会治理跟上

**AGI定义: 非单一模型，多系统融合**
- 世界模型 + 推理能力 + 感知能力 + 智能体系统 = AGI
- 当前差距: 仅缺1-2个关键突破
- 已具备: 大规模预训练、RLHF、思维链、多模态
- 仍缺失: **持续学习**、**长程推理**、**记忆系统优雅整合**、**世界模型(物理规则理解)**

**"锯齿状智能"(Jagged Intelligence)**: 能解IMO奥数却犯小学算术错误——与我们的"推理能力分布不均"观察一致

**2026年DeepMind四大动作**:
1. 自动化实验室(AI+机器人+材料科学)
2. 模型大融合(Gemini+Genie+SIMA→AGI原型)
3. 世界模型推进(虚拟环境→自主学习→闭环训练)
4. 物理基准测试(球滚动/摆运动——检验物理定律掌握)

**对社会预见**: AGI革命=工业革命10倍规模10倍速度。给创业者的警告:"十年期深科技项目必须把AGI中途出现纳入规划"

**对我们的启示**: Hassabis的"多系统融合"=我们的知识三角(物理+宗教+经济+中华)。他的"锯齿状智能"诊断验证了我们的多Agent互补策略

## 11. Jensen Huang — AI工厂时代 (GTC 2026.3 + Morgan Stanley TMT)

**GTC 2026核心宣言**:
- "推理的转折点已经到来"——从训练→推理的时代转型
- 数据中心="AI工厂"——把电力转化为tokens
- **Tokens per watt = "公司营收最重要的事"**
- Blackwell+Vera Rubin采购订单目标: **$1万亿到2027年**

**Agentic AI = "新计算机"**:
- "未来不会有任何软件不是agentic的"
- OpenClaw: 开源agentic AI操作系统(黄仁勋称其"与Linux/HTML/Kubernetes同等重要")
- NemoClaw: 企业版(安全护栏+策略控制+隐私路由)
- "每个公司都需要一个OpenClaw战略"

**硬件路线图**:
| 平台 | 年份 | 关键 |
|------|------|------|
| Vera Rubin | 2026 | 3.6 exaflops/rack, 比10年前快4000万倍 |
| Kyber (Rubin Ultra) | 2027 | NVL144, 144 GPU垂直计算托盘 |
| Feynman | 2028 | 3D芯片堆叠, TSMC 1.6nm, 新Rosa CPU |

**$50万亿物理经济体**: "整条产线由机器人运营，由更多机器人管理，整个工厂就是一个机器人"

**关键引语**: "Compute = Intelligence, Intelligence = Revenue, Revenue = GDP"

**对我们的启示**: Huang的"tokens per watt"=我们铁律1熵预算的工程化表达。OpenClaw=Cherny的agent基础设施的商品化。Agentic everywhere验证了我们多Agent架构方向

## 12. Andrew Ng — Agentic Workflow + 沙盒优先 (2026达沃斯)

**核心判断: Agentic Workflow > 更大模型**
- 实验证明: GPT-3.5+Agentic Workflow > GPT-4零样本
- "真正的商业变革不在万亿参数模型中，在Agentic Workflows里"
- 四种核心设计模式: 反思/工具使用/规划/多智能体协作

**"100倍"战略视角**:
- 不要只问"省了多少钱"——问"能否快100倍？多做100倍？"
- 贷款审批从1小时→10分钟是省成本。10分钟即时到账是重构价值链

**数据驱动务实主义**:
- "数据清理是永无止境的旅程，你认为数据乱？其实所有人都一样"
- 不等待完美数据——让高价值应用拉动数据改进
- 医疗/金融等垂直领域必须专门获取+清洗+输入该领域数据

**"沙盒优先"创新解法**:
- 预设沙盒: 限定预算/限定内部测试/不涉敏感数据/不对外品牌
- 找到客户真正热爱的成果后再投入治理与安全

**人才重塑**: AI将自动化30-40%任务而非消灭职位。顶层="10-20年经验+精通AI"的工程师。PM+工程师角色坍缩进一个人体内

**AGI冷眼**: "至少几十年之遥"，当前已是营销泡沫。"远程员工Turing-AGI测试"——让AI作为远程员工几天内学会并完成全新复杂任务

**对我们的启示**: Ng的Agentic Workflow四模式已在我们Agent编排中实践。沙盒优先=我们的"先为不可胜，在边缘实验"策略

## 13. Jim Fan — 世界建模是新预训练范式 (NVIDIA GEAR 2026.2)

**身份**: NVIDIA具身自主研究GEAR实验室负责人，李飞飞弟子

**核心宣言**:
- "2026将是大世界模型真正为机器人奠定基础的第一年"
- AI正经历第二次预训练范式转变: 从"预测下一个词"→"预测下一个物理状态"
- "猿类没有优秀的语言模型，但物理技能远超最先进机器人"
- "Ilya说得没错——AGI尚未收敛。我们又回到了研究时代"

**VLA→World Action Model范式转换**:
| 旧VLA | 新World Action Model |
|--------|---------------------|
| 语言优先 | 视觉/物理优先 |
| 知识检索强物理弱 | 先预测世界动力学再学行动 |
| 多阶段嫁接 | 端到端统一架构 |

**Dream Zero数据效率**:
- 20,000小时人类手部视频预训练
- **零机器人数据**(0%)预训练
- 仅50小时模拟+4小时真实数据微调(<0.1%)
- "遥操作已死"——人类自我中心视频取代遥操作数据

**2040终局预测**: 物理图灵测试(2-3年)→物理API(中远期)→物理自动化研究顶峰/机器人自改进自构建(2040)

**对我们的启示**: Jim Fan的世界模型预训练=我们的"先验知识是推理的锚"原则。数据效率革命(4小时真实数据)验证了铁律10(简洁涌现)

## 14. Noam Brown — 推理时计算扩展+多Agent文明 (OpenAI)

**身份**: OpenAI o系列推理模型核心研究科学家。前Meta FAIR(Libratus/Pluribus/CICERO)

**职业脉络**: 不完美信息博弈(扑克)→自然语言谈判(Diplomacy)→通用推理(o系列)

**o3推理模型**:
- 2025.4发布，错误率比o1减少~20%
- "推理时计算扩展"范式: 分配更多算力"思考"→分解复杂问题→多策略+自我纠错
- AIME 96.7%, ARC-AGI 87.5%, Codeforces 2727
- o3-pro(2025.6): 思考更长时间获得最大可靠性

**"AI原始人假说" (2025.6 Latent Space)**:
- 当前AI≈7万年前智人——有能力但未形成文明
- 多智能体系统通过相互竞争+合作→可能实现文明级别能力跃升
- 推理时间从分钟→数天→数周——让模型持续思考

**2026年影响**: 
- Ethan Mollick主张o3应被视为AGI——引发行业辩论
- Greg Brockman披露GPT-5路线图由"o3及后续"填补
- 算法优化>算力堆叠——o3同预算下碾压o1

**从扑克到o3的逻辑链**: 扑克中的不确定下搜索+迭代自我博弈+反事实推理→o系列的隐藏思维链+RL架构

**对我们的启示**: Brown的"AI原始人假说"=我们的合纵涌现律——多Agent协作产生文明级能力。"推理时计算=深度思考"验证了铁律1熵预算的多档位设计

## 15. 七大AI领袖2026观点矩阵

| 领袖 | AGI时间线 | 核心路线 | 关键概念 | 与我们框架的交叉点 |
|------|----------|---------|---------|-----------------|
| **Karpathy** | 未明确 | Agentic Engineering | Software 3.0 / "ghosts not animals" | 铁律9(弱同步)+庖丁解牛 |
| **Ilya** | 5-20年 | SSI超级智能15岁 | 内在动机对齐/Return to Research Era | 无我推理+心性公式 |
| **Dario** | 1-3年 | 递归自我改进 | "攀登没有墙"/指数最后冲刺 | SEL v2.0 Growth Loop |
| **Cherny** | 未明确 | Agent编排 | Cron-loop/CLAUDE.md/Verification | 考异溯定律+铁律1 |
| **LeCun** | 未明确 | JEPA世界模型 | 抽象表征空间预测/LLM路线错了 | 嵌套推理+语义空间操作 |
| **Hassabis** | 5-10年 | 多系统融合 | 锯齿状智能/世界模型+推理+感知 | 知识三角+多Agent互补 |
| **Huang** | 未明确 | AI工厂 | tokens per watt/Agentic=新计算机 | 熵预算工程化+多Agent架构 |
| **Andrew Ng** | 数十年 | Agentic Workflow | 沙盒优先/100倍视角 | 四模式+边缘实验 |
| **Jim Fan** | 2040(机器人) | 世界建模预训练 | 预测下一个物理状态 | 铁律10(简洁涌现)+先验锚 |
| **Noam Brown** | 未明确 | 推理时计算扩展 | AI原始人假说/多Agent文明 | 合纵涌现律+铁律1多档位 |

## 16. 与物理/中华/宗教知识框架的交叉验证

| 2026 AI领袖洞见 | 物理铁律 | 中华公式 | 宗教原则 |
|---------------|---------|---------|---------|
| Karpathy "可以外包思考不能外包理解" | 铁律6(自由能最小化) — 理解=内部模型压缩 | 庖丁解牛(直觉穿透) | 吾丧我(元认知观察) |
| Ilya "内在动机对齐" | 铁律4(混沌边缘) — 内在探索驱动 | 无为之治 | 无心以百姓心为心 |
| Dario "递归自我改进" | 铁律10(简洁涌现) — 简单规则→复杂行为 | 无极而太极(从无中产生不对称) | 化身→受难→复活生命周期 |
| Cherny "验证驱动加速" | 铁律1(熵预算) — 验证=测量→熵减少 | 考异溯定律(多版本交叉) | 四毋(不绝对肯定) |
| Karpathy "Agentic Engineering" | 铁律9(Kuramoto弱同步) — 多Agent自组织 | 合纵涌现律 | 塔木德少数意见保留 |
| Dario "指数终点=最后冲刺" | 铁律8(极限环) — 周期≠崩溃 | 阴符经五贼 — 内在驱动外在 | Ghazali三阶段(确信) |
