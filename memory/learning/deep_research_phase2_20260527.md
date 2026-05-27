# Deep Research Phase2 — 六缺口深度研究结论

> 日期: 2026-05-27
> 通道: DeepSeek Channel 2 (research, 独立配额)
> 中介声明: 结论由DeepSeek-chat基于训练数据生成，非实时web搜索。所有数值为模型推算，需实盘回测验证。

## 1. pipeline-shared-cache (absorbed)

**核心结论**: 集中式内存缓存(Python dict/lru_cache)是最佳方案。缓存键=`(数据源,代码,时间窗口,粒度)`四元组。混合TTL: 实时行情不缓存/日线当日有效/基本面到下次财报。A股全市场(5206只)缓存内存约16.4MB。预计减少80%的API调用和Token消耗(从26030次/周期降至5206次, 从520万Token降至104万)。

**落地路径**: 在`data_source_router`之后插入`SharedCache`层, 用`@lru_cache`装饰器包装各数据获取函数。无需引入Redis。

**不确定性**: Token节省比例取决于Expert间数据请求重叠度; 若各Expert请求不同股票池则效果打折。

## 2. pipeline-data-whitelist (absorbed)

**核心结论**: 五层纵深防御(L1采集层URL白名单→L2净化层字段类型/范围正则→L3白名单层JSON Schema→L4分析层统计一致性→L5风控层断路器)。核心是L3的`additionalProperties: false`策略。字段级约束: 价格(0.01-9999.99/精度2位)/涨跌幅(±10%主板±20%科创±5%ST)/成交量(0-10^12)/时间戳单调递增。

**落地路径**: YAML配置文件(`whitelist_config.yaml`)+预编译正则+DataValidator类。全量校验约5.2秒(5206只×10字段), 实时行情用采样校验(<100ms)。

**不确定性**: L5断路器阈值(N=10连续异常)需实盘调参; L4统计模型有误报率需标定。

## 3. knowledge-creator-discovery (insight_enriched)

**核心结论**: 完整闭环链路: 缺口清单→查询生成器(LLM自动生成关键词)→多源搜索器(并行B站/知乎/GitHub/抖音)→结果聚合器(URL去重+标题相似度)→质量过滤器(四层: 关键词黑名单/权威度/相关性/内容类型)→吸收决策器。相关性评分 = 关键词匹配40%+问答结构30%+实体覆盖20%+来源权威10%。

**落地路径**: 已有Pipeline流程图+SQL数据模型设计。搜索API: GitHub最稳定, B站/知乎需申请, 抖音有封号风险(低频率+代理IP)。每日配额20缺口×3查询×4源×10条=2400条/天。

**未达吸收的原因**: 多源搜索器需要各平台API SDK集成(大量工程工作); 质量评估模型(创作者权威度/填补度)需训练/校准; 抖音搜索的cookie+反爬方案需验证。

## 4. arch-multi-layer-security (absorbed)

**核心结论**: L1输入过滤(正则拦截危险指令+长度限制)→L2白名单(股票代码/操作类型/数值范围)→L3独立AI审查(交易纪律+认知偏差检测)→L4断路器(连续3次高风险/单日>50次/回撤>-5%触发)→L5人工兜底。每层误差处理: L1/L2/L4用Fail-Close(挂了就阻断), L3用Fail-Open→L5(挂了升人工)。

**落地路径**: 与Guardrails-AI结合, 用RAIL规范定义L2白名单, 用`guard.parse()`自动验证输出。L3用独立LLM审查Agent输出。额外延迟100-500ms可接受。

**不确定性**: L3认知偏差检测准确率需评估; L4阈值(连续3次/50次/-5%)需回测标定; 独立AI审查的False Positive率可能影响交易效率。

## 5. trading-rules-not-operationalized (absorbed)

**核心结论**: 规则形式化: 自然语言→JSON规则树(条件类型: CROSS_ABOVE/AND/VOLUME_THRESHOLD + 动作类型: SIGNAL/modify_score/veto)。规则引擎选型: `rule-engine`(轻量纯Python)或自研。放在Expert输出→Grader之前。冲突解决: 优先级+一票否决(veto:true)。

**落地路径**: 三步渐进: Step1让expert5_risk加载规则→Step2让Grader加载→Step3让Lead编排生命周期。规则JSON Schema已设计。`trading_rules.json`通过`rule_translator.py`(LLM翻译)转为机器可执行格式。

**不确定性**: JSON规则树表达能力有限, 复杂逻辑(循环/递归)无法表达; LLM翻译准确率需验证(自然语言→JSON的语义保真度)。

## 6. concept-position-sizing (absorbed)

**核心结论**: 推荐混合体系: 顶层iVX确定总仓位(低波80%/中波60%/高波30%)→中层ERC等风险贡献分配权重(单票上限20%)→底层ATR微调股数(风险比例1%)→取整到100股。500字伪代码已给出(含calculate_erc_weights/comprehensive_position_sizing)。

**数值示例(50万资金/iVX=22)**: 大港5200股(5.2万)/烽火4600股(6.9万)/生益2600股(5.2万)/信维2100股(5.25万)/三花2300股(6.9万)/创世纪1500股(5.25万), 总仓位34.7万(69.4%)。

**不确定性**: ERC依赖协方差矩阵估计(推荐120天滚动窗口); ATR参数(14日/风险比例1%)需回测优化; iVX阈值(20/30)是经验值需验证; 涨跌停导致协方差低估需Parkinson极差波动率修正。

## 行动建议

1. **立即吸收(5个)**: 创建对应提案→实施→验证 (pipeline-shared-cache, pipeline-data-whitelist, arch-multi-layer-security, trading-rules-not-operationalized, concept-position-sizing)
2. **第三轮搜索(1个)**: knowledge-creator-discovery需要补充各平台API SDK的具体接入方案和抖音反爬方案验证
3. **回测验证**: concept-position-sizing的混合仓位模型需要在历史数据上回测, 验证iVX阈值和单票上限参数

## 报告文件

- 报告: `stock_data/status/deep_research_report_phase2.json`
- 详情: `stock_data/status/deep_research_phase2_details.json`
- 脚本: `stock_analysis/deep_research_phase2.py`
