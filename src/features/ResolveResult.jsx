import {
  ArrowSquareOut,
  Copy,
  DownloadSimple,
} from "@phosphor-icons/react";
import { absoluteMediaUrl } from "../lib/api.js";

export function ResolveResult({ result, onCopy, isDemo }) {
  const variant = result.media.variants[0];
  const downloadUrl =
    !isDemo && variant?.download_url
      ? absoluteMediaUrl(variant.download_url)
      : "";

  return (
    <section className="resolve-result" aria-label="解析结果">
      <div className="result-kicker">
        <span className="status-dot" aria-hidden="true" />
        <span>{isDemo ? "抖音 · 示例结果" : "抖音 · 解析完成"}</span>
      </div>
      <div className="result-main">
        <div>
          <h2>{result.media.title}</h2>
          <p>
            {result.media.author.name}
            <span> · </span>
            {variant?.label || "原片 MP4"}
          </p>
        </div>
        <div className="result-actions">
          <button
            type="button"
            onClick={() => onCopy(variant?.download_url)}
            disabled={isDemo}
          >
            <Copy size={16} />
            复制取链
          </button>
          {downloadUrl ? (
            <a href={downloadUrl}>
              <DownloadSimple size={16} />
              下载原片
            </a>
          ) : (
            <span className="result-action-disabled">
              <DownloadSimple size={16} />
              示例不可下载
            </span>
          )}
          <a
            href={result.media.source_url}
            target="_blank"
            rel="noreferrer"
            aria-label="打开原作品"
          >
            <ArrowSquareOut size={16} />
          </a>
        </div>
      </div>
    </section>
  );
}
