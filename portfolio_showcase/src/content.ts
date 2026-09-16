import type {
  ArchitectureStep,
  CapabilityCard,
  DemoEvent,
  EvidenceMetric,
  NavItem,
  PositionCard,
  WorkflowScenario,
} from './types'

export const navItems: NavItem[] = [
  { id: 'home', label: '首页' },
  { id: 'architecture', label: '架构' },
  { id: 'capabilities', label: '能力' },
  { id: 'workflow', label: '工作流' },
  { id: 'evidence', label: '工程证据' },
  { id: 'demo', label: '交互演示' },
  { id: 'boundaries', label: '项目边界' },
]

export const positionCards: PositionCard[] = [
  {
    id: 'position-problem',
    index: '01',
    label: 'Problem',
    title: '单体 Demo 无法隔离问题',
    description:
      'Agent 节点直接依赖 Chroma 与 Chunk，检索变化会影响业务 Graph，也无法判断失败来自 RAG 还是生成流程。',
    accent: 'problem',
    isPlaceholder: false,
  },
  {
    id: 'position-decision',
    index: '02',
    label: 'Decision',
    title: '先抽象 Port，再物理拆仓',
    description:
      '先稳定 Evidence、Context、错误和版本合同，再通过双进程 HTTP 将知识服务与工作流运行时分离。',
    accent: 'decision',
    isPlaceholder: false,
  },
  {
    id: 'position-result',
    index: '03',
    label: 'Outcome',
    title: '形成可审计的双服务 MVP',
    description:
      'CourseRAG 独立评价检索与引用，CoursePilot 独立验证 Checkpoint、审批、Artifact 与幂等副作用。',
    accent: 'result',
    isPlaceholder: false,
  },
]

export const architectureSteps: ArchitectureStep[] = [
  {
    id: 'monolith',
    index: '01',
    eyebrow: 'Starting point',
    title: '单体应用承载全部能力',
    description:
      '最初的备课 Demo 将 RAG、教案、试卷和 PPT 放在一起，Agent 节点直接依赖检索实现。',
    note: 'Chroma · Chunk · Workflow',
    isPlaceholder: false,
  },
  {
    id: 'split',
    index: '02',
    eyebrow: 'Separation',
    title: 'Port 稳定后拆成两个核心',
    description:
      'CourseRAG 负责 Evidence-first 知识服务；CoursePilot 负责 Typed Workflow、Interrupt、Validation 与 Artifact。',
    note: 'Versioned HTTP contract',
    isPlaceholder: false,
  },
  {
    id: 'contracts',
    index: '03',
    eyebrow: 'Contracts',
    title: 'HTTP、双 Schema 与版本引用',
    description:
      '两个公开仓库只通过 HTTP 协作，共享 PostgreSQL 实例但拥有独立 Schema 与 Migration；索引和 Trace 不作为唯一事实源。',
    note: 'Evidence · Trace · ArtifactVersion',
    isPlaceholder: false,
  },
]

