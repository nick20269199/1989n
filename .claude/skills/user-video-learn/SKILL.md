---
name: video-learn
description: >-
  视频学习。下载视频 → 提取字幕/语音转文字 → 分析内容。
  支持 B站、YouTube、抖音(需cookies)等。
  TRIGGER when: 用户发视频链接要求学习/分析/总结、"看视频"、"学习这个视频"、
  "分析视频内容"、"这个视频讲了什么"。
  DO NOT TRIGGER when: 用户只是分享链接但没有要求分析。
origin: user
allowed-tools: [Bash, Read]
---

# 视频学习

下载视频并提取文字内容进行分析。

## 使用方式

```bash
cd D:\1989n\stock_analysis && python video_learn.py "<视频URL>"
```

## 工作流程

1. 优先提取视频内置字幕（免费、准确）
2. 无字幕时用本地 faster-whisper 语音识别
3. 将文字内容分析后呈现给用户

## 支持的平台

- B站 (bilibili.com) — 无需登录
- YouTube (youtube.com) — 需代理
- 抖音 (douyin.com) — 需 cookies 文件

## 易错点（Gotchas）

- **ffmpeg未安装**: 音频转码(m4a→wav)依赖ffmpeg。若报错 `ffmpeg: command not found`，需先 `winget install ffmpeg`
- **faster-whisper模型首次下载**: 第一次运行会下载~1GB的small模型，需等待且需要稳定网络
- **B站WBI签名过期**: B站视频下载使用WBI签名，img_key/sub_key可能过期，报错412时需重新获取
- **长视频转录慢**: >30分钟的视频语音识别耗时长(5-15分钟)，耐心等待不要重复运行
- **中文识别精度**: faster-whisper small模型对中文口音/噪声环境准确率~85%，专业术语可能出错
- **别在转录过程中关闭终端**: 转录是CPU密集型，关终端会中断，需重新开始
- **batch_transcribe.py vs video_learn.py**: 批量转录用前者(只处理bilibili_audio/目录)，单个URL用后者
