import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App.jsx";
import { DEMO_SOURCE } from "./lib/history.js";


const API_RESULT = {
  request_id: "req-1",
  provider: "douyin",
  media: {
    provider_id: "7345678901234567890",
    title: "真实解析结果",
    author: { name: "测试作者" },
    source_url: "https://www.douyin.com/video/7345678901234567890",
    variants: [
      {
        id: "opaque",
        label: "原片 MP4",
        mime_type: "video/mp4",
        size_bytes: 123,
        download_url: "/api/v1/media/opaque",
        expires_at: "2026-07-29T12:00:00+00:00",
      },
    ],
  },
};


describe("Linkix resolver", () => {
  beforeEach(() => {
    window.localStorage.clear();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        readText: vi.fn(),
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("fills and resolves the built-in design example", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "没有链接？填一条示例" }));
    expect(screen.getByRole("textbox", { name: "分享链接" })).toHaveValue(DEMO_SOURCE);
    await user.click(screen.getByRole("button", { name: /解析/ }));

    expect(await screen.findByText("抖音 · 示例结果")).toBeInTheDocument();
    expect(screen.getAllByText("海边日落延时摄影 · 等风也等你")).not.toHaveLength(0);
  });

  it("submits a real link to the API and shows the result", async () => {
    vi.spyOn(window, "fetch").mockResolvedValue(
      new Response(JSON.stringify(API_RESULT), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const user = userEvent.setup();
    render(<App />);

    await user.type(
      screen.getByRole("textbox", { name: "分享链接" }),
      "https://v.douyin.com/abc123/",
    );
    await user.click(screen.getByRole("button", { name: /解析/ }));

    expect(await screen.findAllByText("真实解析结果")).not.toHaveLength(0);
    expect(window.fetch).toHaveBeenCalledWith(
      "/api/v1/resolve",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("keeps the input and shows a safe API error", async () => {
    vi.spyOn(window, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          code: "PARSE_FAILED",
          detail: "这个作品暂时无法解析。",
        }),
        {
          status: 502,
          headers: { "Content-Type": "application/problem+json" },
        },
      ),
    );
    const user = userEvent.setup();
    render(<App />);
    const input = screen.getByRole("textbox", { name: "分享链接" });

    await user.type(input, "https://v.douyin.com/broken/");
    await user.click(screen.getByRole("button", { name: /解析/ }));

    expect(await screen.findByText("这个作品暂时无法解析。")).toBeInTheDocument();
    expect(input).toHaveValue("https://v.douyin.com/broken/");
  });
});
