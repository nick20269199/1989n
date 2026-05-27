# Knowledge Graph Report

**Generated:** 2026-05-28
**Source:** D:/1989n (trading system)

## 1. Overview

| Metric | Value |
|--------|-------|
| Total Nodes | 4001 |
| Total Edges | 5626 |
| Communities | 650 |
| Hyperedges | 24 |
| From AST (code) | 0 extracted |
| From Semantic (docs) | 4732 extracted |

## 2. Node Type Distribution (graph)

| Type | Count |
|------|-------|
| unknown | 2461 |
| concept | 325 |
| trading_principle | 267 |
| book | 120 |
| CONCEPT | 115 |
| physics_concept | 64 |
| stock | 42 |
| PERSON | 35 |
| PRODUCT | 29 |
| reading | 25 |
| trading_signal | 24 |
| trading_concept | 22 |
| sector | 18 |
| STOCK | 17 |
| classic_text | 17 |
| rationale | 16 |
| EVENT | 15 |
| live_session | 15 |
| principle | 13 |
| news_event | 11 |

## 3. Edge Type Distribution

| Relation | Count |
|----------|-------|
| calls | 1754 |
| contains | 1690 |
| rationale_for | 873 |
| EXTRACTED | 135 |
| informs | 89 |
| method | 88 |
| introduces | 75 |
| trading_application_of | 44 |
| principle_of | 39 |
| informs_trading_principle | 39 |
| INFERRED | 38 |
| includes | 32 |
| derived_from | 29 |
| proposed_by | 27 |
| related_to | 23 |
| imports_from | 21 |
| complements | 21 |
| teaches | 19 |
| converges_with | 17 |
| includes_session | 15 |

## 4. Communities (top 30 by size)

### Community 0: unknown: 部门架构审查, 构建报告, dept_ops.py

- **Size:** 73 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 70, "audit": 1, "metrics": 1, "infrastructure": 1}
- **Central nodes:** intelligence_service.py (deg=15); OpsGate (deg=10); dept_preflight.py (deg=9)

### Community 1: unknown: Enum, .__init__(), nightly_plan.py

- **Size:** 69 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 69}
- **Central nodes:** trade_engine.py (deg=22); xy_stock_reader.py (deg=15); nightly_plan.py (deg=14)

### Community 2: unknown: bs_analyzer.py, bs_comprehensive_analysis.py, daily_checklist.py

- **Size:** 66 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 66}
- **Central nodes:** main() (deg=49); market_context.py (deg=8); bs_comprehensive_analysis.py (deg=8)

### Community 3: unknown: bridge_config.py, bridge_sender.py, feishu_sender.py

- **Size:** 65 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 65}
- **Central nodes:** test_feishu_router.py (deg=13); _resolve_chat_id() (deg=11); ppt_to_feishu.py (deg=10)

### Community 4: unknown: 冷热温差防范, 系统1与系统2双核处理器, dept_handlers.py

- **Size:** 61 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 59, "concept": 2}
- **Central nodes:** dept_handlers.py (deg=14); feishu_claude_agent.py (deg=13); douyin_extractor.py (deg=8)

### Community 5: unknown: cognitive_engine.py, Save grader result to file., save_grade_result()

- **Size:** 59 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 59}
- **Central nodes:** load_portfolio() (deg=16); lead.py (deg=11); run_single() (deg=10)

### Community 6: unknown: 策略耦合度 K 管理, ensure_dirs(), get_kline_df()

- **Size:** 55 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 54, "trading_principle": 1}
- **Central nodes:** store.py (deg=12); vision.py (deg=10); vv_transcribe.py (deg=9)

### Community 7: unknown: _build_flow_rank_map(), _build_rank_map(), _calc_rotation_speed()

- **Size:** 46 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 43, "hot_concept": 2, "sector_snapshot": 1}
- **Central nodes:** sector_tracker.py (deg=14); recon_daily.py (deg=10); generate_rotation_report() (deg=7)

### Community 8: unknown: 从 portfolio.json 读取持仓代码, _fallback_holdings(), _validate_code()

- **Size:** 45 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 45}
- **Central nodes:** _read() (deg=16); test_real_data.py (deg=16); test_portfolio_loader.py (deg=12)

### Community 9: unknown: l2_parser.py, 白名单校验：字段存在性 + 类型 + 范围。      Args:         data: 待校验的数据 (dict 或 list of dicts), validate_quotes()

- **Size:** 43 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 43}
- **Central nodes:** l2_parser.py (deg=30); parse_tickdata_file() (deg=8); parse_auction_summary() (deg=8)

### Community 10: unknown: call_auction.py, intraday_report.py, monitor_000062.py

- **Size:** 42 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 42}
- **Central nodes:** call_auction.py (deg=13); intraday_report.py (deg=12); safe_get() (deg=12)

