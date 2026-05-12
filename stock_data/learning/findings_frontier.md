# 进化阅读 — 前沿情报 2026-05-12

## 来源：Karpathy Autoresearch + ATLAS 交易系统

**Andrej Karpathy — Autoresearch (2026.03)**
- AI Agent自主运行ML实验过夜：读代码→形成假设→修改代码→跑5分钟实验→评估
- 18%的修改被保留(keep rate)，其余回退(git reset)
- 核心原语：**keep/revert** — 通过可衡量的结果驱动进化

**Chris Worsey (General Intelligence Capital) — ATLAS**
- 将Karpathy的autoresearch循环应用于金融市场
- 25个AI Agent分4层：宏观(10)/行业(7)/超级投资者(4)/决策(4)
- 用滚动Sharpe比率给Agent打分 → 重写最差者的prompt → 测试5个交易日 → keep或revert
- 173天实盘 **+22%收益**，基础设施成本 $20/月 Azure VM
- "最终prompt是进化的产物——由市场反馈塑造，而非人类直觉。"

### 核心洞察

**Prompt是最新可进化基质(evolvable substrate)**。不是代码，不是模型权重——而是自然语言描述的决策规则。进化循环四要素已全部就绪：
1. 变体生成(LLM改写prompt/规则)
2. 适应度评估(Sharpe比率/胜率/回报)
3. 选择(keep top X%)
4. 遗传(保留优秀prompt的片段用于下一轮)

### Agent映射 → 交易决策改进

**问题**: `stock_data/learning/rules.json` 已有凝练规则，但**没有适应度追踪**——无法知道哪些规则真正有效。

**改进方案 — 规则适应度系统**:

1. 在 `rules.json` 每条规则中增加字段：
   ```json
   {
     "condition": "...",
     "action": "...",
     "fitness": {
       "trigger_count": 0,
       "positive_outcomes": 0,
       "negative_outcomes": 0,
       "last_triggered": null,
       "win_rate": null
     }
   }
   ```

2. 规则触发时记录 outcome：24h后自动判断该决策是否正确
   - 止损规则触发后未出现更大亏损 → positive
   - 止损规则触发后错过反弹 → negative
   - 加仓规则触发后盈利 → positive
   - 加仓规则触发后继续下跌 → negative

3. 每周进化审计(已有 `weekly_audit_*` 框架)：
   - 规则按 win_rate 排序
   - bottom 20% → 标记为"待变异" → LLM重写条件或动作 → 替换旧规则
   - top 20% → 标记为"核心规则" → 在变异中受到保护

4. 这直接复用了 Karpathy 的 keep/revert 循环，但作用于**交易规则**而非代码

### 失效信号

- 规则触发次数 < 5 时的 win_rate 不可靠(小样本偏差)
- 市场体制切换后，历史 win_rate 可能反转(牛市止损规则在熊市是错的)
- 需要在 win_rate 旁标注**市场体制上下文**："该规则在启动→主升期 win=80%，在衰退期 win=30%"

### 关联

- [[findings_physics.md]] — 规则适应度系统可作为"质疑"维度的量化基础
- 同时持仓通富微电(+20.2%)和多氟多(-5.4%) → 同一套止损规则在不同持仓上表现迥异 → fitness系统需要按持仓/板块分层
