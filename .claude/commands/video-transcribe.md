---
name: video-transcribe
description: 视频内容提取 — 提取音频转文字(Whisper), 支持URL/本地文件, 自动提炼总结
allowed_tools: ["Bash", "Read"]
---

# /video-transcribe — 视频内容提取 & 提炼

## 用法

```
/video-transcribe <视频URL或路径>                    # 转录为带时间戳文本
/video-transcribe <视频> --refine                     # 转录后自动提炼总结
/video-transcribe <视频> --refine "主题"              # 按指定主题提炼
```

## 执行方式

### 第1步：转录

```bash
python ~/.claude/skills/ecc/video-transcribe/transcribe.py "${ARG1}"
```

> 注意：URL参数会包含 --refine 等标志，transcribe.py 会自动忽略不认识的参数。

如果视频是URL且下载失败，尝试添加 `--local` 使用本地模型：
```bash
python ~/.claude/skills/ecc/video-transcribe/transcribe.py "${ARG1}" --local
```

### 第2步：提炼 (仅当用户使用 --refine 时)

阅读转录文本后，根据内容类型自动选择提炼模式：

**财经/财报视频** → 提取：
- 核心数据（营收、利润、增速等具体数字）
- 业绩指引（管理层对未来展望）
- 风险点（提到的风险因素）
- 关键结论（对投资者的 actionable 建议）

**方法/教程视频** → 提取：
- 核心方法论（用编号列表）
- 每步具体操作（可执行的步骤）
- 案例/举例
- 一句话总结

**市场分析/交易视频** → 提取：
- 交易逻辑和催化剂
- 关键价位和时间窗口
- 风险收益比判断
- 具体操作建议

**通用视频** → 提取：
- 5-10个关键要点
- 一句话核心观点

### 第3步：输出

将提炼结果以结构化 markdown 输出，前面附上视频标签（类型、时长、来源）。
