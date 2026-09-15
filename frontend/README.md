# AI 测试工程平台前端

Vue 3 + TypeScript 的 P0 工作台，覆盖 Project、Requirement、四阶段 AI 工作流、Human Review Gate、Traceability 与 Coverage。前端按 `/api/v1` 契约调用 FastAPI；业务权限和工作流 Gate 最终以后端为准。

## 功能范围

- Project 列表与四步创建 Wizard：Product Type → Knowledge Pack → Project Info → Review。
- Project Overview：固定 Pack 版本、Product Knowledge 摘要与可编辑 Project Context Overlay。
- Requirement 列表与手工新增。
- Requirement Workspace：Requirement、Analysis、Risks、Scenarios、Test Cases、Traceability 六个 Tabs。
- 异步 AI Run 轮询、Review/Reject/Regenerate、Why Generated、Knowledge References。
- 所有可变更动作以 `GET /requirements/{id}/workflow` 的 `available_actions` 为准；混合批次可选择单项审阅，需澄清用例不会阻塞同批次的执行就绪项。
- Requirement Gap、Clarification Required、STALE/SUPERSEDED 等显式信号。
- Assertion/Risk/Scenario/Test Case Coverage 与质量缺口。

## 本地运行

需要 Node.js 24+ 与 pnpm 11。复制 `.env.example` 为 `.env.local` 并按本地后端身份调整，然后运行：

```bash
pnpm install --frozen-lockfile
pnpm --dir frontend dev
```

Vite 将 `/api` 代理到 `http://localhost:8000`。也可通过 `VITE_API_BASE_URL` 指向其他 `/api/v1` 地址。

## 开发身份与 Token

开发模式默认只在请求时发送 `X-User-Id` 与 `X-Tenant-Id`，界面角色与后端统一为 `OWNER`、`EDITOR`、`REVIEWER`、`VIEWER`，默认 `OWNER`。`VITE_DEV_ACTOR_ROLE` 只用于界面显示，不作为后端授权依据。生产 OIDC/OAuth2 接入时，通过 auth store 注入 Bearer access token。

auth store、开发身份和 access token 均为内存态；代码不会写入 `localStorage`、`sessionStorage` 或其他浏览器持久化存储。正式身份授权必须由后端 membership 与 Project Access 校验完成。

## 质量检查

```bash
pnpm --dir frontend typecheck
pnpm --dir frontend build
pnpm --dir frontend test:unit
pnpm --dir frontend test:e2e
```

Vitest 覆盖工作流 Gate、部分审批筛选、结构化用例字段、active asset 解析、开发角色和状态信号。Playwright 覆盖项目创建 smoke，以及包含 `DEFINED` 与 `CLARIFICATION_REQUIRED` 的完整工作流：Scenario 部分审批和 Test Case 执行就绪子集审批都会校验实际请求 ID。

## Docker

`Dockerfile` 构建静态站点并由 Nginx 服务。默认 Nginx 把 `/api/` 代理到 Compose 服务名 `backend:8000`，SPA 路由回退到 `index.html`。

```bash
docker build -f frontend/Dockerfile -t ai-testing-frontend .
docker run --rm -p 8080:80 ai-testing-frontend
```

镜像构建使用仓库根目录的 `pnpm-lock.yaml` 和 `--frozen-lockfile`，以保证依赖可复现。
