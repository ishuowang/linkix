const STORAGE_KEY = "linkix.resolve-history.v1";
const MAX_HISTORY = 8;

export const DEMO_SOURCE = "https://v.douyin.com/linkix-demo/";

export const DEMO_RESULT = {
  demo: true,
  request_id: "linkix-demo",
  provider: "douyin",
  media: {
    provider_id: "demo-sunset",
    title: "海边日落延时摄影 · 等风也等你",
    author: { name: "等风也等你" },
    source_url: DEMO_SOURCE,
    variants: [
      {
        id: "demo",
        label: "原片 MP4",
        mime_type: "video/mp4",
        size_bytes: null,
        download_url: "",
        expires_at: "",
      },
    ],
  },
};

export const DEMO_HISTORY = {
  id: "demo:history",
  provider: "douyin",
  title: "海边日落延时摄影 · 等风也等你",
  author: "等风也等你",
  sourceUrl: DEMO_SOURCE,
  createdAt: new Date("2026-07-28T19:32:00+08:00").toISOString(),
  isDemo: true,
};

export function loadHistory() {
  try {
    const value = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "[]");
    return Array.isArray(value) ? value.slice(0, MAX_HISTORY) : [];
  } catch {
    return [];
  }
}

function saveHistory(entries) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  return entries;
}

export function recordHistory(entry) {
  const next = [
    entry,
    ...loadHistory().filter((item) => item.id !== entry.id),
  ].slice(0, MAX_HISTORY);
  return saveHistory(next);
}

export function clearHistory() {
  window.localStorage.removeItem(STORAGE_KEY);
}
