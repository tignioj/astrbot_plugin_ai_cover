"""AstrBot front end for the RVC AI-cover service."""

from __future__ import annotations

import asyncio
import base64
import json
import math
import time
import uuid
from pathlib import Path
from urllib.parse import unquote

import aiohttp
from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import File, Plain, Record, Reply
from astrbot.api.star import Context, Star, register
from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path


DEFAULT_FORM_VALUES = {
    "index_rate": 0.75,
    "rms_mix_rate": 0.25,
    "protect": 0.25,
}
DEFAULT_VOCAL_GAIN = 1.0
DEFAULT_INSTRUMENTAL_GAIN = 1.0
MAX_GAIN = 2.0


class OriginalFormatRecord(Record):
    """A Record that preserves the source audio instead of converting it to WAV."""

    @staticmethod
    def fromFileSystem(path: str | Path, **kwargs) -> "OriginalFormatRecord":
        file_path = Path(path).resolve(strict=False)
        return OriginalFormatRecord(
            file=file_path.as_uri(),
            path=str(file_path),
            **kwargs,
        )

    async def convert_to_base64(self) -> str:
        if not self.path:
            return await super().convert_to_base64()

        def encode_file() -> str:
            return base64.b64encode(Path(self.path).read_bytes()).decode("ascii")

        return await asyncio.to_thread(encode_file)


