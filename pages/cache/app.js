const bridge = window.AstrBotPluginPage;
const entries = document.getElementById("entries");
const size = document.getElementById("size");
const message = document.getElementById("message");
const refreshButton = document.getElementById("refresh");
const clearButton = document.getElementById("clear");

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KiB", "MiB", "GiB", "TiB"];
  let value = bytes;
  let unit = -1;
  do {
    value /= 1024;
    unit += 1;
  } while (value >= 1024 && unit < units.length - 1);
  return `${value.toFixed(value >= 10 ? 1 : 2)} ${units[unit]}`;
}

function render(stats) {
  entries.textContent = Number.isInteger(stats.entries) ? stats.entries : "—";
  size.textContent = formatBytes(Number(stats.bytes));
}

function setBusy(busy) {
  refreshButton.disabled = busy;
  clearButton.disabled = busy;
}

async function refresh() {
  setBusy(true);
  message.textContent = "正在读取缓存…";
  try {
    const stats = await bridge.apiGet("cache");
    render(stats);
    message.textContent = "缓存状态已更新。";
  } catch (error) {
    message.textContent = `读取失败：${error.message}`;
  } finally {
    setBusy(false);
  }
}

async function clearCache() {
  if (!window.confirm("确定清理全部分离缓存吗？正在运行的任务不会被中断。")) return;
  setBusy(true);
  message.textContent = "正在等待服务并清理缓存…";
  try {
    const result = await bridge.apiPost("cache/clear", {});
    render(result.cache || { entries: 0, bytes: 0 });
    const removed = result.removed || {};
    message.textContent = `已清理 ${removed.entries || 0} 首，共 ${formatBytes(Number(removed.bytes || 0))}。`;
  } catch (error) {
    message.textContent = `清理失败：${error.message}`;
  } finally {
    setBusy(false);
  }
}

refreshButton.addEventListener("click", refresh);
clearButton.addEventListener("click", clearCache);
await bridge.ready();
await refresh();