### Community 11: unknown: bilibili_scraper.py, _api_get(), _compute_mixin_key()

- **Size:** 41 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 41}
- **Central nodes:** bilibili_scraper.py (deg=12); video_learn.py (deg=12); _wbi_sign() (deg=8)

### Community 12: trading_principle: Cohen-Tannoudji 量子力学 I/II, Dirac 量子力学原理, Griffiths 量子力学导论 (第2版)

- **Size:** 39 nodes
- **Dominant type:** trading_principle
- **Type distribution:** {"trading_principle": 19, "physics_concept": 14, "book": 6}
- **Central nodes:** concept_uncertainty_principle (deg=6); book_griffiths_qm (deg=6); concept_unitary_evolution (deg=4)

### Community 13: unknown: _dt_evening.py, news_scheduler.py, now_cst()

- **Size:** 39 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 39}
- **Central nodes:** news_scheduler.py (deg=20); run_intraday() (deg=11); now_cst() (deg=8)

### Community 14: unknown: 获取日K线 (本地缓存优先, 无缓存自动拉取并缓存)          Args:             code: 6位股票代码             d, check_stock(), fmt()

- **Size:** 38 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 38}
- **Central nodes:** schema_gate.py (deg=10); zt_hc.py (deg=10); import_gate.py (deg=9)

### Community 15: unknown: .set(), morning_brief.py, annotate_news_with_stocks()

- **Size:** 36 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 36}
- **Central nodes:** morning_brief.py (deg=16); generate_markdown_v2() (deg=10); annotate_news_with_stocks() (deg=7)

### Community 16: unknown: feishu_bridge.py, health_check.py, nightly_health_check.py

- **Size:** 36 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 36}
- **Central nodes:** health_check.py (deg=11); feishu_bridge.py (deg=9); send_alert() (deg=6)

### Community 17: unknown: analyze_holdings(), scan_vcp(), scan_watchlist_tech()

- **Size:** 36 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 36}
- **Central nodes:** stock_skill.py (deg=19); analyze_holdings() (deg=11); scan_watchlist_tech() (deg=9)

### Community 18: reading: 本金安全——交易的第一原则, 多空平衡——兼听则明, 复盘方法论——从过去中学习

- **Size:** 34 nodes
- **Dominant type:** reading
- **Type distribution:** {"reading": 24, "concept": 10}
- **Central nodes:** 法/系统——用制度管理行为 (deg=5); 顺势——顺应市场规律 (deg=5); 黄帝阴符经 交易穿透 (deg=5)

### Community 19: unknown: sel_lint.py, sel_prune.py, collect_files()

- **Size:** 34 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 34}
- **Central nodes:** sel_lint.py (deg=14); parse_frontmatter() (deg=7); read_file() (deg=6)

### Community 20: unknown: extract_assistant_action(), extract_user_intent(), 从 assistant 消息提取关键动作（工具调用 + 回复摘要）。

- **Size:** 32 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 32}
- **Central nodes:** test_conversation_miner.py (deg=18); extract_user_intent() (deg=11); extract_assistant_action() (deg=7)

### Community 21: unknown: feishu_doc.py, feishu_im_sender.py, add_blocks()

- **Size:** 31 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 31}
- **Central nodes:** feishu_doc.py (deg=12); create_from_markdown() (deg=8); _get_token() (deg=8)

### Community 22: rationale: Arthur 经济中的复杂性 — 经济复杂系统, Easley & Kleinberg 网络、众筹与市场, Haken 协同学 — 自组织同步与序参量

- **Size:** 30 nodes
- **Dominant type:** rationale
- **Type distribution:** {"rationale": 14, "book": 11, "kae_analysis": 3, "CONCEPT": 2}
- **Central nodes:** 序参量役使原理 — 慢变量决定快变量 (deg=6); concept_dissipative_structure_trend (deg=4); kae_concept_pcb_main_line (deg=4)

### Community 23: unknown: _build_review_notes(), _find_closes_at(), _judge_outcome()

- **Size:** 30 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 30}
- **Central nodes:** run_backtest() (deg=9); decision_backtest.py (deg=8); run_dreamer() (deg=6)

### Community 24: unknown: __init__.py, cmd_check(), cmd_indices()

- **Size:** 30 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 30}
- **Central nodes:** MarketPool (deg=16); get_quotes() (deg=10); cli.py (deg=8)

### Community 25: unknown: daily_task.py, _dt_closing.py, fetch_quotes()

- **Size:** 30 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 30}
- **Central nodes:** daily_task.py (deg=17); run_closing_review() (deg=10); fetch_quotes() (deg=10)

### Community 26: unknown: batch_transcribe.py, data_guard.py, git_auto_push.py

- **Size:** 29 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 29}
- **Central nodes:** run() (deg=13); data_guard.py (deg=6); task_sentinel.py (deg=6)

