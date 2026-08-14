# AstrBot AI 翻唱插件

这个插件把聊天平台收到的音频发给 Windows 上的 RVC 服务，按以下顺序处理：

> 本仓库包含 AstrBot 前端插件，需要配合提供 `/health`、`/models` 和 `/cover` 接口的 RVC AI 翻唱服务使用。

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
http://127.0.0.1:18888
```

如果 AstrBot 运行在 Docker 中，或 RVC 服务位于另一台主机，请在插件配置中把 `service_url` 修改为 AstrBot 容器能够访问的地址。

## 指令

- `/翻唱模型`：列出模型与索引状态；
- `/翻唱 胡桃 0`：使用“胡桃”模型，升降调为 0，并采用插件配置中的默认人声/伴奏音量；
- `/翻唱 胡桃 0 1.2 0.8`：本次翻唱使用 1.2 倍人声音量和 0.8 倍伴奏音量；允许范围为 0–2，0 表示静音；
- `/翻唱状态`：检查 RVC 服务连接和任务状态。

翻唱命令需附带音频，也可回复一条音频后发送。插件配置页的“默认翻唱人声音量倍率”和“默认伴奏音量倍率”会作为每次任务的默认值，命令中的两个可选音量参数只覆盖当前任务。

“将结果作为语音消息发送”默认关闭：关闭时发送 MP3 文件；开启时，插件会保留生成的 MP3 格式并交给消息适配器，不再经过 AstrBot 默认的 WAV 转换，以免 Base64 消息体积过大。消息平台仍可能再次转码或限制超长音频。

同一时刻只执行一个 GPU 任务；后续请求会排队，避免分离模型和 RVC 模型同时抢占显存。