export const capabilityCards: CapabilityCard[] = [
  {
    id: 'rag-ingestion',
    product: 'CourseRAG',
    index: 'R.01',
    title: 'Document → Evidence',
    description:
      '通过 PDF/DOCX Parser Router 与 OCR 形成结构化文档，把稳定 Evidence 与可变化的检索 Chunk 分离。',
    tags: ['Parser Router', 'OCR', 'Stable Evidence'],
    size: 'wide',
    tone: 'rag',
    isPlaceholder: false,
  },
  {
    id: 'rag-retrieval',
    product: 'CourseRAG',
    index: 'R.02',
    title: 'Hybrid Retrieval',
    description: 'Dense 与 BM25S 经 RRF 融合，再做可配置重排；单次查询固定 Primary 与 Overlay 版本。',
    tags: ['Dense', 'BM25S', 'RRF + Rerank'],
    size: 'standard',
    tone: 'rag',
    isPlaceholder: false,
  },
  {
    id: 'pilot-state',
    product: 'CoursePilot',
    index: 'P.01',
    title: 'Resumable Workflow',
    description:
      '稳定 Thread 与 PostgreSQL Checkpoint 支持服务重启后恢复，六类人工节点允许编辑、重规划、拒绝或取消。',
    tags: ['Typed State', '6 Interrupts', 'Checkpoint'],
    size: 'tall',
    tone: 'pilot',
    isPlaceholder: false,
  },
  {
    id: 'pilot-quality',
    product: 'CoursePilot',
    index: 'P.02',
    title: 'Validate & Repair',
    description: 'ValidationIssue 定位到 Item 与 JSON Path；RepairPlanner 预先限定 allowed_paths，并检查越界修改与回归。',
    tags: ['ValidationIssue', 'Allowed Paths'],
    size: 'standard',
    tone: 'pilot',
    isPlaceholder: false,
  },
  {
    id: 'platform-trace',
    product: 'Platform',
    index: 'S.01',
    title: 'Traceable by design',
    description:
      'Evidence/Context 版本、模型 Profile、不可变 ArtifactVersion、Approval Scope 与 SideEffect identity 共同形成审计链。',
    tags: ['HTTP-only', 'Two Schemas', 'Idempotency'],
    size: 'wide',
    tone: 'neutral',
    isPlaceholder: false,
  },
]

export const workflowScenarios: WorkflowScenario[] = [
  {
    id: 'lesson',
    label: '备课',
    title: '从已审核 Evidence 到版本化教案',
    output: 'Lesson Plan · DOCX',
    steps: [
      { id: 'lesson-context', index: '01', title: 'Context', subtitle: '引用已审核知识', description: '读取 CourseRAG 的 KP、Evidence 与 ContextPackageRef，不重复抽取 KP。' },
      { id: 'lesson-blueprint', index: '02', title: 'Blueprint', subtitle: '创建结构版本', description: '生成可审阅的 Lesson Blueprint ArtifactVersion。' },
      { id: 'lesson-interrupt', index: '03', title: 'Interrupt', subtitle: '人工确认蓝图', description: '教师可以批准、字段编辑后恢复、重新规划、拒绝或取消。' },
      { id: 'lesson-validate', index: '04', title: 'Validate', subtitle: '校验 Session', description: '对分课时内容与全局约束输出结构化 ValidationIssue。' },
      { id: 'lesson-repair', index: '05', title: 'Repair', subtitle: '局部修复', description: '按 allowed_paths 修复目标 Session，并重跑目标与全局校验。' },
      { id: 'lesson-export', index: '06', title: 'Export', subtitle: '版本化导出', description: '导出可编辑 DOCX；只有经独立批准的片段才能写回。' },
    ],
    isPlaceholder: false,
  },
  {
    id: 'exam',
    label: '命题',
    title: '从命题蓝图到全卷一致性校验',
    output: 'Exam Package · DOCX',
    steps: [
      { id: 'exam-context', index: '01', title: 'Context', subtitle: '绑定课程证据', description: '锁定本次命题使用的 KP、Evidence 与版本引用。' },
      { id: 'exam-blueprint', index: '02', title: 'Blueprint', subtitle: '冻结命题约束', description: '固定题型、分值、难度、KP 覆盖与生成 Batch。' },
      { id: 'exam-interrupt', index: '03', title: 'Interrupt', subtitle: '人工审核蓝图', description: '在批量生成前确认整卷结构与约束。' },
      { id: 'exam-validate', index: '04', title: 'Validate', subtitle: 'Fan-in 全局校验', description: '稳定编号后检查题量、总分、覆盖、重复与答案泄漏。' },
      { id: 'exam-repair', index: '05', title: 'Repair', subtitle: '只修目标题目', description: '重复题修后出现项，缺题只生成缺失 Slot，不整卷重跑。' },
      { id: 'exam-export', index: '06', title: 'Export', subtitle: '形成试卷包', description: '导出版本化成果；写回范围限制为单题或解析。' },
    ],
    isPlaceholder: false,
  },
  {
    id: 'slides',
    label: 'PPT',
    title: '从 Slide Architecture 到可编辑 PPTX',
    output: 'Editable Slides · PPTX',
    steps: [
      { id: 'slides-context', index: '01', title: 'Context', subtitle: '绑定课程证据', description: '准备 Evidence、教学目标与素材边界。' },
      { id: 'slides-blueprint', index: '02', title: 'Architecture', subtitle: '先设计页面结构', description: '生成 Slide Architecture，再逐页生成内容、Notes 与 Citation。' },
      { id: 'slides-interrupt', index: '03', title: 'Interrupt', subtitle: '人工确认架构', description: '在页面批量生成前审核并编辑整体叙事。' },
      { id: 'slides-validate', index: '04', title: 'Validate', subtitle: '打开与渲染检查', description: '通过 LibreOffice/Poppler 检查 Open、Render、Overflow 与 Boundary。' },
      { id: 'slides-repair', index: '05', title: 'Repair', subtitle: '定位单页修复', description: '保留已确认页面，只处理被定位的内容或布局问题。' },
      { id: 'slides-export', index: '06', title: 'Export', subtitle: '输出可编辑对象', description: '使用真实 Layout 与 Office 对象导出版本化 PPTX。' },
    ],
    isPlaceholder: false,
  },
]

