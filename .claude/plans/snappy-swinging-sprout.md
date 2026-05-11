# 飞书 ↔ Claude 双向桥接服务

## 问题
当前只能通过飞书 Webhook 单向推送消息。需要在飞书群里发指令让 Claude 执行，结果返回群里。

## 架构方案：飞书 App + WebSocket 长连接

选择 WebSocket 而非 HTTP Webhook 的原因：你在家用 Windows 电脑，没有公网 IP。WebSocket 长连接是你主动连飞书服务器，**不需要公网地址、不需要 frp/ngrok 隧道**。

```
飞书群消息 → 飞书 WS 服务器 → feishu_bridge.py(常驻进程) → Claude API → 执行命令 → 飞书 API 回复
```

## 你需要做的（飞书开放平台配置，约 10 分钟）

1. 打开 [飞书开放平台](https://open.feishu.cn/app)，创建「企业自建应用」
2. 添加「机器人」能力
3. 权限管理里添加：`im:message`、`im:message:send_as_bot`、`im:chat:read`
4. 事件订阅 → 选择「使用长连接」→ 订阅 `im.message.receive_v1`
5. 发布并审批（你自己审批即可）
6. 把机器人加到你的股票群里
7. 拿到 App ID、App Secret，填到 `.env` 文件

## 我要创建的文件

| 文件 | 作用 |
|------|------|
| `bridge_config.py` | 读取 .env 配置，API 密钥管理 |
| `bridge_sender.py` | 通过飞书 App API 发送/回复消息（替代 webhook 发送） |
| `bridge_nlp.py` | 调用 Claude/DeepSeek API 把自然语言解析成股票命令 |
| `feishu_bridge.py` | 主服务进程：WebSocket 收消息 → 解析 → 执行 → 回复 |
| `start_bridge.bat` | Windows 看门狗脚本，崩溃自动重启 |
| `.env.example` | 配置模板 |

## 可靠性设计

- **4 层崩溃恢复**：单条消息异常不崩 → WebSocket 断线自动重连 → batch 脚本无限重启 → 系统计划任务每 5 分钟巡检
- **降级策略**：DeepSeek API 挂了自动切到关键词匹配，保证基本可用
- **日志**：滚动文件日志，方便排查问题
- **限流**：每分钟最多 10 条命令，防止刷屏

## 不修改的文件

`stock_skill.py`、`daily_task.py`、`feishu_sender.py`、`modules/`、`sources/` 全部不动。桥接服务是纯增量，不影响现有定时推送。

## 验证方式

1. 启动桥接后，在飞书群 @机器人 发送"行情"
2. 收到确认回复 → Claude 解析命令 → 执行 market 命令 → 返回实时行情到群里
3. 测试"贵州茅台K线"、"今日快讯"、"板块排行"等自然语言是否能正确解析
4. 杀掉进程 → 验证 watchdog 自动重启
5. 断网重连 → 验证 WebSocket 自动恢复
