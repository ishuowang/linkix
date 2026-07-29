const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, code = "UNKNOWN_ERROR", status = 0) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

export async function resolveLink(text, { signal } = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE}/api/v1/resolve`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json, application/problem+json",
      },
      body: JSON.stringify({ text }),
      signal,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError("连接不到解析服务，请确认后端已经启动。", "NETWORK_ERROR");
  }

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new ApiError(
      payload.detail || "解析服务暂时不可用。",
      payload.code,
      response.status,
    );
  }
  return payload;
}

export function absoluteMediaUrl(path) {
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  const base = API_BASE || window.location.origin;
  return new URL(path, `${base}/`).toString();
}
