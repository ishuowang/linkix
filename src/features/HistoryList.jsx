import { providerLabel } from "../lib/platforms.js";

function displayTime(value) {
  try {
    return new Intl.DateTimeFormat("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(value));
  } catch {
    return "--:--";
  }
}

export function HistoryList({
  entries,
  clearArmed,
  onClear,
  onRevisit,
}) {
  return (
    <section className="history" aria-labelledby="history-title">
      <div className="history-head">
        <h2 id="history-title">解析历史 · 仅保存在本地</h2>
        <button type="button" onClick={onClear}>
          {clearArmed ? "再按一次" : "清空"}
        </button>
      </div>

      <div className="history-list">
        {entries.map((entry) => (
          <article className="history-row" key={entry.id}>
            <span className="status-dot" aria-hidden="true" />
            <span className="history-provider">
              {providerLabel(entry.provider)}
            </span>
            <strong title={entry.title}>{entry.title}</strong>
            <time dateTime={entry.createdAt}>{displayTime(entry.createdAt)}</time>
            <button type="button" onClick={() => onRevisit(entry)}>
              再次查看
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}
