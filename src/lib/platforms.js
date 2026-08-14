export const PLATFORM_STATUS = [
  { id: "douyin", label: "抖音", status: "available" },
  { id: "kuaishou", label: "快手", status: "available" },
  { id: "xiaohongshu", label: "小红书", status: "available" },
  { id: "bilibili", label: "B站", status: "available" },
  { id: "weibo", label: "微博", status: "available" },
  { id: "tiktok", label: "TikTok", status: "planned" },
];

const PROVIDER_LABELS = Object.fromEntries(
  PLATFORM_STATUS.map(({ id, label }) => [id, label]),
);

export function providerLabel(provider) {
  if (!provider) return "未知平台";
  return PROVIDER_LABELS[provider.toLowerCase()] || provider;
}
