import json, pathlib

data = {
  "entities": [
    {
      "id": "complexity_science_wolfram_ca",
      "name": "Wolfram 元胞自动机与复杂性",
      "file_type": "document",
      "source_path": "stock_data/reading_notes/2026-05-27_沃尔弗拉姆元胞自动机与复杂性_交易穿透.md",
      "labels": ["reading_note", "complexity_science", "cellular_automata", "trading_penetration"],
      "properties": {"author": "Stephen Wolfram", "date": "2026-05-27", "branch": "physics_branch_C", "core_insight": "局部规则+邻居交互+时间迭代=涌现全局模式；交易决策只需要局部信息"},
      "confidence": 1.0
    },
    {
      "id": "complexity_science_wolfram_nks",
      "name": "Wolfram 一种新科学",
      "file_type": "document",
      "source_path": "stock_data/reading_notes/2026-05-27_沃尔弗拉姆一种新科学_计算等价与简单规则_交易穿透.md",
      "labels": ["reading_note", "complexity_science", "computational_equivalence", "trading_penetration"],
      "properties": {"author": "Stephen Wolfram", "date": "2026-05-27", "core_insight": "计算等价性原理：市场与你同样聪明；简单规则+大量迭代=涌现复杂适应力"},
      "confidence": 1.0
    },
    {
      "id": "complexity_science_holland_emergence",
      "name": "Holland 涌现",
      "file_type": "document",
      "source_path": "stock_data/reading_notes/2026-05-27_霍兰德涌现_简单规则复杂行为_交易穿透.md",
      "labels": ["reading_note", "complexity_science", "emergence", "genetic_algorithm", "trading_penetration"],
      "properties": {"author": "John Holland", "date": "2026-05-27", "core_insight": "简单规则+大量交互+重复迭代=涌现；竞选-信用分配-繁殖-淘汰演化循环"},
      "confidence": 1.0
    },
    {
      "id": "complexity_science_holland_hidden_order",
      "name": "Holland 隐秩序",
      "file_type": "document",
      "source_path": "stock_data/reading_notes/2026-05-27_霍兰德隐秩序_适应性演化_交易穿透.md",
      "labels": ["reading_note", "complexity_science", "hidden_order", "adaptive_agent", "trading_penetration"],
      "properties": {"author": "John Holland", "date": "2026-05-27", "core_insight": "隐秩序是适应性主体局部交互涌现的副产品；桶队算法信用分配；内模型持续更新"},
      "confidence": 1.0
    },
    {
      "id": "complexity_science_miller_page_cas",
      "name": "Miller & Page 复杂适应性系统",
      "file_type": "document",
      "source_path": "stock_data/reading_notes/2026-05-27_米勒佩奇复杂适应性系统_CAS框架_交易穿透.md",
      "labels": ["reading_note", "complexity_science", "CAS", "trading_penetration"],
      "properties": {"author": "John Miller, Scott Page", "date": "2026-05-27", "core_insight": "CAS四要素；计算视角分析；异质性核心逻辑假设必须不同"},
      "confidence": 1.0
    },
    {
      "id": "complexity_science_mitchell",
      "name": "Mitchell 复杂性的边界",
      "file_type": "document",
      "source_path": "stock_data/reading_notes/2026-05-27_米切尔复杂性的边界_简单规则复杂行为_交易穿透.md",
      "labels": ["reading_note", "complexity_science", "GA", "trading_penetration"],
      "properties": {"author": "Melanie Mitchell", "date": "2026-05-27", "core_insight": "复杂性三标准；遗传算法进化策略；认知CAS管理"},
      "confidence": 1.0
    },
    {
      "id": "complexity_science_arthur",
      "name": "Arthur 复杂经济学",
      "file_type": "document",
      "source_path": "stock_data/reading_notes/2026-05-27_阿瑟复杂经济学_收益递增与非均衡_交易穿透.md",
      "labels": ["reading_note", "complex_economics", "increasing_returns", "non_equilibrium", "trading_penetration"],
      "properties": {"author": "Brian Arthur", "date": "2026-05-27", "core_insight": "收益递增导致锁定和非均衡；归纳推理替代演绎；市场永远在形成中"},
      "confidence": 1.0
    },
    {
      "id": "complexity_science_wiener",
      "name": "Wiener 控制论",
      "file_type": "document",
      "source_path": "stock_data/reading_notes/2026-05-27_维纳控制论_反馈控制_交易穿透.md",
      "labels": ["reading_note", "cybernetics", "feedback", "control_theory", "trading_penetration"],
      "properties": {"author": "Norbert Wiener", "date": "2026-05-27", "core_insight": "负反馈是控制核心；信息即负熵；控制优先于预测"},
      "confidence": 1.0
    },
    {
      "id": "complexity_science_bertalanffy",
      "name": "Bertalanffy 一般系统论",
      "file_type": "document",
      "source_path": "stock_data/reading_notes/2026-05-27_贝塔朗菲一般系统论_开放系统_交易穿透.md",
      "labels": ["reading_note", "general_systems_theory", "open_system", "trading_penetration"],
      "properties": {"author": "Ludwig von Bertalanffy", "date": "2026-05-27", "core_insight": "开放系统持续输入负熵；等结局性多路径可达；整体不等于部分之和"},
      "confidence": 1.0
    },
    {
      "id": "complexity_science_simon",
      "name": "Simon 人工科学",
      "file_type": "document",
      "source_path": "stock_data/reading_notes/2026-05-27_西蒙人工科学_层级结构_交易穿透.md",
      "labels": ["reading_note", "artificial_science", "bounded_rationality", "hierarchy", "trading_penetration"],
      "properties": {"author": "Herbert Simon", "date": "2026-05-27", "core_insight": "近可分解层级；有限理性满意原则；交易系统是设计品"},
      "confidence": 1.0
    },
    {
      "id": "complexity_science_ashby",
      "name": "Ashby 必要多样性定律",
      "file_type": "document",
      "source_path": "stock_data/reading_notes/2026-05-27_阿什比必要多样性定律_策略多样性_交易穿透.md",
      "labels": ["reading_note", "cybernetics", "requisite_variety", "trading_penetration"],
      "properties": {"author": "W. Ross Ashby", "date": "2026-05-27", "core_insight": "策略多样性必须匹配市场状态多样性；超稳定性；黑箱方法"},
      "confidence": 1.0
    },
    {
      "id": "complexity_science_meadows",
      "name": "Meadows 系统思考",
      "file_type": "document",
      "source_path": "stock_data/reading_notes/2026-05-27_梅多斯系统思考_杠杆点与系统动力学_交易穿透.md",
      "labels": ["reading_note", "systems_thinking", "leverage_points", "trading_penetration"],
      "properties": {"author": "Donella Meadows", "date": "2026-05-27", "core_insight": "12杠杆点从参数到范式；反馈回路决定系统行为；范式是最高杠杆"},
      "confidence": 1.0
    },
    {
      "id": "shiller_irrational_exuberance",
      "name": "非理性繁荣",
      "file_type": "document",
      "source_path": "stock_data/reading_notes/2026-05-25_非理性繁荣_交易穿透.md",
      "labels": ["reading_note", "behavioral_finance", "bubble", "shiller", "trading_penetration"],
      "properties": {"author": "Robert Shiller", "date": "2026-05-25", "core_insight": "反馈循环驱动泡沫；新纪元故事；泡沫六阶段识别框架"},
      "confidence": 1.0
    },
    {
      "id": "graham_intelligent_investor",
      "name": "聪明的投资者",
      "file_type": "document",
      "source_path": "stock_data/reading_notes/2026-05-25_聪明的投资者_交易穿透.md",
      "labels": ["reading_note", "value_investing", "graham", "margin_of_safety", "trading_penetration"],
      "properties": {"author": "Benjamin Graham", "date": "2026-05-25", "core_insight": "市场先生情绪报价；安全边际体系；防御型vs进取型"},
      "confidence": 1.0
    },
    {
      "id": "klarman_margin_of_safety",
      "name": "安全边际",
      "file_type": "document",
      "source_path": "stock_data/reading_notes/2026-05-25_安全边际_交易穿透.md",
      "labels": ["reading_note", "value_investing", "klarman", "risk_management", "trading_penetration"],
      "properties": {"author": "Seth Klarman", "date": "2026-05-25", "core_insight": "安全边际是对不确定性的谦卑；流动性折价；催化剂清单防价值陷阱"},
      "confidence": 1.0
    },
    {
      "id": "zeng_guofan_family_letters",
      "name": "曾国藩家书选",
      "file_type": "document",
      "source_path": "stock_data/reading_notes/2026-05-22_曾国藩家书选_交易穿透.md",
      "labels": ["reading_note", "chinese_civilization", "confucian", "self_cultivation", "trading_penetration"],
      "properties": {"author": "曾国藩", "date": "2026-05-22", "core_insight": "月盈则亏后收缩；花未全开月未圆留余地；傲为凶德惰为衰气；方寸为严师"},
      "confidence": 1.0
    },
    {
      "id": "daxue_zhongyong",
      "name": "大学中庸",
      "file_type": "document",
      "source_path": "stock_data/reading_notes/2026-05-23_大学中庸_交易穿透.md",
      "labels": ["reading_note", "chinese_civilization", "confucian", "zhongyong", "trading_penetration"],
      "properties": {"author": "曾子, 子思", "date": "2026-05-23", "core_insight": "知止而后有定；诚意毋自欺；慎独；居易以俟命"},
      "confidence": 1.0
    },
    {
      "id": "liuzu_tanjing",
      "name": "六祖坛经选",
      "file_type": "document",
      "source_path": "stock_data/reading_notes/2026-05-24_六祖坛经选_交易穿透.md",
      "labels": ["reading_note", "chinese_civilization", "buddhist", "zen", "trading_penetration"],
      "properties": {"author": "惠能", "date": "2026-05-24", "core_insight": "无念无相无住三无真谛；于相而离相；直心是道场"},
      "confidence": 1.0
    },
    {
      "id": "trading_concept_local_information",
      "name": "局部信息决策原则",
      "file_type": "rationale",
      "source_path": "stock_data/reading_notes/2026-05-27_沃尔弗拉姆元胞自动机与复杂性_交易穿透.md",
      "labels": ["trading_concept", "local_information", "decision_making"],
      "properties": {"derived_from": "wolfram_cellular_automata", "principle": "交易决策不需要全市场数据，应定义邻居范围，局部信息足够"},
      "confidence": 0.95
    },
    {
      "id": "trading_concept_emergence_system",
      "name": "涌现系统构建原则",
      "file_type": "rationale",
      "source_path": "stock_data/reading_notes/2026-05-27_霍兰德涌现_简单规则复杂行为_交易穿透.md",
      "labels": ["trading_concept", "emergence", "system_design"],
      "properties": {"derived_from": "holland_emergence", "principle": "3-5条简单规则+大量迭代=涌现适应性行为；竞选-信用分配-繁殖-淘汰循环"},
      "confidence": 0.95
    },
    {
      "id": "trading_concept_hidden_order",
      "name": "隐秩序利用原则",
      "file_type": "rationale",
      "source_path": "stock_data/reading_notes/2026-05-27_霍兰德隐秩序_适应性演化_交易穿透.md",
      "labels": ["trading_concept", "hidden_order", "market_structure"],
      "properties": {"derived_from": "holland_hidden_order", "principle": "识别当前涌现的秩序，利用它但设退出条件，秩序消失就放手"},
      "confidence": 0.85
    },
    {
      "id": "trading_concept_computational_equivalence",
      "name": "计算等价谦逊原则",
      "file_type": "rationale",
      "source_path": "stock_data/reading_notes/2026-05-27_沃尔弗拉姆一种新科学_计算等价与简单规则_交易穿透.md",
      "labels": ["trading_concept", "computational_equivalence", "humility"],
      "properties": {"derived_from": "wolfram_nks", "principle": "无法比市场聪明；优势来自策略与市场的不对齐而非更聪明"},
      "confidence": 0.95
    },
    {
      "id": "trading_concept_cas_four_elements",
      "name": "CAS四要素检查",
      "file_type": "rationale",
      "source_path": "stock_data/reading_notes/2026-05-27_米勒佩奇复杂适应性系统_CAS框架_交易穿透.md",
      "labels": ["trading_concept", "CAS", "system_check"],
      "properties": {"derived_from": "miller_page_cas", "principle": "检查系统：主体+交互+适应+涌现四要素缺一不可"},
      "confidence": 0.95
    },
    {
      "id": "trading_concept_requisite_variety",
      "name": "必要多样性覆盖原则",
      "file_type": "rationale",
      "source_path": "stock_data/reading_notes/2026-05-27_阿什比必要多样性定律_策略多样性_交易穿透.md",
      "labels": ["trading_concept", "requisite_variety", "strategy_diversity"],
      "properties": {"derived_from": "ashby_requisite_variety", "principle": "策略多样性必须匹配市场状态多样性，覆盖率缺口处必然亏损"},
      "confidence": 0.95
    },
    {
      "id": "trading_concept_negative_feedback",
      "name": "负反馈控制系统设计",
      "file_type": "rationale",
      "source_path": "stock_data/reading_notes/2026-05-27_维纳控制论_反馈控制_交易穿透.md",
      "labels": ["trading_concept", "feedback", "control_system"],
      "properties": {"derived_from": "wiener_cybernetics", "principle": "完整反馈回路四要素；控制优先于预测"},
      "confidence": 0.95
    },
    {
      "id": "trading_concept_bounded_rationality",
      "name": "有限理性满意原则",
      "file_type": "rationale",
      "source_path": "stock_data/reading_notes/2026-05-27_西蒙人工科学_层级结构_交易穿透.md",
      "labels": ["trading_concept", "bounded_rationality", "satisficing"],
      "properties": {"derived_from": "simon_artificial_science", "principle": "放弃最优交易幻觉；设最低可接受标准，第一个满足的就执行"},
      "confidence": 0.95
    },
    {
      "id": "trading_concept_leverage_points",
      "name": "杠杆点优先级原则",
      "file_type": "rationale",
      "source_path": "stock_data/reading_notes/2026-05-27_梅多斯系统思考_杠杆点与系统动力学_交易穿透.md",
      "labels": ["trading_concept", "leverage_points", "system_intervention"],
      "properties": {"derived_from": "meadows_systems_thinking", "principle": "从最强杠杆点(范式/目标/假设)开始审查再向下"},
      "confidence": 0.95
    },
    {
      "id": "trading_concept_open_system",
      "name": "开放系统负熵输入原则",
      "file_type": "rationale",
      "source_path": "stock_data/reading_notes/2026-05-27_贝塔朗菲一般系统论_开放系统_交易穿透.md",
      "labels": ["trading_concept", "open_system", "negentropy"],
      "properties": {"derived_from": "bertalanffy_general_systems", "principle": "每周检查是否有挑战假设的信息输入；越确定越危险"},
      "confidence": 0.95
    },
    {
      "id": "trading_concept_margin_of_safety",
      "name": "安全边际系统化",
      "file_type": "rationale",
      "source_path": "stock_data/reading_notes/2026-05-25_安全边际_交易穿透.md",
      "labels": ["trading_concept", "margin_of_safety", "risk_management"],
      "properties": {"derived_from": "klarman_margin_of_safety", "principle": "系统能承受的误差范围=安全边际；流动性折价"},
      "confidence": 1.0
    },
    {
      "id": "trading_concept_bubble_six_stages",
      "name": "泡沫六阶段识别",
      "file_type": "rationale",
      "source_path": "stock_data/reading_notes/2026-05-25_非理性繁荣_交易穿透.md",
      "labels": ["trading_concept", "bubble", "shiller", "market_cycle"],
      "properties": {"derived_from": "shiller_irrational_exuberance", "principle": "识别当前阶段：触发/上涨/反馈/新纪元/机构投降/崩盘"},
      "confidence": 1.0
    },
    {
      "id": "trading_concept_mr_market",
      "name": "市场先生与情绪管理",
      "file_type": "rationale",
      "source_path": "stock_data/reading_notes/2026-05-25_聪明的投资者_交易穿透.md",
      "labels": ["trading_concept", "mr_market", "emotion", "graham"],
      "properties": {"derived_from": "graham_intelligent_investor", "principle": "大跌时悲观=机会；大涨时乐观=风险；降低看盘频率"},
      "confidence": 1.0
    },
    {
      "id": "trading_concept_moderation_and_remainder",
      "name": "花未全开月未圆留余原则",
      "file_type": "rationale",
      "source_path": "stock_data/reading_notes/2026-05-22_曾国藩家书选_交易穿透.md",
      "labels": ["trading_concept", "moderation", "chinese_wisdom"],
      "properties": {"derived_from": "zeng_guofan_family_letters", "principle": "仓位不打满；防守即进攻；收啬而生机厚"},
      "confidence": 0.95
    },
    {
      "id": "trading_concept_shen_du",
      "name": "慎独作为交易纪律哲学基础",
      "file_type": "rationale",
      "source_path": "stock_data/reading_notes/2026-05-23_大学中庸_交易穿透.md",
      "labels": ["trading_concept", "self_discipline", "zhongyong"],
      "properties": {"derived_from": "daxue_zhongyong", "principle": "独自面对市场时无人监督仍遵守系统是纪律核心"},
      "confidence": 0.95
    },
    {
      "id": "trading_concept_wunian_wuxiang_wuzhu",
      "name": "三无交易真谛",
      "file_type": "rationale",
      "source_path": "stock_data/reading_notes/2026-05-24_六祖坛经选_交易穿透.md",
      "labels": ["trading_concept", "zen", "non_attachment"],
      "properties": {"derived_from": "liuzu_tanjing", "principle": "无念(不动心)/无相(不被表象牵)/无住(不执著结果)"},
      "confidence": 0.95
    },
    {
      "id": "trading_concept_inductive_reasoning",
      "name": "归纳推理循环",
      "file_type": "rationale",
      "source_path": "stock_data/reading_notes/2026-05-27_阿瑟复杂经济学_收益递增与非均衡_交易穿透.md",
      "labels": ["trading_concept", "inductive_reasoning", "arthur"],
      "properties": {"derived_from": "arthur_complex_economics", "principle": "用最近模式归纳行动更新；更新速度比精度重要"},
      "confidence": 0.95
    },
    {
      "id": "author_stephen_wolfram",
      "name": "Stephen Wolfram",
      "file_type": "rationale",
      "labels": ["author", "complexity_scientist", "cellular_automata"],
      "properties": {"field": "complexity science, cellular automata", "key_works": "A New Kind of Science, Cellular Automata", "key_insight": "计算等价性原理；规则110图灵完备；四类行为；计算不可约减"},
      "confidence": 1.0
    },
    {
      "id": "author_john_holland",
      "name": "John Holland",
      "file_type": "rationale",
      "labels": ["author", "complexity_scientist", "genetic_algorithm"],
      "properties": {"field": "complex adaptive systems, genetic algorithms", "key_works": "Emergence, Hidden Order", "key_insight": "GA发明者；涌现四条件；桶队算法信用分配；积木块假设"},
      "confidence": 1.0
    },
    {
      "id": "concept_emergence",
      "name": "涌现",
      "file_type": "rationale",
      "labels": ["concept", "complexity_science", "emergence"],
      "properties": {"definition": "简单元素按简单规则相互作用产生无法从单个元素预测的整体行为", "trading_application": "3-5条简单规则+大量迭代=涌现适应性"},
      "confidence": 1.0
    },
    {
      "id": "concept_computational_irreducibility",
      "name": "计算不可约减性",
      "file_type": "rationale",
      "labels": ["concept", "complexity_science", "prediction_limit"],
      "properties": {"definition": "某些过程无法加速预测，必须运行才知道结果", "trading_application": "30分钟不能决定则小仓位试"},
      "confidence": 1.0
    },
    {
      "id": "concept_bounded_rationality",
      "name": "有限理性",
      "file_type": "rationale",
      "labels": ["concept", "decision_theory", "simon"],
      "properties": {"definition": "信息有限、计算有限、时间有限，无法最优只能满意", "trading_application": "放弃最优幻觉，第一个满足标准就执行"},
      "confidence": 1.0
    },
    {
      "id": "concept_requisite_variety",
      "name": "必要多样性定律",
      "file_type": "rationale",
      "labels": ["concept", "cybernetics", "ashby"],
      "properties": {"definition": "控制系统的多样性至少等于被控系统的多样性才能控制", "trading_application": "策略多样性匹配市场状态多样性"},
      "confidence": 1.0
    },
    {
      "id": "concept_negative_feedback_loop",
      "name": "负反馈回路",
      "file_type": "rationale",
      "labels": ["concept", "cybernetics", "stability"],
      "properties": {"definition": "输出与目标比较，差值驱动修正使系统收敛", "trading_application": "自动止损/目标减仓/超阈值降仓"},
      "confidence": 1.0
    },
    {
      "id": "concept_building_blocks",
      "name": "积木块策略架构",
      "file_type": "rationale",
      "labels": ["concept", "strategy_design", "holland"],
      "properties": {"definition": "好策略由积木块(入场/出场/仓位/风控)组合而成", "trading_application": "维护积木块库，积木块本身也要进化"},
      "confidence": 1.0
    },
    {
      "id": "concept_nearly_decomposable_hierarchy",
      "name": "近可分解层级",
      "file_type": "rationale",
      "labels": ["concept", "system_design", "simon"],
      "properties": {"definition": "同层交互强、跨层交互弱的层级结构", "trading_application": "认知/策略/执行/反馈四层独立，各有时间尺度"},
      "confidence": 1.0
    },
    {
      "id": "concept_non_equilibrium_economics",
      "name": "非均衡市场观",
      "file_type": "rationale",
      "labels": ["concept", "economics", "arthur"],
      "properties": {"definition": "市场永远在形成中；价格是适应行为的涌现快照", "trading_application": "不预设回归，用适应模式会持续还是改变来交易"},
      "confidence": 1.0
    }
  ],
  "relationships": [
    {"source": "complexity_science_holland_emergence", "target": "author_john_holland", "type": "authored_by", "confidence": 1.0},
    {"source": "complexity_science_holland_hidden_order", "target": "author_john_holland", "type": "authored_by", "confidence": 1.0},
    {"source": "complexity_science_wolfram_ca", "target": "author_stephen_wolfram", "type": "authored_by", "confidence": 1.0},
    {"source": "complexity_science_wolfram_nks", "target": "author_stephen_wolfram", "type": "authored_by", "confidence": 1.0},
    {"source": "concept_emergence", "target": "author_john_holland", "type": "developed_by", "confidence": 0.95},
    {"source": "concept_emergence", "target": "complexity_science_holland_emergence", "type": "detailed_in", "confidence": 1.0},
    {"source": "concept_computational_irreducibility", "target": "author_stephen_wolfram", "type": "developed_by", "confidence": 1.0},
    {"source": "concept_bounded_rationality", "target": "complexity_science_simon", "type": "detailed_in", "confidence": 1.0},
    {"source": "concept_requisite_variety", "target": "complexity_science_ashby", "type": "detailed_in", "confidence": 1.0},
    {"source": "concept_negative_feedback_loop", "target": "complexity_science_wiener", "type": "detailed_in", "confidence": 1.0},
    {"source": "concept_building_blocks", "target": "author_john_holland", "type": "developed_by", "confidence": 0.95},
    {"source": "concept_nearly_decomposable_hierarchy", "target": "complexity_science_simon", "type": "detailed_in", "confidence": 1.0},
    {"source": "concept_non_equilibrium_economics", "target": "complexity_science_arthur", "type": "detailed_in", "confidence": 1.0},
    {"source": "trading_concept_local_information", "target": "complexity_science_wolfram_ca", "type": "derived_from", "confidence": 1.0},
    {"source": "trading_concept_emergence_system", "target": "complexity_science_holland_emergence", "type": "derived_from", "confidence": 1.0},
    {"source": "trading_concept_hidden_order", "target": "complexity_science_holland_hidden_order", "type": "derived_from", "confidence": 1.0},
    {"source": "trading_concept_computational_equivalence", "target": "complexity_science_wolfram_nks", "type": "derived_from", "confidence": 1.0},
    {"source": "trading_concept_cas_four_elements", "target": "complexity_science_miller_page_cas", "type": "derived_from", "confidence": 1.0},
    {"source": "trading_concept_requisite_variety", "target": "complexity_science_ashby", "type": "derived_from", "confidence": 1.0},
    {"source": "trading_concept_negative_feedback", "target": "complexity_science_wiener", "type": "derived_from", "confidence": 1.0},
    {"source": "trading_concept_bounded_rationality", "target": "complexity_science_simon", "type": "derived_from", "confidence": 1.0},
    {"source": "trading_concept_leverage_points", "target": "complexity_science_meadows", "type": "derived_from", "confidence": 1.0},
    {"source": "trading_concept_open_system", "target": "complexity_science_bertalanffy", "type": "derived_from", "confidence": 1.0},
    {"source": "trading_concept_bubble_six_stages", "target": "shiller_irrational_exuberance", "type": "derived_from", "confidence": 1.0},
    {"source": "trading_concept_margin_of_safety", "target": "klarman_margin_of_safety", "type": "derived_from", "confidence": 1.0},
    {"source": "trading_concept_mr_market", "target": "graham_intelligent_investor", "type": "derived_from", "confidence": 1.0},
    {"source": "trading_concept_moderation_and_remainder", "target": "zeng_guofan_family_letters", "type": "derived_from", "confidence": 1.0},
    {"source": "trading_concept_shen_du", "target": "daxue_zhongyong", "type": "derived_from", "confidence": 1.0},
    {"source": "trading_concept_wunian_wuxiang_wuzhu", "target": "liuzu_tanjing", "type": "derived_from", "confidence": 1.0},
    {"source": "trading_concept_inductive_reasoning", "target": "complexity_science_arthur", "type": "derived_from", "confidence": 1.0},
    {"source": "graham_intelligent_investor", "target": "klarman_margin_of_safety", "type": "influenced", "confidence": 0.85},
    {"source": "concept_emergence", "target": "concept_computational_irreducibility", "type": "related_to", "confidence": 0.75},
    {"source": "complexity_science_miller_page_cas", "target": "complexity_science_mitchell", "type": "builds_upon", "confidence": 0.85},
    {"source": "complexity_science_arthur", "target": "complexity_science_holland_emergence", "type": "influenced_by", "confidence": 0.85},
    {"source": "complexity_science_wiener", "target": "complexity_science_ashby", "type": "influenced", "confidence": 0.95},
    {"source": "complexity_science_wiener", "target": "complexity_science_bertalanffy", "type": "influenced", "confidence": 0.75},
    {"source": "trading_concept_emergence_system", "target": "trading_concept_cas_four_elements", "type": "extended_by", "confidence": 0.85}
  ],
  "hyperedges": [
    {
      "id": "hyperedge_complexity_trading_framework",
      "name": "复杂性科学交易框架",
      "type": "knowledge_cluster",
      "members": [
        "complexity_science_wolfram_ca", "complexity_science_holland_emergence",
        "complexity_science_holland_hidden_order", "complexity_science_miller_page_cas",
        "complexity_science_mitchell", "complexity_science_arthur",
        "complexity_science_wiener", "complexity_science_ashby",
        "complexity_science_meadows", "complexity_science_bertalanffy",
        "complexity_science_simon", "trading_concept_local_information",
        "trading_concept_emergence_system", "trading_concept_cas_four_elements",
        "trading_concept_requisite_variety", "trading_concept_negative_feedback",
        "trading_concept_bounded_rationality", "trading_concept_leverage_points",
        "trading_concept_open_system", "trading_concept_computational_equivalence"
      ],
      "properties": {
        "theme": "Complexity science applied to trading system design",
        "core_insight": "局部规则+反馈+多样性+层级+涌现=全局适应力",
        "practical_framework": "1.邻居范围 2.简单规则 3.多样性矩阵 4.反馈四要素 5.杠杆点 6.满意原则 7.负熵输入"
      },
      "confidence": 0.95
    },
    {
      "id": "hyperedge_eastern_wisdom_trading",
      "name": "东方智慧交易心法",
      "type": "knowledge_cluster",
      "members": [
        "zeng_guofan_family_letters", "daxue_zhongyong", "liuzu_tanjing",
        "trading_concept_moderation_and_remainder", "trading_concept_shen_du",
        "trading_concept_wunian_wuxiang_wuzhu"
      ],
      "properties": {
        "theme": "Chinese classical wisdom for trading psychology",
        "core_insight": "曾国藩仓位管理 + 大学中庸纪律哲学 + 坛经情绪管理 = 完整心法",
        "practical_framework": "花未全开 慎独 三无"
      },
      "confidence": 0.95
    },
    {
      "id": "hyperedge_value_investing_risk",
      "name": "价值投资与风险管理",
      "type": "knowledge_cluster",
      "members": [
        "graham_intelligent_investor", "klarman_margin_of_safety",
        "shiller_irrational_exuberance", "trading_concept_margin_of_safety",
        "trading_concept_bubble_six_stages", "trading_concept_mr_market"
      ],
      "properties": {
        "theme": "Value investing integrated with behavioral risk management",
        "core_insight": "市场先生+安全边际+流动性折价+泡沫阶段=完整安全边际体系",
        "practical_framework": "反向利用情绪 三层安全边际 泡沫定位 催化剂清单 现金管理"
      },
      "confidence": 0.95
    }
  ]
}

outpath = pathlib.Path("D:/1989n/graphify-out/.graphify_chunk_034.json")
outpath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Written: {len(data['entities'])} entities, {len(data['relationships'])} relationships, {len(data['hyperedges'])} hyperedges")
print(f"File size: {outpath.stat().st_size} bytes")
