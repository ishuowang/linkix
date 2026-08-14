<div align="center">

# Linkix · 取链

一个面向公开单视频的多平台取链工具。粘贴分享文本或链接，Linkix 会识别平台、解析作品信息，并生成短时有效的下载地址。

[![CI](https://github.com/ishuowang/linkix/actions/workflows/ci.yml/badge.svg)](https://github.com/ishuowang/linkix/actions/workflows/ci.yml)
[![Website](https://img.shields.io/badge/在线访问-linkix.vercel.app-b84424?style=flat-square)](https://linkix.vercel.app)
[Telegram 机器人](https://t.me/vid_dld_bot)

### [打开 Linkix 在线版 →](https://linkix.vercel.app)

</div>

> [!IMPORTANT]
> 当前支持 **抖音、快手、小红书、B 站和微博的公开单视频**，TikTok 仍在计划中。平台风控会随时变化；私密、已删除、地区受限、会员或需要登录的作品会被拒绝。Linkix 不接收用户 cookies，也不绕过访问控制。

![Linkix 桌面端首页](docs/screenshots/linkix-home-desktop.png)

## 能做什么

Linkix 把浏览器、平台识别、解析器和媒体下载链路分开：

1. 在网页粘贴任一已支持平台的分享文本、短链或公开视频链接。
2. API 根据域名选择 Provider；Provider 负责输入边界，并将结果归一成同一份媒体模型。
3. 抖音和快手使用受限的专用解析器；小红书、B 站和微博使用 `yt-dlp` 内置 extractor。
4. 前端只收到不透明、短时有效的媒体 handle，不会得到上游签名地址。
5. 下载时由 API 再次校验目标、文件大小和响应内容，临时文件在响应结束后删除。
6. 最近八条解析历史只保存在当前浏览器的 `localStorage`。

内置的“填一条示例”使用演示数据，不会请求任何真实平台，也不会产生可下载文件。

### 平台状态

| 平台 | 状态 | 当前范围 |
| --- | --- | --- |
| 抖音 | ✅ 可用 | 公开单视频；支持分享文本、短链和完整链接 |
| 快手 | ✅ 可用 | 公开单视频；支持分享文本、短链和完整链接 |
| 小红书 | ✅ 可用 | 公开的视频笔记；不包含图文笔记 |
| B 站 | ✅ 可用 | 公开单视频；不包含会员、付费或登录后内容 |
| 微博 | ✅ 可用 | 公开单视频；不包含仅粉丝可见内容 |
| TikTok | 🧭 计划中 | Provider 尚未实现 |

可用表示解析链路已经接入，并不代表能够绕过平台登录、地区、会员或其他访问控制。请只处理你有权访问和保存的内容。

## 架构

```mermaid
flowchart LR
    U[用户] --> W[React / Vite Web]
    U -. 可选入口 .-> T[Telegram 机器人<br/>独立配套服务]
    W -->|POST /api/v1/resolve| A[FastAPI]
    A --> R{Provider Router}
    R --> DY[抖音专用 Provider]
    R --> KS[快手 INIT_STATE Provider]
    R --> Y[yt-dlp Provider]
    Y --> XHS[小红书]
    Y --> BL[B 站]
    Y --> WB[微博]
    DY & KS & Y -->|受限出站请求| D[平台公开页面 / CDN]
    BL --> F[ffmpeg 合并 DASH<br/>ffprobe 校验]
    A --> H[(进程内短期 handle)]
    W -->|GET /api/v1/media/:handle| A
    A -->|临时文件响应后删除| W
    W --> L[(浏览器 localStorage)]
```

Telegram 机器人目前独立运行，不包含在本仓库的 Web/API 启动命令中。入口：[打开 `@vid_dld_bot`](https://t.me/vid_dld_bot)。机器人二维码可通过 `npm run generate:assets` 重新生成。

## 本地运行

需要 Node.js 22、Python 3.11+（CI 使用 3.12）以及 Git。B 站的音视频分轨需要 `ffmpeg` 和 `ffprobe`；Docker 镜像会自动安装，本机运行 API 时需确保它们在 `PATH` 中。

### 1. 安装后端

```bash
git clone git@github.com:ishuowang/linkix.git
cd linkix

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e "api[dev]"
uvicorn linkix.app:app --host 127.0.0.1 --port 8010 --reload
```

健康检查：

```bash
curl http://127.0.0.1:8010/api/v1/health
```

### 2. 启动前端

另开一个终端：

```bash
cd linkix
npm ci
npm run dev
```

开发服务器会把 `/api` 代理到 `http://127.0.0.1:8010`。默认配置不需要 `.env`；需要修改限制或跨域来源时，可复制 `.env.example` 并在启动进程前导出其中变量。

### 3. 运行检查

```bash
npm test
npm run build
npm run test:sites

python -m ruff check api
python -m pytest api
```

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/v1/health` | 服务健康状态 |
| `POST` | `/api/v1/resolve` | 接收 `{"text":"分享文本或链接"}`，返回作品信息和短期 handle |
| `GET` | `/api/v1/media/{handle}` | 校验 handle 后下载媒体文件 |
| `GET` | `/api/docs` | FastAPI 交互文档 |

错误使用 `application/problem+json`，响应中会携带 `code` 和 `request_id`，便于定位问题。不同平台最终都会返回统一的 `provider`、`media` 和 `variants` 结构，前端无需理解各站点页面格式。

## 配置

常用配置位于 [.env.example](.env.example)：

| 变量 | 默认值 | 用途 |
| --- | --- | --- |
| `VITE_API_BASE_URL` | 空 | 前端构建时写入的 API 公网地址；同源部署保持为空 |
| `LINKIX_CORS_ORIGINS` | 本地 Vite 地址 | 允许访问 API 的完整 Origin，多个值用逗号分隔 |
| `LINKIX_MAX_MEDIA_BYTES` | `104857600` | 单个媒体文件最大字节数（默认 100 MiB） |
| `LINKIX_MEDIA_HANDLE_TTL_SECONDS` | `900` | 不透明下载 handle 的有效期 |
| `LINKIX_RESOLVE_LIMIT_PER_MINUTE` | `10` | 单个客户端每分钟解析次数 |
| `LINKIX_MAX_PARALLEL_DOWNLOADS` | `4` | 单进程并发下载上限 |
| `LINKIX_CONNECT_RETRIES` | `4` | 连接失败重试次数 |
| `LINKIX_BACKOFF_FACTOR` | `0.75` | 重试退避系数 |
| `LINKIX_DOUYIN_PROXY` | 空 | 抖音专用 HTTP(S) 代理；不要复用 Telegram 凭据 |
| `LINKIX_KUAISHOU_PROXY` | 空 | 快手专用代理；中国网络通常保持直连 |
| `LINKIX_YTDLP_PROXY` | 空 | 小红书和微博的可选 HTTP(S) 代理 |
| `LINKIX_BILIBILI_PROXY` | 空 | B 站专用代理；默认直连，避免海外节点常见的 `412` |
| `LINKIX_FFMPEG_PATH` | `ffmpeg` | B 站 DASH 音视频无损封装程序 |
| `LINKIX_FFPROBE_PATH` | `ffprobe` | 合并后 H.264 + AAC 流校验程序 |
| `LINKIX_ENABLE_PARSER_FALLBACK` | `false` | 是否允许把作品 ID 交给第三方备用解析器 |
| `LINKIX_PARSER_API` | `https://douyin.wtf/...` | 备用解析器地址 |

建议保持备用解析器关闭。启用前应自行评估隐私、稳定性和第三方服务条款。

默认 100 MiB 上限会优先保留可播放的高画质候选，并在实际下载超限时自动尝试更低清晰度。Compose 为 4 个完整下载生命周期配置了 1 GiB `/tmp`；B 站合流期间每个任务可能同时占用输入与输出两份空间。若修改 `LINKIX_MAX_MEDIA_BYTES` 或 `LINKIX_MAX_PARALLEL_DOWNLOADS`，请按 `并发数 × 2 × 媒体上限` 再留余量，同步调整 [compose.yaml](compose.yaml) 的 `tmpfs`。

## 安全边界

- 输入只接受 HTTP/HTTPS，且域名必须属于受支持平台的输入白名单；拒绝 URL 凭据、自定义端口和伪造后缀域名。
- 每次访问输入页和媒体前都会检查域名及 DNS 解析结果，拒绝私网、回环、链路本地等非公网地址，以降低 SSRF 风险。生产环境仍应配置出站防火墙。
- API 不向浏览器暴露平台 CDN 的签名 URL，只返回随机 handle；默认 15 分钟后失效。
- 媒体下载有平台 CDN 白名单、大小、并发、超时、重试和文件头校验；B 站分轨经 `ffmpeg` 封装并由 `ffprobe` 确认 H.264 + AAC，临时文件在响应结束后删除。
- 服务不把用户链接写入数据库；网页历史仅在本机浏览器中保存。日志、反向代理和监控仍需由部署者自行做脱敏。
- 限流器和 handle 存储目前都在进程内。请保持单 worker；多实例部署前需要改用 Redis 等共享存储。
- Linkix 只解析当前网络身份本来就能访问的公开内容，不提供权限绕过，也不提供 cookies 配置入口；遇到过期分享参数时请重新复制公开分享链接。
- 不要把 Telegram token、代理凭据、cookies、上游签名地址或用户提交的链接提交到 Git。

本项目只面向个人学习和对自己有权处理的内容。请遵守平台条款、当地法律和原创者授权，不要用于绕过访问控制或批量分发受版权保护的内容。

## 部署

### 前端：Vercel 或静态托管

前端是静态 Vite 应用：

- 构建命令：`npm ci && npm run build`
- 静态输出目录：`dist/client`
- 环境变量：`VITE_API_BASE_URL=https://你的-api-域名`
- Vercel 的构建设置已经固化在 [`vercel.json`](vercel.json)

如果前端和 API 共用一个域名，可让 Nginx/Caddy 把 `/api/*` 反向代理到 `127.0.0.1:8010`，并保持 `VITE_API_BASE_URL` 为空。仓库同时保留 Sites 所需的 worker 和打包检查。

### 后端：Docker Compose

```bash
cp .env.example .env
# 至少把 LINKIX_CORS_ORIGINS 改为实际前端 Origin
docker compose up -d --build api
curl http://127.0.0.1:8010/api/v1/health
```

Compose 只把 API 暴露到本机 `127.0.0.1:8010`，建议在前面放置 HTTPS 反向代理或 Cloudflare Tunnel。示例配置见：

- [compose.yaml](compose.yaml)
- [Caddyfile.example](infra/Caddyfile.example)
- [linkix-api.service](infra/linkix-api.service)

当前 handle 在内存中，因此滚动发布、进程重启或切换实例都会使既有下载地址立即失效，这是有意的安全取舍。

## 仓库结构

```text
linkix/
├── src/                   # React 前端、结果页和本地历史
├── api/                   # FastAPI、多平台 Provider、yt-dlp、安全校验和测试
├── public/assets/         # Telegram 二维码等静态资产
├── worker/                # 静态站点 SPA fallback
├── infra/                 # Caddy 与 systemd 示例
├── docs/reference/        # 产品设计参考图
├── docs/screenshots/      # 实现截图与设计 QA 对比图
└── .github/workflows/     # 前后端 CI
```

## 路线图

- 接入 TikTok Provider，并继续完善平台变更后的兼容性测试。
- 为限流和媒体 handle 增加可选共享存储。
- 完善 Telegram 机器人与 Web API 的统一部署和可观测性。
- 增加真实上游的隔离集成测试，不在 CI 中保存 cookies 或签名地址。

## License

[MIT](LICENSE)