@register(
    "astrbot_plugin_ai_cover",
    "Codex",
    "调用局域网 RVC 服务完成分离、去混响、音色转换和混音",
    "1.1.2",
)
class AICoverPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.service_url = str(
            config.get("service_url", "http://192.168.100.143:18888")
        ).rstrip("/")
        self.api_token = str(config.get("api_token", ""))
        self.timeout_seconds = max(60, int(config.get("timeout_seconds", 3600)))
        self.data_dir = Path(get_astrbot_plugin_data_path()) / "astrbot_plugin_ai_cover"
        self.output_dir = self.data_dir / "outputs"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _headers(self) -> dict[str, str]:
        return {"X-AI-Cover-Token": self.api_token} if self.api_token else {}

    async def _get_json(self, path: str) -> dict:
        timeout = aiohttp.ClientTimeout(total=30)
        async with (
            aiohttp.ClientSession(timeout=timeout, trust_env=True) as session,
            session.get(
                f"{self.service_url}{path}", headers=self._headers()
            ) as response,
        ):
            payload = await response.text()
            if response.status != 200:
                raise RuntimeError(self._error_detail(payload, response.status))
            return json.loads(payload)

    @staticmethod
    def _error_detail(payload: str, status: int) -> str:
        try:
            detail = json.loads(payload).get("detail")
        except (json.JSONDecodeError, AttributeError):
            detail = payload.strip()
        return f"RVC 服务返回 HTTP {status}: {detail or '未知错误'}"

    @staticmethod
    def _reply_components(component: object) -> list[object]:
        if isinstance(component, Reply) and component.chain:
            return list(component.chain)
        return []

    async def _find_audio(self, event: AstrMessageEvent) -> tuple[str, str]:
        components = list(event.get_messages())
        for component in list(components):
            components.extend(self._reply_components(component))

        for component in components:
            if isinstance(component, Record):
                path = await component.convert_to_file_path()
                return path, Path(path).name or "record.wav"
            if isinstance(component, File):
                path = await component.get_file()
                if path:
                    return path, component.name or Path(path).name
        raise ValueError("请在同一条消息中附带音频文件，或回复一条音频后使用命令。")

    def _cleanup_outputs_sync(self) -> None:
        retention = max(1, int(self.config.get("output_retention_hours", 24)))
        deadline = time.time() - retention * 3600
        for path in self.output_dir.glob("ai_cover_*.mp3"):
            try:
                if path.stat().st_mtime < deadline:
                    path.unlink()
            except OSError:
                continue

    def _configured_gain(self, key: str, default: float) -> float:
        """Read a gain safely so configs created before v1.1 still work."""
        try:
            gain = float(self.config.get(key, default))
        except (TypeError, ValueError):
            return default
        return gain if math.isfinite(gain) and 0.0 <= gain <= MAX_GAIN else default

    def _resolve_gains(
        self,
        vocal_gain: float,
        instrumental_gain: float,
    ) -> tuple[float, float]:
        gains = {
            "人声音量": (
                vocal_gain,
                self._configured_gain("vocal_gain", DEFAULT_VOCAL_GAIN),
            ),
            "伴奏音量": (
                instrumental_gain,
                self._configured_gain(
                    "instrumental_gain", DEFAULT_INSTRUMENTAL_GAIN
                ),
            ),
        }
        resolved: list[float] = []
        for label, (requested, configured) in gains.items():
            gain = configured if requested == -1 else requested
            if not math.isfinite(gain) or not 0.0 <= gain <= MAX_GAIN:
                raise ValueError(f"{label}必须在 0 到 {MAX_GAIN:g} 之间。")
            resolved.append(gain)
        return resolved[0], resolved[1]

    async def _request_cover(
        self,
        audio_path: str,
        original_name: str,
        model: str,
        transpose: int,
        vocal_gain: float,
        instrumental_gain: float,
    ) -> tuple[Path, str, str]:
        timeout = aiohttp.ClientTimeout(
            total=self.timeout_seconds,
            connect=30,
            sock_read=self.timeout_seconds,
        )
        form = aiohttp.FormData()
        handle = await asyncio.to_thread(Path(audio_path).open, "rb")
        form.add_field(
            "audio",
            handle,
            filename=original_name,
            content_type="application/octet-stream",
        )
        form.add_field("model", model)
        form.add_field("transpose", str(transpose))
        for key, default in DEFAULT_FORM_VALUES.items():
            form.add_field(key, str(self.config.get(key, default)))
        form.add_field("vocal_gain", str(vocal_gain))
        form.add_field("instrumental_gain", str(instrumental_gain))

        output = self.output_dir / f"ai_cover_{uuid.uuid4().hex}.mp3"
        try:
            async with (
                aiohttp.ClientSession(timeout=timeout, trust_env=True) as session,
                session.post(
                    f"{self.service_url}/cover",
                    data=form,
                    headers=self._headers(),
                ) as response,
            ):
                if response.status != 200:
                    payload = await response.text()
                    raise RuntimeError(self._error_detail(payload, response.status))
                target = await asyncio.to_thread(output.open, "wb")
                try:
                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        await asyncio.to_thread(target.write, chunk)
                finally:
                    await asyncio.to_thread(target.close)
                if output.stat().st_size == 0:
                    raise RuntimeError("RVC 服务返回了空音频")
                actual_model = unquote(response.headers.get("X-AI-Cover-Model", model))
                index = unquote(response.headers.get("X-AI-Cover-Index", ""))
                return output, actual_model, index
        except Exception:
            output.unlink(missing_ok=True)
            raise
        finally:
            await asyncio.to_thread(handle.close)

    @filter.command("翻唱模型")
    async def cover_models(self, event: AstrMessageEvent):
        """列出当前 RVC 服务可用的翻唱模型。"""
        try:
            payload = await self._get_json("/models")
            rows = payload.get("models", [])
            if not rows:
                yield event.plain_result("RVC 服务中没有发现可用的 .pth 模型。")
                return
            lines = ["可用翻唱模型："]
            for row in rows:
                marker = "✓索引" if row.get("has_index") else "无索引"
                lines.append(f"- {row['name']}（{marker}）")
            lines.append(
                "\n用法：/翻唱 模型名 [升降调] [人声音量] [伴奏音量]，"
                "并附带或回复音频。"
            )
            yield event.plain_result("\n".join(lines))
        except Exception as error:  # noqa: BLE001 - command boundary reports failures
            yield event.plain_result(f"获取翻唱模型失败：{error}")

    @filter.command("翻唱")
    async def cover(
        self,
        event: AstrMessageEvent,
        model: str,
        transpose: int = 0,
        vocal_gain: float = -1,
        instrumental_gain: float = -1,
    ):
        """制作 AI 翻唱。示例：/翻唱 胡桃 0 1.1 0.8。"""
        if not -24 <= transpose <= 24:
            yield event.plain_result("升降调必须在 -24 到 24 之间。")
            return
        try:
            vocal_gain, instrumental_gain = self._resolve_gains(
                vocal_gain,
                instrumental_gain,
            )
        except ValueError as error:
            yield event.plain_result(str(error))
            return
        try:
            audio_path, original_name = await self._find_audio(event)
        except Exception as error:  # noqa: BLE001 - adapters may raise platform errors
            yield event.plain_result(str(error))
            return

        await event.send(
            event.plain_result(
                f"已接收音频，开始制作 AI 翻唱：{model}（升降调 {transpose}）。\n"
                f"人声音量 {vocal_gain:.2f} 倍，伴奏音量 {instrumental_gain:.2f} 倍。\n"
                "将依次执行人声分离、去混响、RVC 转换和混音，请耐心等待。"
            )
        )
        try:
            await asyncio.to_thread(self._cleanup_outputs_sync)
            output, actual_model, index = await self._request_cover(
                audio_path,
                original_name,
                model,
                transpose,
                vocal_gain,
                instrumental_gain,
            )
            summary = (
                f"AI 翻唱完成：{actual_model}，升降调 {transpose}，"
                f"人声 {vocal_gain:.2f} 倍，伴奏 {instrumental_gain:.2f} 倍"
            )
            if index:
                summary += f"，索引 {index}"
            if bool(self.config.get("send_as_record", False)):
                chain = [
                    Plain(summary),
                    OriginalFormatRecord.fromFileSystem(output),
                ]
            else:
                chain = [
                    Plain(summary),
                    File(name=f"AI翻唱-{actual_model}.mp3", file=str(output)),
                ]
            yield event.chain_result(chain)
        except asyncio.TimeoutError:
            yield event.plain_result(
                f"AI 翻唱超时（{self.timeout_seconds} 秒），请检查 RVC 服务日志。"
            )
        except Exception as error:  # noqa: BLE001 - keep one failed job from crashing plugin
            yield event.plain_result(f"AI 翻唱失败：{error}")

    @filter.command("翻唱状态")
    async def cover_status(self, event: AstrMessageEvent):
        """检查 RVC 服务状态。"""
        try:
            payload = await self._get_json("/health")
            state = "正在处理任务" if payload.get("busy") else "空闲"
            yield event.plain_result(
                f"RVC 服务正常：{state}，可用模型 {payload.get('models', 0)} 个。"
            )
        except Exception as error:  # noqa: BLE001 - status command reports connectivity errors
            yield event.plain_result(f"RVC 服务不可用：{error}")
