# AstrBot AI 翻唱插件

这个插件把聊天平台收到的音频发给 Windows 上的 RVC 服务，按以下顺序处理：

1. PyMSS `去伴奏`：得到人声和伴奏；
2. PyMSS `去混响`：得到干净人声；
3. RVC：使用 `assets/weights` 中指定的模型和 `logs` 中匹配的索引；
4. FFmpeg：把翻唱人声与原伴奏合成为 320 kbps MP3。

## 启动 RVC 服务

在 Windows 项目根目录运行：

```bat
start-ai-cover-service.bat
```

默认监听 `0.0.0.0:18888`，限制上传 200 MiB、音频 15 分钟。可通过以下环境变量覆盖：

- `AI_COVER_HOST`
- `AI_COVER_PORT`
- `AI_COVER_API_TOKEN`
- `AI_COVER_MAX_UPLOAD_MB`
- `AI_COVER_MAX_AUDIO_SECONDS`

## 安装 AstrBot 插件

把本目录复制到 AstrBot 的：

```text
data/plugins/astrbot_plugin_ai_cover
```

重启 AstrBot 或在插件管理页重载。插件默认访问：

```text
http://192.168.100.143:18888
```

若 Windows 地址改变，在 AstrBot 插件配置中修改 `service_url`。

## 指令

- `/翻唱模型`：列出模型与索引状态；
- `/翻唱 胡桃 0`：使用“胡桃”模型，升降调为 0；命令消息需附带音频，也可回复一条音频后发送；
- `/翻唱状态`：检查 RVC 服务连接和任务状态。

同一时刻只执行一个 GPU 任务；后续请求会排队，避免分离模型和 RVC 模型同时抢占显存。