### Community 27: unknown: session_tracker.py, 从 DB 获取近期热门股票趋势，按频率排序。, end_session()

- **Size:** 29 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 29}
- **Central nodes:** test_session_stress.py (deg=11); init_session_tracker() (deg=9); get_active_session() (deg=9)

### Community 28: unknown: _abs_log(), _bat_closing_review(), _bat_lint()

- **Size:** 29 nodes
- **Dominant type:** unknown
- **Type distribution:** {"unknown": 29}
- **Central nodes:** generate_task_bats.py (deg=19); _cron_human() (deg=9); _abs_log() (deg=7)

### Community 29: CONCEPT: 传习录 王阳明, 道德经, 毛选论持久战

- **Size:** 27 nodes
- **Dominant type:** CONCEPT
- **Type distribution:** {"CONCEPT": 15, "PRODUCT": 8, "PERSON": 4}
- **Central nodes:** 庄子内篇 (deg=5); 道德经 (deg=4); 毛选矛盾论 (deg=3)

## 5. Cross-Community Connections

Total cross-community edges: 1065

| Source | Target | Relation | Source Community | Target Community |
|--------|--------|----------|-----------------|-----------------|
| AI | 小鹅通 (Xiaoe Tech) | EXTRACTED | PERSON: 人工意识, 生命3.0, AI | concept: 五阶段末期理论, 四阶段修整期理论, 仓位管理体系 |
| Claude Code Skills 系统 | 知识缺口: Agent自我进化/技能蒸馏 | INFERRED | PERSON: 人工意识, 生命3.0, AI | unknown: architecture_checklist.md, Epstein 生成社会科学, 生成解释 |
| 进化引擎 — 可进化基质 | 知识缺口: Agent自我进化/技能蒸馏 | INFERRED | LEARNING_CONCEPT: ATLAS 四层Agent架构, 进化引擎 — 可进化基质, 规则适应度追踪系统 | unknown: architecture_checklist.md, Epstein 生成社会科学, 生成解释 |
| stock_002156 | report_closing_20260507 | includes_holding | stock: 东方财富行情, 多氟多硬止损, 光力科技持有 | news_event: 财联社, 腾讯行情API, 苹果MacBook Neo产量目标提至1000万台 |
| stock_002156 | report_morning_20260508 | assesses_signal | stock: 东方财富行情, 多氟多硬止损, 光力科技持有 | news_event: R6六问自检框架, 工信部批复6G技术试验频率, Anthropic估值冲1.2万亿首次反超OpenAI |
| stock_002156 | recon_report_20260525 | RATES_STOCK | stock: 东方财富行情, 多氟多硬止损, 光力科技持有 | report: 大V雷达五轮分析, 大V定性判断, 大V雷达错误日志 |
| stock_000062 | report_morning_20260508 | assesses_signal | news_event: 财联社, 腾讯行情API, 苹果MacBook Neo产量目标提至1000万台 | news_event: R6六问自检框架, 工信部批复6G技术试验频率, Anthropic估值冲1.2万亿首次反超OpenAI |
| stock_000062 | report_holdings_20260508 | analyzes_stock | news_event: 财联社, 腾讯行情API, 苹果MacBook Neo产量目标提至1000万台 | stock: 东方财富行情, 多氟多硬止损, 光力科技持有 |
| stock_300480 | report_closing_20260507 | includes_holding | news_event: R6六问自检框架, 工信部批复6G技术试验频率, Anthropic估值冲1.2万亿首次反超OpenAI | news_event: 财联社, 腾讯行情API, 苹果MacBook Neo产量目标提至1000万台 |
| stock_300480 | report_holdings_20260508 | analyzes_stock | news_event: R6六问自检框架, 工信部批复6G技术试验频率, Anthropic估值冲1.2万亿首次反超OpenAI | stock: 东方财富行情, 多氟多硬止损, 光力科技持有 |
| stock_002407 | report_closing_20260507 | includes_holding | news_event: R6六问自检框架, 工信部批复6G技术试验频率, Anthropic估值冲1.2万亿首次反超OpenAI | news_event: 财联社, 腾讯行情API, 苹果MacBook Neo产量目标提至1000万台 |
| stock_002407 | report_holdings_20260508 | analyzes_stock | news_event: R6六问自检框架, 工信部批复6G技术试验频率, Anthropic估值冲1.2万亿首次反超OpenAI | stock: 东方财富行情, 多氟多硬止损, 光力科技持有 |
| report_closing_20260507 | decision_tongfu_take_profit | generates_decision | news_event: 财联社, 腾讯行情API, 苹果MacBook Neo产量目标提至1000万台 | stock: 东方财富行情, 多氟多硬止损, 光力科技持有 |
| report_holdings_20260508 | risk_matrix_20260508 | generates_risk_matrix | stock: 东方财富行情, 多氟多硬止损, 光力科技持有 | risk_item: 通富微电集中度风险, 风险矩阵 2026-05-08, 多氟多硬止损35元 |
| vv_radar_errors | vv_transcribe_pipeline | blocked_by | report: 大V雷达五轮分析, 大V定性判断, 大V雷达错误日志 | department: KAE代码审查报告, 一致性报告, 深度研究 DR20260526_01 |
| 2026-05-23 板块全景 | AI | contains_concept | unknown: _build_flow_rank_map(), _build_rank_map(), _calc_rotation_speed() | PERSON: 人工意识, 生命3.0, AI |
| 传习录 王阳明 | 知识缺口: Agent自我进化/技能蒸馏 | informs | trading_rule: Ladyman 理解复杂系统——复杂性的哲学基础, 耗散结构, 约束防止最大熵 | unknown: architecture_checklist.md, Epstein 生成社会科学, 生成解释 |
| 标度律 | 幂律分布 | related_to | concept: 贫穷的本质, 规模, 思考,快与慢 | concept: 混沌边缘, 催化网络, Stuart Kauffman |
| 热力学熵 | 耗散结构 | contradicts_superficially | concept: 非周期晶体, 时间之矢, Bell定理 | concept: 混沌边缘, 催化网络, Stuart Kauffman |
| 自组织临界性 | Kuramoto自发同步 | related_to | concept: 混沌边缘, 催化网络, Stuart Kauffman | concept: 幂律分布, 1/f 噪声, Per Bak |
| AI | PCB板块 | sub_sector_of | PERSON: 人工意识, 生命3.0, AI | concept: 三、研发创新, 8. 认知压缩 Level 3 — 跨品种模式匹配, 9. 自适应调度 |
| AI | 半导体/封测板块 | sub_sector_of | PERSON: 人工意识, 生命3.0, AI | concept: 五阶段末期理论, 四阶段修整期理论, 仓位管理体系 |
| AI | 心意/老大 (课程讲师) | taught_by | PERSON: 人工意识, 生命3.0, AI | concept: 五阶段末期理论, 四阶段修整期理论, 仓位管理体系 |
| AI | AI交易大师内部私享会 0526 | references | PERSON: 人工意识, 生命3.0, AI | concept: 五阶段末期理论, 四阶段修整期理论, 仓位管理体系 |
| physics_reading_cluster_branch_b_quantum | physics_concept_superposition | contains | trading_principle: 交叉对称性预警, 涨落编码响应, 涨落-耗散定理 | trading_principle: 决策即测量, 决策量子比特, 叠加态原理 |
| physics_reading_cluster_branch_b_quantum | physics_concept_entanglement | contains | trading_principle: 交叉对称性预警, 涨落编码响应, 涨落-耗散定理 | trading_principle: 分布式量子计算→多策略纠缠协调, 纠缠即证明, 量子纠缠 |
| physics_reading_cluster_branch_b_quantum | physics_concept_decoherence | contains | trading_principle: 交叉对称性预警, 涨落编码响应, 涨落-耗散定理 | trading_principle: 分支涌现时间, 环境选择, 退相干 |
| physics_reading_cluster_branch_b_quantum | physics_concept_renormalization | contains | trading_principle: 交叉对称性预警, 涨落编码响应, 涨落-耗散定理 | trading_principle: 正确标度→尺度选择, 普适类分类, 重整化群 |
| physics_reading_cluster_branch_b_quantum | physics_concept_criticality | contains | trading_principle: 交叉对称性预警, 涨落编码响应, 涨落-耗散定理 | trading_principle: 长程关联→临界点预警, 标度不变性→多框架共振, 临界现象 |
| physics_reading_cluster_branch_b_quantum | physics_concept_phase_transition | contains | trading_principle: 交叉对称性预警, 涨落编码响应, 涨落-耗散定理 | trading_principle: 拥挤交易预警(BEC), 弱信号配对(Cooper对), Tc临界点 |

## 6. Suggested Questions

- What is the structure of "unknown: 部门架构审查, 构建报告, dept_ops.py"?
- What is the structure of "unknown: Enum, .__init__(), nightly_plan.py"?
- What is the structure of "unknown: bs_analyzer.py, bs_comprehensive_analysis.py, daily_checklist.py"?
- What is the structure of "unknown: bridge_config.py, bridge_sender.py, feishu_sender.py"?
- What is the structure of "unknown: 冷热温差防范, 系统1与系统2双核处理器, dept_handlers.py"?
- How does PERSON: 人工意识, 生命3.0, AI connect to concept: 五阶段末期理论, 四阶段修整期理论, 仓位管理体系?
- Which communities are growing in influence?
- What are the highest-confidence relationships across domains?
- Are there isolated knowledge domains with few external connections?