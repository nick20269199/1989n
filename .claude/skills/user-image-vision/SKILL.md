---
name: image-vision
description: >-
  看图理解。使用百炼 qwen-vl-max 分析图片内容。
  TRIGGER when: 用户发截图路径、问图片内容、"帮我看这张图"、"截图里有什么"、
  "识别图片"、"图片说了什么"、发 PNG/JPG 文件路径要求分析。
  DO NOT TRIGGER when: 用户只是提到图片但没有具体文件路径。
origin: user
allowed-tools: [Bash, Read]
---

# 图片分析

当用户需要分析图片内容时，调用 vision.py 工具。

## 使用方式

```bash
cd C:\Users\1989n\stock_analysis && python vision.py "<图片路径>" "<可选的提示词>"
```

## 工作流程

1. 确认图片路径存在
2. 运行 `python vision.py <路径>`
3. 将分析结果呈现给用户

## 默认提示词

如果不指定提示词，默认使用："请详细描述这张图片的内容，包括所有文字信息"

## 易错点（Gotchas）

- **API Key过期**: 百炼API Key可能过期，报错 `InvalidApiKey` 时需去[阿里云百炼控制台](https://bailian.console.aliyun.com/)重新生成
- **图片文件不存在**: 先确认文件路径存在再调用，否则Python会直接crash
- **大图片超时**: >10MB的图片可能超时，建议先用其他工具压缩
- **非图片格式**: vision.py只支持常见图片格式(png/jpg/jpeg/webp/gif)，PDF/视频会报错
- **qwen-vl-max限流**: 免费额度有QPM限制，连续调用可能被限流
- **中文OCR优于描述**: 如果只关心图片中的文字，提示词明确要求"提取所有文字"比"描述图片"更精准
