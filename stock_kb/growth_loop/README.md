# Growth Loop — 每日进化阅读

两个阅读池轮换，产出驱动交易决策改进。

## 目录结构

```
growth_loop/
├── README.md                    # 本文件
├── pool1_physics_econ/          # 池1：物理/经济学深度阅读
│   └── findings.md              # 洞察产出
├── pool2_frontier/              # 池2：AI前沿情报
│   └── findings.md              # 洞察产出
├── synthesis/                   # 跨域连接
│   └── connections.md           # 跨池模式识别
└── queue/                       # 阅读队列
    ├── pool1_queue.md           # 池1待读清单
    └── pool2_queue.md           # 池2待读清单
```

## 轮换规则

- 单日：池1（物理/经济学）— 选1章深读 → 1洞察 → Agent映射
- 双日：池2（前沿情报）— Karpathy/Ilya/arXiv → 1洞察 → Agent映射
- 每日产出写入对应 findings.md
- 跨池连接标注在 synthesis/connections.md

## 写入约束（硬）

**洞察必须能落地到交易决策改进，否则不写入。**

落地标准（满足任一条即可写入）：
1. 能改变某个分析脚本的算法/参数
2. 能修正某个决策规则（仓位/择时/选股）
3. 能优化数据管道的采集/处理逻辑
4. 能改进复盘模板的检查项
5. 能增强对抗审查的攻击维度

不满足以上任何一条 → 不写入。宁可空一天，不写废话。

## 格式规范

每条记录包含：
- 日期、来源
- 1个核心洞察（≤3句话）
- Agent映射：改哪个文件/哪个函数/哪个参数
- 落地状态：planned / implemented / verified

## 与现有系统集成

- 每周六 `weekly-audit` 读取本周 findings.md 做模式识别
- 每日 `daily-load` 可加载最近 findings 到上下文
- 洞察落地后更新对应脚本的 CLAUDE.md 注释
