# P12 PostgreSQL Checkpoint、六个 Interrupt 与审批

## PostgreSQL Gate Repair Completion (2026-08-14)

The initial focused tests used fakes and could not prove the PostgreSQL boundary. The repository
does contain a PostgreSQL image, but the historical containers were stopped and the evaluation
compose file exposes the database on host port `55432`; blank local `.env` values were not enough
for host-side Alembic commands. P12 also needed to pass its checkpoint URL and feature flag into
the agent container.

The narrow repair added explicit compose wiring and
`scripts/run_p12_postgres_gate.ps1`. It starts an isolated `coursepilot_p12_gate` project, waits
for readiness, runs Alembic upgrade/downgrade/upgrade, the real Postgres integration tests, and the
CP-DS6 structural runner, then stops the container without deleting its isolated volume. No user
database, legacy table, Chroma collection, Test lock, or external provider was touched.

The first real run exposed two implementation defects rather than a network failure: the worker
could leave the previous Interrupt in `resuming` while creating the next one, and a test approval
used a fixed decision hash that collided on retained-volume reruns. The runtime now flushes the
previous Interrupt before creating the next record; the integration test selects the current
pending Interrupt and derives a unique approval hash per task.

Final evidence: migration round-trip `0016 -> 0017 -> 0016 -> 0017` passed; the real integration
suite passed `6` cases; CP-DS6 executed `24` structural cases with all six Interrupt types,
external calls `0`, and Gold promotion `false`. Recoverable remains opt-in and disabled by default.
P12 Exit Gate is passed and P13 is unblocked for planning.

## 完成内容

- P12-T01/T02：新增 PostgreSQL Checkpointer 工厂、稳定 Thread 配置和六类 Recoverable Interrupt
  Skeleton；旧 Legacy Graph 默认编译和入口保持兼容。
- P12-T03/T04：实现 Decision、Approve/Reject/Cancel、Edit+Resume、Reopen、7 天软过期和不可变
  Artifact Version；恢复使用同一 Thread 和 `Command(resume=...)`。
- P12-T05/T06：新增独立 Export/Verified Writeback Scope、SideEffect 幂等事实、Recoverable
  Task/Interrupt/Decision/Resume API，并复用可信 Principal/Course/Role Header。
- P12-T07/T08：Worker 可认领 pending Resume Command；Approved CP-DS6 24 条输入只做结构校验，
  不读取 Test、不调用外部 Provider、不提升为 Gold。

## 验证证据

- `0017_coursepilot_checkpoint_interrupts (head)`。
- P12 相关专项与迁移测试：`22 passed`；随后 Worker、Graph、CP-DS6 回归：`11 passed`。
- `uv run ruff check src/coursepilot src/agents/coursepilot/graphs`：通过。
- `uv run mypy src/`：通过（401 source files）。
- Legacy Lesson/Exam/PPT Graph smoke：`16 passed`。
- CP-DS6 structural runner：24 cases、六类 Interrupt 各 4 条、external calls=0、Gold promotion=false。

## 当前边界与质量债务

后续收敛验证已完成：新增 P12 Schema/路由被作为兼容增量处理，B0 旧接口投影未发生变化；
全量测试为 `641 passed, 6 skipped`，Ruff Format/Check、Mypy（403 个源文件）通过，迁移
head 为 `0017_coursepilot_checkpoint_interrupts`。当前没有可用 Docker/PostgreSQL 连接，
`alembic check` 仍因缺少 `POSTGRES_*` 配置失败；未用 Fake 冒充 PostgreSQL 集成结果。待
Compose PostgreSQL 可用后执行 `0016→0017→0016→0017`、真实 Checkpoint/Resume、服务重启
和 24 条 CP-DS6 runtime runner。P12 继续保持 `completed_with_quality_debt`，P13 不启动。

- 本阶段的六个暂停点先由 Recoverable Skeleton Graph 承载，P14-P16 再把最终业务节点替换到同一
  Checkpoint/Interrupt 基础设施；因此不宣称 P14-P16 业务质量已经完成。
- 本机当前没有可用 Docker/PostgreSQL 连接，`alembic check` 因缺少 `POSTGRES_*` 配置失败；未用
  Fake 冒充 PostgreSQL 集成结果。需要在 Compose PostgreSQL 可用后执行 `0016→0017→0016→0017`、
  实际 Checkpoint/Resume、服务重启和 24 条 CP-DS6 runtime runner。
- `P12` 状态为 `completed_with_quality_debt`，不是最终 `completed`；P13 暂不具备启动条件。

## 回滚

将 `COURSEPILOT_RECOVERABLE_WORKFLOWS_ENABLED=false`，旧 API 继续使用 Legacy；保留 0017 审计
事实和 Checkpoint，不删除任务、Artifact、旧表或旧评测。
