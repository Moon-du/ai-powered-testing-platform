# AI Powered Test Engineering Platform

这是依据《AI 驱动的垂直产品测试工程平台开发总纲》实现的 P0 绿地工程。首个可验证切片聚焦 Electronic Pipette 的 Volume Setting 需求，并用确定性的 Fake LLM 跑通：

`Product Knowledge → Project Context → Requirement → Analysis → Risk → Scenario Review → Test Case → Traceability`

## 当前实现目标

- Product Type、版本化 Knowledge Pack 与 Project pin
- Project Context 和项目级访问隔离
- Requirement revision、Atomic Assertions 与下游 STALE 传播
- 四阶段强类型 AI 工作流与可替换 LLM Gateway
- Scenario 人工审批强 Gate
- 未定义 Expected Behavior 的显式阻断问题
- Knowledge Reference、Why Generated、Traceability 与 Coverage
- FastAPI/OpenAPI 后端和 Vue 3 工作台
- PostgreSQL/pgvector、Redis/Celery、MinIO 的 Docker 本地环境

真实模型、企业 OIDC、OCR、正式导出模板和完整 Knowledge Authoring Console 保留为可替换边界；首切片默认不依赖外部模型或企业凭据。

## 项目结构

```text
backend/    FastAPI 模块化单体、Celery worker、Alembic、pytest
frontend/   Vue 3、TypeScript、Vite、Ant Design Vue、Vitest、Playwright
docker-compose.yml
docker-compose.prod.yml
```

## Docker 启动

1. 复制 `.env.example` 为 `.env`，并为 `POSTGRES_PASSWORD`、`OBJECT_STORAGE_ACCESS_KEY`、`OBJECT_STORAGE_SECRET_KEY` 填入本机随机值。当前 Compose 会把 PostgreSQL 密码嵌入连接 URL，因此 `POSTGRES_PASSWORD` 请使用足够长的 URL-safe 字符（字母、数字、`_`、`-`），不要直接使用含 `@`、`:`、`/` 的原始密码。
2. 首次运行 `docker compose up --build`。默认 Compose 是开发模式：FastAPI 使用 `--reload`，Vue 使用 Vite HMR，Celery worker 在 Python 文件变化时自动重启。
3. 打开前端 `http://localhost:5173`；OpenAPI 位于 `http://localhost:8000/docs`。

日常修改 `backend/app` 或 `frontend` 下的源码后无需重新构建镜像，保存文件即可生效。修改 Python 依赖或 Dockerfile 后需要重新运行 `docker compose up --build`；修改前端依赖后重启前端容器，启动命令会按 lockfile 更新容器内依赖卷。

需要验证 Nginx 静态资源生产镜像时，使用独立生产配置：

```powershell
docker compose -f docker-compose.prod.yml up --build
```

开发模式使用显式的开发认证适配器；部署到非开发环境前必须关闭 `DEV_AUTH_ENABLED`、关闭 `SEED_DEMO`，并配置 OIDC/JWT 校验。
Compose 的所有宿主机端口仅绑定 `127.0.0.1`，开发身份头和本地基础设施不会暴露到局域网。

## 本地开发

后端和前端的独立安装、迁移、测试及启动命令分别记录在 `backend/README.md` 与 `frontend/README.md`。测试默认使用隔离的 SQLite 数据库和 Fake LLM，因此不需要真实模型、Redis 或对象存储。

当前完成度、验证结果与后续 P0 backlog 见 `docs/p0-implementation-status.md`；需要业务方确认但不阻塞首切片的事项见 `docs/open-decisions.md`。

## 产品默认值

- P0 首批仅 seed Electronic Pipette。
- LLM provider 默认为 `fake`，业务代码只依赖 Gateway contract。
- 检索先采用结构化筛选和确定性 seed；embedding/chunk 策略通过配置扩展。
- 导出采用平台自带列定义；接入现有 TMS 前再确认企业模板。
- 生产 SSO、角色映射、领域 seed 审核和扫描件 OCR 仍需产品/架构团队确认。