export const evidenceMetrics: EvidenceMetric[] = [
  {
    id: 'metric-hybrid-recall',
    value: 91.67,
    decimals: 2,
    suffix: '%',
    label: 'Hybrid Recall@10',
    description: 'CourseRAG 课程特定小规模 Dev 集；不代表开放域效果。',
    status: 'complete',
    isPlaceholder: false,
  },
  {
    id: 'metric-citation',
    value: 100,
    suffix: '%',
    label: 'Citation Resolvability',
    description: 'CourseRAG 课程特定 Dev QA 结果，同时 Claim-Citation Completeness 为 100%。',
    status: 'complete',
    isPlaceholder: false,
  },
  {
    id: 'metric-tests',
    value: 258,
    suffix: ' passed',
    label: 'CoursePilot repository tests',
    description: 'P19 公开仓库验证结果；另有 CourseRAG 199 passed、2 skipped。',
    status: 'complete',
    isPlaceholder: false,
  },
  {
    id: 'metric-p18-quality',
    value: 29.17,
    decimals: 2,
    suffix: '%',
    label: 'P18 acceptable rate',
    description: '24 项人工审核：7 minor、13 major、4 reject；正式内容质量 Gate 未通过。',
    status: 'failed',
    isPlaceholder: false,
  },
]

export const demoEvents: DemoEvent[] = [
  {
    id: 'demo-services',
    delay: 180,
    time: 'STEP 01',
    label: 'Services healthy',
    detail: 'PostgreSQL 16 · CourseRAG :8001 · CoursePilot :8000',
    status: 'verified',
  },
  {
    id: 'demo-created',
    delay: 620,
    time: 'STEP 02',
    label: 'Idempotent task created',
    detail: 'Demo course + deterministic lesson journey',
    status: 'running',
  },
  {
    id: 'demo-remote-rag',
    delay: 760,
    time: 'STEP 03',
    label: 'CourseRAG called over HTTP',
    detail: 'labelled demo Evidence · legacy in-process path disabled',
    status: 'resumed',
  },
  {
    id: 'demo-completed',
    delay: 680,
    time: 'STEP 04',
    label: 'Task reached completed',
    detail: 'terminal state: completed · generated artifact: one lesson record',
    status: 'exported',
  },
  {
    id: 'demo-verified',
    delay: 540,
    time: 'STEP 05',
    label: 'Engineering journey verified',
    detail: 'verified 2026-08-26 · paid_provider_calls = 0',
    status: 'verified',
  },
]
