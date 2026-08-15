const bridge = window.AstrBotPluginPage;
const entries = document.getElementById("entries");
const size = document.getElementById("size");
const message = document.getElementById("message");
const refreshButton = document.getElementById("refresh");
const clearButton = document.getElementById("clear");
const searchInput = document.getElementById("search");
const cacheList = document.getElementById("cache-list");
const empty = document.getElementById("empty");
const resultCount = document.getElementById("result-count");
const selectAll = document.getElementById("select-all");
const selectedCount = document.getElementById("selected-count");
const deleteSelectedButton = document.getElementById("delete-selected");

const state = {
  items: [],
  selected: new Set(),
  busy: false,
};

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

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function renderStats(stats) {
  entries.textContent = Number.isInteger(stats.entries) ? stats.entries : "—";
  size.textContent = formatBytes(Number(stats.bytes));
}

function filteredItems() {
  const query = searchInput.value.trim().toLocaleLowerCase();
  if (!query) return state.items;
  return state.items.filter((item) =>
    [item.song_name, item.source_filename].some((value) =>
      String(value || "").toLocaleLowerCase().includes(query),
    ),
  );
}

function updateSelectionControls(visibleItems) {
  const visibleIds = visibleItems.map((item) => item.id);
  const selectedVisible = visibleIds.filter((id) => state.selected.has(id)).length;
  selectAll.checked = visibleIds.length > 0 && selectedVisible === visibleIds.length;
  selectAll.indeterminate = selectedVisible > 0 && selectedVisible < visibleIds.length;
  selectAll.disabled = state.busy || visibleIds.length === 0;
  selectedCount.textContent = `已选 ${state.selected.size} 首`;
  deleteSelectedButton.disabled = state.busy || state.selected.size === 0;
}

function textElement(tag, className, text) {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = text;
  return element;
}

function renderList() {
  const validIds = new Set(state.items.map((item) => item.id));
  state.selected = new Set([...state.selected].filter((id) => validIds.has(id)));
  const visibleItems = filteredItems();
  cacheList.replaceChildren();
  empty.hidden = visibleItems.length !== 0;
  empty.textContent = state.items.length === 0 ? "暂无缓存。" : "没有匹配的歌曲。";
  resultCount.textContent = searchInput.value.trim()
    ? `找到 ${visibleItems.length} 首，共 ${state.items.length} 首`
    : `共 ${state.items.length} 首`;

  for (const item of visibleItems) {
    const row = document.createElement("article");
    row.className = "cache-row";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "row-check";
    checkbox.checked = state.selected.has(item.id);
    checkbox.disabled = state.busy;
    checkbox.setAttribute("aria-label", `选择 ${item.song_name}`);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) state.selected.add(item.id);
      else state.selected.delete(item.id);
      updateSelectionControls(filteredItems());
    });

    const identity = document.createElement("div");
    identity.className = "identity";
    identity.append(
      textElement("h3", "song-name", item.song_name || "未知歌曲"),
      textElement("p", "source-name", item.source_filename || "未知音频"),
    );

    const details = document.createElement("div");
    details.className = "row-details";
    details.append(
      textElement("span", "cache-size", formatBytes(Number(item.bytes))),
      textElement("span", "last-used", `最近使用 ${formatDate(item.last_accessed_at)}`),
    );

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "row-delete";
    removeButton.textContent = "清理";
    removeButton.disabled = state.busy;
    removeButton.addEventListener("click", () => deleteEntries([item.id], item.song_name));

    row.append(checkbox, identity, details, removeButton);
    cacheList.append(row);
  }
  updateSelectionControls(visibleItems);
}

function setBusy(busy) {
  state.busy = busy;
  refreshButton.disabled = busy;
  clearButton.disabled = busy;
  searchInput.disabled = busy;
  renderList();
}

function applyPayload(payload) {
  renderStats(payload.cache || { entries: 0, bytes: 0 });
  state.items = Array.isArray(payload.items) ? payload.items : [];
  renderList();
}

async function refresh() {
  setBusy(true);
  message.textContent = "正在读取缓存…";
  try {
    const payload = await bridge.apiGet("cache");
    applyPayload(payload);
    message.textContent = "缓存状态已更新。";
  } catch (error) {
    message.textContent = `读取失败：${error.message}`;
  } finally {
    setBusy(false);
  }
}

async function deleteEntries(ids, songName = "") {
  const label = ids.length === 1 ? `“${songName}”` : `所选 ${ids.length} 首歌曲`;
  if (!window.confirm(`确定清理${label}的分离缓存吗？`)) return;
  setBusy(true);
  message.textContent = "正在等待服务并清理所选缓存…";
  try {
    const result = await bridge.apiPost("cache/delete", { ids });
    state.selected.clear();
    applyPayload(result);
    const removed = result.removed || {};
    message.textContent = `已清理 ${removed.entries || 0} 首，共 ${formatBytes(Number(removed.bytes || 0))}。`;
  } catch (error) {
    message.textContent = `清理失败：${error.message}`;
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
    state.selected.clear();
    applyPayload({ cache: result.cache, items: [] });
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
deleteSelectedButton.addEventListener("click", () =>
  deleteEntries([...state.selected]),
);
searchInput.addEventListener("input", renderList);
selectAll.addEventListener("change", () => {
  for (const item of filteredItems()) {
    if (selectAll.checked) state.selected.add(item.id);
    else state.selected.delete(item.id);
  }
  renderList();
});
await bridge.ready();
await refresh();
