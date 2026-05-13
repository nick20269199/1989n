# 技术侦查日报 2026-05-13

## 交易策略 (2 items)
### Strat-LLM: LLM股票交易对齐框架 — 来源: [arXiv 2605.06024](https://arxiv.org/html/2605.06024v1)
- **做什么**: 系统性测试LLM作为交易代理的三种模式——Free（自由推理）、Guided（带约束提示）、Strict（规则硬约束）。在A股和美股上做了全年前向测试。核心发现：推理型大模型在Free模式下表现最好，但规则硬约束会损害大模型表现（"Alignment Tax"）。
- **对我们的作用**: 直接应用于 `daily_task.py` 的信号聚合逻辑——当前对LLM输出是"Strict模式"（固定模板+硬止损），可能抑制了模型的市场感知。可实验在intraday_report中引入"Free→Guided"两级模式：初期让模型自由推理识别信号，输出后再套风控约束，而非先约束再推理。
- **风险评估**: arXiv论文（2026年5月），附有项目网站。论文级成熟度，但概念（Alignment Tax）可直接迁移到现有管道中，无需等待代码发布。

### AlphaLogics: 多Agent市场逻辑因子挖掘 — 来源: [arXiv 2603.20247](https://arxiv.org/html/2603.20247v1)
- **做什么**: 多Agent系统，从现有因子库（Alpha101/191/158/360）中逆向提取市场逻辑，然后迭代生成新因子。CSI 500年化超额16.72%（扣费后），S&P 500超额13.75%。核心创新：因子生成从"随机搜索"变为"逻辑驱动的定向生成"。
- **对我们的作用**: 因子挖掘方法论参考——当前技术扫描（tech_scan）基于固定指标集（VCP/MA/RSI等），AlphaLogics的"逻辑逆向提取"方法可用来发现哪些因子在当前周期阶段真正有效。可直接与StratEvo的遗传算法互补：StratEvo做权重优化，AlphaLogics做因子空间探索。
- **风险评估**: arXiv论文（2026年3月），AAAI投稿级别。无开源代码。方法论可直接借鉴到因子研究流程中，不依赖代码实现。

## 交易软件/工具 (1 item)
### finagg v2.0: 免费金融数据聚合器 — 来源: [GitHub](https://github.com/theOGognf/finagg)
- **做什么**: Python包，统一聚合FRED（美联储）、BEA（经济分析局）、SEC EDGAR的免费数据。支持SQL数据库存储、特征工程、缓存。v2.0.0（2026年3月发布），pip install finagg。
- **对我们的作用**: 填补宏观数据缺口——当前数据管道覆盖A股行情（Sina/Tencent）和美股指数（akshare），但缺乏美国宏观指标（利率/就业/GDP）。可接入 `data_source_router.py` 作为宏观数据通道，用于morning_brief的全球宏观部分和持仓背景判断（如通富微电的半导体周期定位）。
- **风险评估**: MIT协议，GitHub活跃更新（v2.0.0 Mar 2026），免费API key即可使用。成熟度4/5。集成成本低（纯Python + SQLite）。
