---
name: vv-leida
description: 大V雷达 — 10位抖音投资大V内容监控，抓取→转录→分析→报告全流水线。三V互补框架(口罩哥宏观+魔法师资金+好运佛系供应链)交叉验证。
origin: 1989n
allowed-tools: [Bash, Read, Grep, Write, Edit]
---

# 大V雷达

监控10位抖音投资大V的新视频，批量转录后按三V互补框架分析。

## 命令

```bash
# 抓取所有关注大V的新视频
cd D:/1989n && python stock_analysis/vv_radar.py fetch

# 批量转录(按优先级: 行家5人→专项→其余)
cd D:/1989n && python stock_analysis/vv_transcribe.py --priority --limit 10

# 转录指定账号
cd D:/1989n && python stock_analysis/vv_transcribe.py --account <vv_id> --limit 5

# 查看大V列表和视频统计
cd D:/1989n && python stock_analysis/vv_radar.py list

# 查看某大V最新报告
cd D:/1989n && python stock_analysis/vv_radar.py report <vv_id>
```

## 三V互补框架

| 大V | 抖音号 | 角色 | 核心问题 | 跟法 |
|------|--------|------|---------|------|
| 口罩哥 | @yanbao60 | 信息层级架构师 | 什么信号驱动资金？ | 宏观方向参考 |
| 创业魔法师 | @guojame | 资金结构解码器 | 资金现在去哪了？ | A股具体操作参考 |
| 好运佛系 | @85164940078 | 供应链量化策略师 | 供应链钱往哪流？ | CPO/航天赛道 |

**三者必须交叉验证，不可偏废。**

## 全部10位大V

| 优先级 | 抖音号 | 昵称 | 评级 | 视频数 |
|--------|--------|------|------|--------|
| P0 | yanbao60 | 口罩哥研报60秒 | 行家 | 63 |
| P0 | Trader9 | Trader韭 | 行家 | 63 |
| P0 | Cyclequeen | 周期女王 | 行家 | 43 |
| P0 | HuDaMao.New | 胡大毛 | 行家 | 60 |
| P0 | guojame | 创业魔法师 | 行家(已修正) | 71 |
| P1 | 85164940078 | 好运佛系 | 专项赛道 | 64 |
| P1 | xiaositv | 小司频道 | 行家(宏观) | 62 |
| P2 | kaixin2091 | 凯心 | 中等/有保留 | 61 |
| — | Zihui518 | 子辉先生 | 水货 | 68 |
| — | 6052m9121 | 太阳李博良 | 水货 | 60 |

## 数据库

```bash
# 查看转录状态
py -c "
import sqlite3
conn = sqlite3.connect('D:/1989n/stock_data/vv_radar.db')
c = conn.cursor()
c.execute('''SELECT vv_id, COUNT(*) as cnt,
    SUM(CASE WHEN transcript_text IS NOT NULL THEN 1 ELSE 0 END) as done
    FROM vv_videos GROUP BY vv_id ORDER BY done ASC''')
for row in c.fetchall():
    print(f'{row[0]}: {row[2]}/{row[1]} 已转录')
conn.close()
"
```

## 易错点

- **登录态过期**: 转录报错 → 先跑 `python stock_analysis/vv_login.py` 重新登录抖音
- **CDN URL过期**: 视频URL几小时就失效 → `vv_transcribe.py` 已内置即时获取+下载，但一次性跑太多(>20个)中途可能过期
- **ffmpeg未安装**: `winget install ffmpeg` 或下载到 `D:\tools\ffmpeg\bin\ffmpeg.exe`
- **faster-whisper首运行**: 下载~1GB small模型，等几分钟
- **转录慢**: CPU模式下每个60秒视频约需2分钟，规划好时间

## 分析输出格式

分析任何大V内容时，必须标注：
1. **来源**: 哪个大V + 视频ID + 发布时间
2. **核心判断**: 该大V今天/本周的核心观点(1-2句话)
3. **与其他大V交叉**: 口罩哥的宏观判断是否支持魔法师的点位？好运佛系的赛道是否被魔法师的资金流向印证？
4. **对持仓的映射**: 该信息对当前6只持仓的具体影响
5. **置信度**: 基于大V评级 + 是否有其他大V印证 + 是否有具体数据
