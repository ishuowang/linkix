import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowBendDownLeft,
  Check,
  SpinnerGap,
} from "@phosphor-icons/react";
import { BotPanel } from "./components/BotPanel.jsx";
import { BrandHeader } from "./components/BrandHeader.jsx";
import { HistoryList } from "./features/HistoryList.jsx";
import { ResolveResult } from "./features/ResolveResult.jsx";
import { absoluteMediaUrl, resolveLink } from "./lib/api.js";
import {
  DEMO_HISTORY,
  DEMO_RESULT,
  DEMO_SOURCE,
  clearHistory,
  loadHistory,
  recordHistory,
} from "./lib/history.js";
import { PLATFORM_STATUS } from "./lib/platforms.js";

const EMPTY_STATE = {
  phase: "idle",
  result: null,
  error: "",
};

export function App() {
  const [input, setInput] = useState("");
  const [state, setState] = useState(EMPTY_STATE);
  const [history, setHistory] = useState(() => loadHistory());
  const [notice, setNotice] = useState("");
  const [clearArmed, setClearArmed] = useState(false);
  const inputRef = useRef(null);
  const abortRef = useRef(null);

  const hint = useMemo(() => {
    if (state.phase === "loading") return "正在展开短链并读取作品信息…";
    if (state.phase === "error") return state.error;
    if (state.phase === "success") return "解析完成，取链地址 15 分钟内有效";
    return "";
  }, [state]);

  useEffect(() => {
    if (!notice) return undefined;
    const timer = window.setTimeout(() => setNotice(""), 2400);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  function saveResolvedResult(result, sourceText, isDemo = false) {
    setState({ phase: "success", result, error: "" });
    const entry = {
      id: `${result.provider}:${result.media.provider_id}`,
      provider: result.provider,
      title: result.media.title,
      author: result.media.author.name,
      sourceUrl: result.media.source_url || sourceText,
      createdAt: new Date().toISOString(),
      isDemo,
    };
    setHistory(recordHistory(entry));
  }

  async function runResolve(value) {
    const normalized = value.trim();
    if (!normalized) {
      setState({
        phase: "error",
        result: null,
        error: "先粘贴一条受支持平台的分享链接。",
      });
      inputRef.current?.focus();
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setState({ phase: "loading", result: null, error: "" });

    if (normalized === DEMO_SOURCE) {
      await new Promise((resolve) => window.setTimeout(resolve, 360));
      if (!controller.signal.aborted) {
        saveResolvedResult(DEMO_RESULT, normalized, true);
      }
      return;
    }

    try {
      const result = await resolveLink(normalized, { signal: controller.signal });
      saveResolvedResult(result, normalized);
    } catch (error) {
      if (error.name === "AbortError") return;
      setState({
        phase: "error",
        result: null,
        error: error.message || "解析失败，请稍后重试。",
      });
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    runResolve(input);
  }

  async function handlePaste() {
    inputRef.current?.focus();
    try {
      const value = await navigator.clipboard.readText();
      if (value) {
        setInput(value.trim());
        setNotice("已从剪贴板粘贴");
      }
    } catch {
      setNotice("请在输入框中粘贴链接");
    }
  }

  function fillExample() {
    setInput(DEMO_SOURCE);
    setState(EMPTY_STATE);
    inputRef.current?.focus();
  }

  function revisit(entry) {
    const value = entry.isDemo ? DEMO_SOURCE : entry.sourceUrl;
    setInput(value);
    runResolve(value);
  }

  function handleClearHistory() {
    if (!clearArmed) {
      setClearArmed(true);
      window.setTimeout(() => setClearArmed(false), 3000);
      return;
    }
    clearHistory();
    setHistory([]);
    setClearArmed(false);
    setNotice("本地历史已清空");
  }

  async function copyMediaLink(path) {
    if (!path) {
      setNotice("示例数据没有真实下载地址");
      return;
    }
    const value = absoluteMediaUrl(path);
    try {
      await navigator.clipboard.writeText(value);
      setNotice("取链地址已复制");
    } catch {
      setNotice("复制失败，请打开下载后复制地址");
    }
  }

  return (
    <main className="app-shell">
      <div className="page-frame">
        <BrandHeader />

        <section className="hero" aria-labelledby="hero-title">
          <h1 id="hero-title">粘贴链接，拿走原片。</h1>
          <p className="platforms" aria-label="支持的平台">
            {PLATFORM_STATUS.map((platform) => (
              <span
                key={platform.id}
                className={`platform-${platform.status}`}
                data-status={platform.status}
                title={platform.status === "available" ? "已支持" : "计划中"}
              >
                {platform.label}
                {platform.status === "planned" && <em>计划中</em>}
              </span>
            ))}
          </p>

          <form className="resolver" onSubmit={handleSubmit}>
            <div
              className={`resolver-line ${state.phase === "loading" ? "is-loading" : ""}`}
            >
              <button
                className="paste-action"
                type="button"
                onClick={handlePaste}
                aria-label="从剪贴板粘贴"
              >
                粘贴
              </button>
              <input
                ref={inputRef}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                placeholder="粘贴任一已支持平台的分享链接…"
                aria-label="分享链接"
                autoComplete="off"
                spellCheck="false"
                disabled={state.phase === "loading"}
              />
              <button
                className="resolve-action"
                type="submit"
                disabled={state.phase === "loading"}
              >
                {state.phase === "loading" ? (
                  <>
                    解析中
                    <SpinnerGap size={16} weight="bold" className="spin" />
                  </>
                ) : (
                  <>
                    解析
                    <ArrowBendDownLeft size={15} weight="bold" />
                  </>
                )}
              </button>
            </div>

            <div
              className={`resolver-hint ${state.phase === "error" ? "is-error" : ""}`}
              aria-live="polite"
            >
              {hint || (
                <button type="button" onClick={fillExample}>
                  没有链接？填一条示例
                </button>
              )}
            </div>
          </form>

          {state.result && (
            <ResolveResult
              result={state.result}
              onCopy={copyMediaLink}
              isDemo={state.result.demo === true}
            />
          )}

          <HistoryList
            entries={history.length ? history : [DEMO_HISTORY]}
            clearArmed={clearArmed}
            onClear={handleClearHistory}
            onRevisit={revisit}
          />
        </section>

        <BotPanel />

        <footer className="site-footer">
          仅供个人学习备份 · 请尊重原创版权
        </footer>
      </div>

      <div className={`toast ${notice ? "is-visible" : ""}`} aria-live="polite">
        <Check size={15} weight="bold" />
        {notice}
      </div>
    </main>
  );
}
