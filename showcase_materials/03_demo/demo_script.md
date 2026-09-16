# 本地 Demo 操作与中文讲解脚本

## Demo 原则

- 不在面试现场调用付费 Provider；
- 使用本地 Docker 和 deterministic journey 证明架构；
- Lesson/Exam/PPT 质量使用预生成 Artifact 截图或文件展示；
- 不把 deterministic 输出说成真实模型质量；
- 现场失败时优先展示已录屏和截图，不临时改环境。

## 准备工作

1. 克隆 `course-rag` 和 `course-pilot` 到同级目录。
2. 从 CoursePilot 仓库启动作品集 Compose。
3. 确认：
   - CoursePilot `http://localhost:8000/docs`
   - CourseRAG `http://localhost:8001/docs`
4. 准备三个预生成文件：Lesson DOCX、Exam 四文件、PPTX + 页面 PNG。

## 3 分钟版本

### 0:00–0:30 背景

讲解：

> 这是一个高校教师备课 Agent。它最初是单体 Demo，我把知识服务拆成 CourseRAG，把工作流
> 拆成 CoursePilot。今天的演示不调用付费模型，重点展示两个服务的边界、任务执行和可追溯性。

### 0:30–1:00 服务边界

打开两个 Swagger，展示独立服务和 Health Endpoint。

讲解：

> CoursePilot 不直接访问向量库或 CourseRAG 数据表，只通过版本化 HTTP Contract 获取 Context
> 和 Evidence。两个服务共享 PostgreSQL 实例，但分别拥有 `coursepilot` 和 `courserag` Schema。

### 1:00–2:00 执行 Journey

在 CoursePilot 容器运行：

```powershell
docker compose -p courseportfolio exec -T coursepilot `
  python scripts/demo_local.py --base-url http://localhost:8000
```

指出输出中的：

- `task_status=completed`
- `remote_courserag_mode=true`
- Artifact ID/Version
- `paid_provider_calls=0`

### 2:00–3:00 结果与工程控制

打开 Artifact 或预生成 DOCX，解释 Blueprint、Evidence 引用、Validation 和 Export。最后说明：

> 这个 Demo 证明工程链路可以运行。正式评测也暴露了内容质量问题，因此当前定位为工程 MVP，
> 没有把模型生成质量包装成生产水平。

## 5–8 分钟技术版本

在 3 分钟版本上增加：

1. CourseRAG Search/Context 响应中的 Evidence ID、Index Version、Trace ID；
2. CoursePilot Task、ArtifactVersion 和 WorkflowRun；
3. 一个 ValidationIssue 与 allowed-path Repair 示例；
4. 一个 Interrupt/Edit/Resume 状态变化；
5. 一个 Verified Writeback → Overlay → 后续检索示例；
6. 打开预生成 PPTX，展示对象可编辑而不是整页图片。

## 录屏分镜

1. GitHub 两个仓库首页；
2. 架构图；
3. Docker 三容器健康；
4. 两个 Swagger；
5. Demo CLI；
6. Trace/Artifact；
7. DOCX/PPTX；
8. Evaluation 与 Known Limitations。

## 常见故障

- 端口被占用：确认 Demo PostgreSQL 不暴露宿主 5432，仅检查 8000/8001。
- Docker 冷构建慢：提前完成构建，面试时只 `up -d`。
- Service 未健康：查看容器日志，不现场重装依赖。
- Demo CLI 失败：切换到已录屏和 `LOCAL_DEMO_RESULT.md`，不要临时调用真实 Provider。
