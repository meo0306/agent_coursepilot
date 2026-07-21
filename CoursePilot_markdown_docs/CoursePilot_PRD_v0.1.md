# CoursePilot PRD v0.1

## 面向高校教师的课程备课助教 Agent 系统

## 0. 文档信息

| 项目     | 内容                                                                        |
|----------|-----------------------------------------------------------------------------|
| 产品名称 | CoursePilot                                                                 |
| 产品类型 | Teacher Assistant Agent / 教师备课助理系统                                  |
| 目标用户 | 高校教师、助教、课程建设人员                                                |
| 核心场景 | 基于教材、课程大纲等课程资料，辅助教师完成教学设计、PPT 初稿、作业/试卷生成 |
| 产品阶段 | MVP 需求定义                                                                |
| 文档版本 | v0.1                                                                        |
| 主要目标 | 指导后续技术开发、工程拆解和简历项目实现                                    |

# 1. 产品背景

高校教师在课程备课过程中通常需要完成以下工作：

1.  阅读教材、课程大纲、讲义等大量资料；
2.  梳理章节结构、知识点、教学目标、重点难点；
3.  将教学内容分配到不同课时；
4.  编写教学设计；
5.  制作课程 PPT；
6.  设计课后作业、课堂练习或阶段性测试；
7.  根据教学经验反复修改和沉淀课程资源。

这些工作具有明显的重复性和材料依赖性，但又不能完全自动化替代教师判断。因此，本项目定位为一个 **human-in-the-loop 的教师备课助理系统**：系统负责生成结构化草稿、执行资料检索、完成格式化文档输出和质量校验；教师负责审核、修改、确认和最终使用。

# 2. 产品定位

CoursePilot 是一个面向高校教师备课场景的 Teacher Assistant Agent 系统。

系统支持教师上传教材、课程大纲和补充资料，自动构建私有课程知识库，并基于知识库完成：

1.  教学设计生成；
2.  PPT 初稿生成；
3.  作业/试卷生成；
4.  教师审核后的内容沉淀与知识库更新。

系统采用 **workflow-first, agent-enhanced** 的设计思路：

- 主干流程使用 workflow 保证稳定性和可控性；
- 复杂生成任务采用 plan-and-solve/plan- execute；
- 局部修改、异常补题、外部资料补充等场景采用 ReAct-style tool-use loop；
- 生成结果通过 validator / critic / reflection 节点进行检查和修复；
- 所有核心输出尽量采用结构化 JSON 中间表示，便于解析、校验和文件导出。

# 3. 产品目标

## 3.1 业务目标

1.  降低高校教师备课过程中的材料整理成本；
2.  辅助教师快速生成教学设计、PPT 初稿和作业/试卷；
3.  保证生成内容基于教师上传资料，具备引用来源和可追溯性；
4.  支持教师审核与局部修改，使系统输出更符合真实教学需要；
5.  将教师确认后的优质内容沉淀为课程知识资产。

## 3.2 技术展示目标

该项目作为 Agent / 大模型应用开发方向的简历项目，需要体现：

1.  Agent workflow 编排能力；
2.  RAG 私有知识库构建能力；
3.  结构化输出与 JSON schema 校验能力；
4.  docx / pptx 文件生成能力；
5.  human-in-the-loop 交互能力；
6.  生成内容引用溯源能力；
7.  harness engineering：格式校验、数量校验、重复度检测、异常重试、缓存隔离；
8.  评估指标设计与实验验证能力。

# 4. 目标用户与用户画像

## 4.1 核心用户：高校课程教师

### 用户特征

- 负责一门或多门高校课程；
- 持有教材、课程大纲、讲义、课件等课程资料；
- 需要定期备课、更新教学设计、布置作业或出题；
- 对生成内容质量有较高要求；
- 不希望 AI 完全替代自己，而希望 AI 提供可修改、可追溯的草稿。

### 核心痛点

| 痛点               | 描述                                                          |
|--------------------|---------------------------------------------------------------|
| 材料整理成本高     | 教材、课程大纲、讲义分散，备课前需要反复查找                  |
| 教学设计重复劳动多 | 每节课都要写目标、重点、难点、流程、互动环节                  |
| PPT 制作耗时       | 从教学设计转为 PPT 初稿需要大量格式化工作                     |
| 出题质量不稳定     | 直接让 LLM 出题容易出现题量错误、重复题、答案不完整、考点失衡 |
| 课程资源难沉淀     | 修改后的教案、题目、解析没有形成可复用知识库                  |

# 5. 使用场景

## 5.1 场景一：教师首次创建课程知识库

教师上传教材 PDF 和课程大纲，系统自动解析资料内容，提取章节结构、知识点、教学目标和引用来源，构建该课程的私有知识库。

## 5.2 场景二：教师生成某章节教学设计

教师选择课程、章节、课时数、学生层次和教学模板，系统检索相关资料，识别重点难点，生成按课时组织的教学设计。教师可以对某一课时、某一环节提出局部修改意见。

## 5.3 场景三：教师基于教学设计生成 PPT 初稿

教师确认教学设计后，系统根据教学设计和知识库资料生成 PPT 大纲，并导出可编辑的 `.pptx` 文件。

## 5.4 场景四：教师生成课后作业或试卷

教师选择章节范围、题型、题量、分值和难度分布，系统先生成考点与试卷蓝图，待教师确认后生成题目、答案和解析，并导出学生版试卷、教师版答案、详细解析和答题卡。

## 5.5 场景五：教师审核内容并写回知识库

教师确认某份教学设计、某批题目或某份解析质量较高后，可将其标记为“已审核”，系统将其写回课程知识库，供后续生成任务参考。

# 6. 产品范围
| 模块                 | 是否纳入 MVP | 说明                                  |
|----------------------|--------------|---------------------------------------|
| 课程创建             | 是           | 创建课程空间，维护课程基础信息        |
| 文档上传与解析       | 是           | 支持 PDF / docx / md / txt 等基础格式 |
| 私有知识库构建       | 是           | 支持 chunk 切分、metadata、向量索引   |
| 教学设计生成         | 是           | 项目核心功能                          |
| 教学设计局部修改     | 是           | 支持教师反馈闭环                      |
| PPT 初稿生成         | 是           | 支持基于教学设计生成 pptx             |
| 作业/试卷生成        | 是           | 项目核心亮点，重点做校验机制          |
| docx / pptx 导出     | 是           | 增强项目展示性                        |
| 引用溯源             | 是           | RAG 项目必要能力                      |
| 教师审核与写回知识库 | 是           | 体现动态知识库增长                    |
| 生成质量校验         | 是           | 包括 schema、题量、引用、重复度等     |

# 7. 产品总体流程

## 7.1 主流程

    教师创建课程
      ↓
    上传教材 / 课程大纲 / 讲义
      ↓
    系统解析资料并构建课程知识库
      ↓
    教师选择任务类型
      ├── 生成教学设计
      ├── 生成 PPT
      └── 生成作业 / 试卷
      ↓
    系统执行 Agent Workflow
      ↓
    输出结构化结果与可下载文件
      ↓
    教师审核 / 修改
      ↓
    审核通过内容写回知识库

## 7.2 Agent 架构原则

系统整体采用：

    Workflow 主干
    + RAG 检索
    + Plan-and-Solve 规划生成
    + ReAct-style 工具调用
    + Reflection 校验修正
    + Human Review
    + Knowledge Update

# 8. 信息架构

## 8.1 页面结构

MVP 可采用简化 Web Demo 页面结构：

    首页 / Dashboard
    ├── 课程管理
    │   ├── 创建课程
    │   ├── 课程列表
    │   └── 课程详情
    │
    ├── 资料管理
    │   ├── 上传资料
    │   ├── 资料列表
    │   └── 知识库状态
    │
    ├── 教学设计生成
    │   ├── 参数配置
    │   ├── 生成结果
    │   ├── 局部修改
    │   └── 导出 / 保存
    │
    ├── PPT 生成
    │   ├── 选择教学设计
    │   ├── PPT 参数配置
    │   ├── PPT 大纲预览
    │   └── pptx 下载
    │
    ├── 作业 / 试卷生成
    │   ├── 参数配置
    │   ├── 考点规划确认
    │   ├── 题目生成结果
    │   ├── 校验报告
    │   └── docx 下载
    │
    └── 历史记录
        ├── 教学设计记录
        ├── PPT 记录
        ├── 试卷记录
        └── 已审核内容

# 9. 核心功能需求

## 9.1 课程管理模块

### FR-001 创建课程

#### 功能描述

用户可以创建一个课程空间，用于管理该课程的资料、知识库、教学设计、PPT 和作业试卷。

#### 输入字段

| 字段         | 必填 | 示例                         |
|--------------|------|------------------------------|
| 课程名称     | 是   | 人工智能导论                 |
| 课程类型     | 否   | 理论课 / 实验课 / 综合课     |
| 授课对象     | 否   | 本科二年级                   |
| 专业背景     | 否   | 计算机类 / 非计算机类        |
| 默认教学模板 | 否   | 标准教案 / BOPPPS            |
| 课程说明     | 否   | 本课程介绍 AI 基础理论与应用 |

#### 输出

- 创建课程成功；
- 生成 course_id；
- 进入课程详情页。

#### 验收标准

1.  用户可以成功创建课程；
2.  课程信息可以被后续资料上传、教学设计生成、试卷生成等模块调用；
3.  课程名称不能为空；
4.  同名课程允许存在，但需要不同 course_id 区分。

## 9.2 资料上传与知识库构建模块

### FR-002 上传课程资料

#### 功能描述

用户可以上传教材、课程大纲、讲义、实验指导书等资料，系统解析后写入课程知识库。

#### 支持文件类型

MVP 阶段建议支持：

| 类型     | 优先级 |
|----------|--------|
| PDF      | P0     |
| DOCX     | P0     |
| TXT      | P0     |
| Markdown | P0     |
| PPTX     | P1     |

#### 上传资料类型

| source_type      | 描述       |
|------------------|------------|
| textbook         | 教材       |
| syllabus         | 课程大纲   |
| lecture_note     | 讲义       |
| experiment_guide | 实验指导书 |
| case_material    | 案例材料   |
| other            | 其他资料   |

#### 验收标准

1.  用户可以上传单个或多个文件；
2.  文件上传后展示解析状态；
3.  解析成功后可进入知识库构建流程；
4.  解析失败时需要返回错误原因；
5.  系统需要记录文件名、文件类型、上传时间、解析状态。

### FR-003 文档解析与 chunk 切分

#### 功能描述

系统解析上传文档内容，并切分为适合 RAG 检索的文本块。

#### 处理要求

每个 chunk 至少包含以下 metadata：

| 字段             | 说明                   |
|------------------|------------------------|
| chunk_id         | 文本块 ID              |
| course_id        | 所属课程               |
| document_id      | 来源文档               |
| source_type      | 教材 / 大纲 / 讲义等   |
| chapter          | 所属章节               |
| section          | 所属小节               |
| page             | 页码，无法识别时可为空 |
| title            | 当前 chunk 标题        |
| content          | chunk 文本内容         |
| knowledge_points | 自动识别的知识点标签   |
| verified         | 是否为教师审核内容     |
| created_at       | 创建时间               |

#### 验收标准

1.  系统可以将文档切分为多个 chunk；
2.  chunk 可被向量化并检索；
3.  chunk metadata 可用于过滤检索；
4.  检索结果中可以展示引用来源；
5.  至少支持按 course_id、source_type、chapter 过滤。

### FR-004 构建私有课程知识库

#### 功能描述

系统将解析后的 chunk 写入向量数据库和结构化数据库，形成课程私有知识库。

#### 知识库内容类型

| 类型           | 描述                                   |
|----------------|----------------------------------------|
| 原始资料 chunk | 从教材、大纲、讲义中解析出的内容       |
| 结构化知识点   | 自动抽取的章节、知识点、教学目标       |
| 已审核生成内容 | 教师确认后的教学设计、题目、答案、解析 |

#### 验收标准

1.  每门课程拥有独立知识库；
2.  支持基于章节、知识点、资料类型检索；
3.  检索结果返回文本内容和引用来源；
4.  不同课程之间知识库内容不可混淆；
5.  后续生成任务必须显式传入 course_id。

## 9.3 教学设计生成模块

### FR-005 教学设计参数配置

#### 功能描述

教师选择课程和章节，并配置教学设计生成参数。

#### 输入字段

| 字段                    | 必填 | 示例                           |
|-------------------------|------|--------------------------------|
| course_id               | 是   | 当前课程                       |
| chapter_range           | 是   | 第 3 章                        |
| total_sessions          | 是   | 2                              |
| session_duration        | 是   | 45 分钟                        |
| student_level           | 否   | 本科低年级                     |
| student_background      | 否   | 非计算机专业                   |
| teaching_template       | 是   | 标准教案 / BOPPPS              |
| teaching_focus          | 否   | 理论理解 / 算法实现 / 案例应用 |
| include_interaction     | 否   | 是                             |
| include_homework        | 否   | 是                             |
| additional_requirements | 否   | 希望多加入案例                 |

#### 验收标准

1.  必填字段为空时不能发起生成；
2.  用户可以选择已有课程和章节；
3.  用户可以配置课时数和模板；
4.  参数配置应被记录到 generation_task 中。

### FR-006 课程资料检索与知识点抽取

#### 功能描述

系统根据用户配置，从课程知识库中检索相关教材、大纲和讲义内容，抽取本次教学设计所需的知识点、重点和难点。

#### 输出结构

    {
      "chapter": "第3章 搜索算法",
      "retrieved_contexts": [
        {
          "chunk_id": "chunk_001",
          "source_type": "textbook",
          "chapter": "第3章",
          "page": 45,
          "content_preview": "搜索问题通常由状态空间、初始状态、目标测试和路径代价组成..."
        }
      ],
      "knowledge_points": [
        {
          "name": "状态空间",
          "importance": "high",
          "difficulty": "medium",
          "source_chunk_ids": ["chunk_001"]
        }
      ]
    }

#### 验收标准

1.  系统能够返回与章节相关的检索内容；
2.  抽取出的知识点需要绑定 source_chunk_ids；
3.  若检索结果为空，需要提示用户补充资料或调整章节范围；
4.  不允许在无任何课程资料支撑的情况下生成教学设计。

### FR-007 生成课时规划

#### 功能描述

系统基于知识点、课程大纲和教师配置，先生成课时级规划，再生成完整教学设计。

该节点体现 plan-and-solve 中的 plan 阶段。

#### 输出结构

    {
      "session_plan": [
        {
          "session_index": 1,
          "session_title": "搜索问题的基本概念",
          "duration": 45,
          "knowledge_points": ["状态空间", "初始状态", "目标状态", "路径代价"],
          "teaching_focus": "帮助学生理解搜索问题的建模方式",
          "difficulty_points": ["状态空间抽象"],
          "time_allocation": [
            {
              "activity": "导入案例",
              "minutes": 5
            },
            {
              "activity": "概念讲解",
              "minutes": 25
            },
            {
              "activity": "课堂练习",
              "minutes": 10
            },
            {
              "activity": "总结",
              "minutes": 5
            }
          ]
        }
      ]
    }

#### 验收标准

1.  课时数量必须等于用户配置的 total_sessions；
2.  每个课时必须有主题、知识点、重点、难点和时间分配；
3.  每个课时时间分配总和应等于 session_duration；
4.  核心知识点不能遗漏；
5.  课时规划生成后进入教学设计生成节点。

### FR-008 生成完整教学设计

#### 功能描述

系统基于课时规划生成完整教学设计。

#### 每个课时的输出内容

| 字段                            | 描述            |
|---------------------------------|-----------------|
| session_index                   | 第几课时        |
| session_title                   | 课时标题        |
| teaching_objectives             | 教学目标        |
| key_points                      | 教学重点        |
| difficult_points                | 教学难点        |
| teaching_process                | 教学流程        |
| interaction_design              | 互动设计        |
| blackboard_or_slide_suggestions | 板书或 PPT 建议 |
| homework_suggestion             | 作业建议        |
| references                      | 引用来源        |

#### 输出结构示例

    {
      "lesson_design": {
        "course_name": "人工智能导论",
        "chapter": "第3章 搜索算法",
        "total_sessions": 2,
        "sessions": [
          {
            "session_index": 1,
            "session_title": "搜索问题的基本概念",
            "teaching_objectives": [
              "理解搜索问题的基本组成要素",
              "能够用状态空间描述简单问题"
            ],
            "key_points": ["状态空间", "目标测试", "路径代价"],
            "difficult_points": ["如何抽象状态空间"],
            "teaching_process": [
              {
                "stage": "导入",
                "minutes": 5,
                "content": "以校园路径规划问题引入搜索问题。"
              }
            ],
            "interaction_design": [
              "请学生尝试描述迷宫问题中的状态、动作和目标。"
            ],
            "homework_suggestion": [
              "用搜索问题的四要素描述八数码问题。"
            ],
            "references": [
              {
                "source_type": "textbook",
                "chapter": "第3章",
                "page": 45,
                "chunk_id": "chunk_001"
              }
            ]
          }
        ]
      }
    }

#### 验收标准

1.  输出必须符合 JSON schema；
2.  每个课时必须包含教学目标、重点、难点、流程、引用；
3.  生成内容应基于检索结果；
4.  至少核心知识点需要有引用来源；
5.  支持保存为草稿；
6.  支持导出为 docx 或 markdown。

### FR-009 教学设计质量校验

#### 功能描述

系统对生成的教学设计进行自动校验，并在必要时执行反思式修正。

该节点体现 reflection / critic 机制。

#### 校验项

| 校验项                   | 说明                   |
|--------------------------|------------------------|
| schema_valid             | JSON 是否符合 schema   |
| session_count_valid      | 课时数量是否正确       |
| time_allocation_valid    | 每课时时间分配是否合理 |
| objective_coverage_valid | 是否覆盖课程大纲目标   |
| knowledge_coverage_valid | 是否覆盖核心知识点     |
| reference_valid          | 是否包含有效引用       |
| overload_warning         | 是否某课时内容过载     |

#### 验收标准

1.  系统必须生成校验报告；
2.  关键校验失败时不能直接进入最终确认状态；
3.  系统可自动修复格式错误和轻微内容缺失；
4.  自动修复最多执行 2 轮；
5.  仍无法修复时向用户展示问题。

### FR-010 教学设计局部修改

#### 功能描述

教师可以针对生成结果提出局部修改意见，例如：

- “把第 2 课时的案例换成更贴近学生生活的案例”；
- “第 1 课时减少理论讲解，增加课堂互动”；
- “把第 3 部分改得更适合非计算机专业学生”。

系统需要定位修改对象，检索相关资料，并生成局部替换内容。

该节点可采用 ReAct-style tool-use loop。

#### 输入字段

| 字段                 | 必填 | 示例                                 |
|----------------------|------|--------------------------------------|
| lesson_design_id     | 是   | 当前教学设计                         |
| target_scope         | 是   | 第 2 课时 / 教学流程 / 互动环节      |
| feedback_text        | 是   | 案例太抽象，换成更贴近学生生活的案例 |
| keep_unchanged_parts | 否   | 是                                   |

#### 验收标准

1.  系统能识别用户要修改的位置；
2.  默认只修改目标范围，不影响其他课时内容；
3.  修改后需要保留版本记录；
4.  修改内容需要重新进行局部校验；
5.  修改结果需要展示修改说明。

## 9.4 PPT 生成模块

### FR-011 PPT 生成参数配置

#### 功能描述

教师基于已确认的教学设计生成 PPT 初稿。

#### 输入字段

| 字段                   | 必填 | 示例           |
|------------------------|------|----------------|
| lesson_design_id       | 是   | 已确认教学设计 |
| slide_count            | 否   | 20             |
| ppt_style              | 否   | 简洁教学风     |
| include_cases          | 否   | 是             |
| include_interaction    | 否   | 是             |
| include_summary        | 否   | 是             |
| include_homework_slide | 否   | 是             |

#### 验收标准

1.  必须选择一个教学设计；
2.  未确认的教学设计也可生成 PPT，但需要标记来源状态为 draft；
3.  用户可配置页数和内容偏好。

### FR-012 生成 PPT 大纲

#### 功能描述

系统先将教学设计转化为 slide outline，再生成 pptx 文件。

该节点体现 plan-and-solve：先规划 PPT 结构，再生成页面内容。

#### 输出结构

    {
      "slide_outline": [
        {
          "slide_id": 1,
          "slide_type": "title",
          "title": "搜索算法概述",
          "content_points": [],
          "source_session": 1,
          "references": []
        },
        {
          "slide_id": 2,
          "slide_type": "learning_objectives",
          "title": "学习目标",
          "content_points": [
            "理解搜索问题的基本组成",
            "掌握状态空间的表示方式"
          ],
          "source_session": 1,
          "references": [
            {
              "chunk_id": "chunk_001",
              "page": 45
            }
          ]
        }
      ]
    }

#### 验收标准

1.  PPT 大纲必须符合 JSON schema；
2.  PPT 页面应覆盖教学设计中的核心内容；
3.  页面数量应接近用户配置的 slide_count；
4.  每页应包含 slide_type；
5.  核心内容页应包含引用来源。

### FR-013 生成 PPTX 文件

#### 功能描述

系统基于 PPT 大纲生成可编辑 `.pptx` 文件。

#### MVP 要求

PPT 不追求复杂视觉设计，但需要满足：

1.  结构完整；
2.  标题清晰；
3.  要点分明；
4.  可下载；
5.  可编辑；
6.  参考资料可追溯。

#### 验收标准

1.  系统成功导出 `.pptx` 文件；
2.  文件可正常打开；
3.  PPT 页数与大纲一致；
4.  每页标题和内容正常渲染；
5.  参考资料页包含引用来源；
6.  导出失败时返回明确错误信息。

## 9.5 作业 / 试卷生成模块

### FR-014 出题参数配置

#### 功能描述

教师配置作业或试卷生成参数。

#### 输入字段

| 字段                    | 必填 | 示例                      |
|-------------------------|------|---------------------------|
| course_id               | 是   | 当前课程                  |
| chapter_range           | 是   | 第 3 章                   |
| generation_type         | 是   | 作业 / 试卷               |
| total_score             | 否   | 100                       |
| question_types          | 是   | 单选、多选、判断、简答    |
| question_count          | 是   | 单选 10，道判断 5，简答 3 |
| difficulty_distribution | 否   | 易 30%，中 50%，难 20%    |
| include_answer          | 否   | 是                        |
| include_explanation     | 否   | 是                        |
| include_answer_sheet    | 否   | 是                        |
| additional_requirements | 否   | 尽量结合应用案例          |

#### 验收标准

1.  题型和题量不能为空；
2.  如果是试卷，建议 total_score 必填；
3.  系统需校验题量配置是否合法；
4.  参数配置需要进入后续考点规划节点。

### FR-015 生成考点与分值规划

#### 功能描述

系统在正式生成题目前，先生成 exam blueprint，包括考点覆盖、题型分布、分值分布和难度分布。

该节点是作业/试卷生成模块的核心亮点。

#### 输出结构

    {
      "exam_blueprint": {
        "generation_type": "exam",
        "total_score": 100,
        "chapter_range": "第3章 搜索算法",
        "difficulty_distribution": {
          "easy": 0.3,
          "medium": 0.5,
          "hard": 0.2
        },
        "question_groups": [
          {
            "question_type": "single_choice",
            "count": 10,
            "score_each": 2,
            "total_score": 20,
            "knowledge_points": [
              "状态空间",
              "广度优先搜索",
              "深度优先搜索"
            ]
          },
          {
            "question_type": "short_answer",
            "count": 3,
            "score_each": 10,
            "total_score": 30,
            "knowledge_points": [
              "启发式函数",
              "A*算法性质"
            ]
          }
        ]
      }
    }

#### 验收标准

1.  题型数量必须与用户配置一致；
2.  总分必须与 total_score 一致；
3.  考点应来自知识库检索结果；
4.  核心知识点不能明显遗漏；
5.  用户可以确认、修改或重新生成 blueprint；
6.  只有 blueprint 确认后才进入正式出题。

### FR-016 按题型生成题目

#### 功能描述

系统根据已确认的 exam blueprint，按题型分流调用不同生成节点，生成题目、答案、解析和引用。

#### 支持题型

MVP 建议支持：

| 题型       | 优先级 |
|------------|--------|
| 单选题     | P0     |
| 多选题     | P0     |
| 判断题     | P0     |
| 简答题     | P0     |
| 编程题     | P1     |
| 案例分析题 | P1     |

#### 题目结构

    {
      "questions": [
        {
          "question_id": "q_001",
          "question_type": "single_choice",
          "knowledge_point": "状态空间",
          "difficulty": "easy",
          "score": 2,
          "question": "以下哪一项最能表示搜索问题中的状态空间？",
          "options": {
            "A": "所有可能状态的集合",
            "B": "最终答案的集合",
            "C": "算法运行时间",
            "D": "启发式函数的取值"
          },
          "correct_answer": "A",
          "explanation": "状态空间是问题中所有可能状态的集合。",
          "references": [
            {
              "chunk_id": "chunk_001",
              "source_type": "textbook",
              "chapter": "第3章",
              "page": 45
            }
          ]
        }
      ]
    }

#### 验收标准

1.  每道题必须包含 question_type、knowledge_point、difficulty、score、question；
2.  客观题必须包含 options 和 correct_answer；
3.  每道题必须包含 answer 或 correct_answer；
4.  如果用户选择生成解析，每道题必须包含 explanation；
5.  每道题应尽量包含 references；
6.  输出必须符合 JSON schema。

### FR-017 题目质量校验

#### 功能描述

系统对生成题目进行格式、数量、答案、考点、重复度等校验。

#### 校验项

| 校验项                   | 说明                   |
|--------------------------|------------------------|
| schema_valid             | JSON 格式是否正确      |
| question_count_valid     | 各题型题量是否符合要求 |
| score_valid              | 分值总和是否正确       |
| answer_valid             | 答案是否完整           |
| option_valid             | 客观题选项是否合法     |
| explanation_valid        | 解析是否完整           |
| knowledge_coverage_valid | 考点是否覆盖 blueprint |
| duplicate_rate           | 题目重复率             |
| citation_valid           | 引用是否有效           |

#### 验收标准

1.  系统必须输出校验报告；
2.  题量不足时自动补题；
3.  JSON 解析失败时自动修复；
4.  重复题超过阈值时自动替换；
5.  答案缺失时自动补全；
6.  自动修复最多执行 2 轮；
7.  仍失败时展示失败原因和可人工处理项。

### FR-018 导出作业 / 试卷文件

#### 功能描述

系统将题目生成结果导出为 docx 文件。

#### 输出文件

MVP 建议导出四类文件：

| 文件            | 内容                       |
|-----------------|----------------------------|
| 学生版试卷      | 仅包含题目和答题区域       |
| 教师版答案      | 包含题目和标准答案         |
| 详细解析        | 包含题目、答案、解析和引用 |
| 答题卡 / 评分表 | 用于客观题作答或教师评分   |

#### 验收标准

1.  系统成功生成 docx 文件；
2.  文件可正常打开；
3.  题目顺序符合固定规则；
4.  题号连续；
5.  答案文件与学生版试卷题号一致；
6.  下载链接可用；
7.  导出失败时返回明确错误信息。

## 9.6 教师审核与知识库更新模块

### FR-019 教师审核生成内容

#### 功能描述

教师可以对生成内容进行确认、修改、弃用或写回知识库。

#### 内容类型

| 类型          | 是否支持审核 |
|---------------|--------------|
| 教学设计      | 是           |
| PPT 大纲      | 是           |
| 题目          | 是           |
| 答案解析      | 是           |
| PPT 文件本身  | 可选         |
| docx 文件本身 | 可选         |

#### 状态流转

    draft → reviewed → approved / rejected → archived

#### 验收标准

1.  生成内容默认状态为 draft；
2.  教师可以将内容标记为 approved；
3.  被 approved 的内容可以写回知识库；
4.  rejected 内容不会进入知识库；
5.  所有审核操作需要记录时间。

### FR-020 已审核内容写回知识库

#### 功能描述

教师确认后的高质量内容可以写回课程知识库，供后续生成任务参考。

#### 写回内容 metadata

| 字段             | 说明                                   |
|------------------|----------------------------------------|
| content_id       | 内容 ID                                |
| course_id        | 所属课程                               |
| content_type     | lesson_design / question / explanation |
| related_chapter  | 关联章节                               |
| knowledge_points | 知识点标签                             |
| verified         | true                                   |
| source           | generated_and_approved                 |
| created_at       | 创建时间                               |

#### 验收标准

1.  只有 approved 内容可以写回知识库；
2.  写回内容必须带 verified=true；
3.  后续检索结果中可以区分原始资料与已审核生成内容；
4.  系统不能将未审核内容自动写回知识库。

# 10. 任务与状态管理

## 10.1 Generation Task

系统中每次生成都应记录为一个 generation_task。

### 任务类型

| task_type       | 描述            |
|-----------------|-----------------|
| build_kb        | 构建知识库      |
| generate_lesson | 生成教学设计    |
| revise_lesson   | 修改教学设计    |
| generate_ppt    | 生成 PPT        |
| generate_exam   | 生成作业 / 试卷 |
| export_docx     | 导出 docx       |
| export_pptx     | 导出 pptx       |

### 任务状态

    pending → running → success / failed / partially_success

### 任务记录字段

| 字段                 | 说明     |
|----------------------|----------|
| task_id              | 任务 ID  |
| course_id            | 所属课程 |
| task_type            | 任务类型 |
| input_params         | 输入参数 |
| status               | 当前状态 |
| intermediate_outputs | 中间结果 |
| validation_report    | 校验报告 |
| output_files         | 输出文件 |
| error_message        | 错误信息 |
| created_at           | 创建时间 |
| updated_at           | 更新时间 |

# 11. 核心数据对象

## 11.1 Course

    {
      "course_id": "course_001",
      "course_name": "人工智能导论",
      "course_type": "理论课",
      "student_level": "本科二年级",
      "student_background": "计算机类",
      "description": "介绍人工智能基础理论与典型算法",
      "created_at": "2026-06-19T10:00:00"
    }

## 11.2 Document

    {
      "document_id": "doc_001",
      "course_id": "course_001",
      "file_name": "人工智能导论教材.pdf",
      "source_type": "textbook",
      "file_type": "pdf",
      "parse_status": "success",
      "created_at": "2026-06-19T10:05:00"
    }

## 11.3 Knowledge Chunk

    {
      "chunk_id": "chunk_001",
      "course_id": "course_001",
      "document_id": "doc_001",
      "source_type": "textbook",
      "chapter": "第3章",
      "section": "3.1 搜索问题",
      "page": 45,
      "title": "搜索问题的基本组成",
      "content": "搜索问题通常由状态空间、初始状态、目标测试和路径代价组成...",
      "knowledge_points": ["状态空间", "初始状态", "目标测试", "路径代价"],
      "verified": false
    }

## 11.4 Lesson Design

    {
      "lesson_design_id": "lesson_001",
      "course_id": "course_001",
      "chapter": "第3章 搜索算法",
      "status": "draft",
      "total_sessions": 2,
      "sessions": [],
      "validation_report": {},
      "created_at": "2026-06-19T11:00:00"
    }

## 11.5 Question

    {
      "question_id": "q_001",
      "course_id": "course_001",
      "question_type": "single_choice",
      "knowledge_point": "状态空间",
      "difficulty": "easy",
      "score": 2,
      "question": "以下哪一项最能表示搜索问题中的状态空间？",
      "options": {
        "A": "所有可能状态的集合",
        "B": "最终答案的集合",
        "C": "算法运行时间",
        "D": "启发式函数的取值"
      },
      "correct_answer": "A",
      "explanation": "状态空间是问题中所有可能状态的集合。",
      "references": [],
      "status": "draft"
    }

# 12. Agent Workflow 设计要求

## 12.1 总体原则

1.  主流程用 workflow 显式编排；
2.  每个节点输入输出必须结构化；
3.  LLM 输出必须经过 schema 校验；
4.  生成任务必须有中间结果记录；
5.  关键节点必须有失败处理机制；
6.  用户审核是正式写回知识库的前置条件。

## 12.2 教学设计 Workflow

    Input Params
      ↓
    Retrieve Course Context
      ↓
    Extract Knowledge Points
      ↓
    Plan Sessions
      ↓
    Generate Lesson Design
      ↓
    Validate Lesson Design
      ↓
    Save Draft
      ↓
    Human Review
      ↓
    Reflect & Revise（可选）

## 12.3 PPT 生成 Workflow

    Select Lesson Design
      ↓
    Generate Slide Outline
      ↓
    Validate Slide Outline
      ↓
    Build PPTX
      ↓
    Export File

## 12.4 作业 / 试卷生成 Workflow

    Input Exam Params
      ↓
    Retrieve Course Context
      ↓
    Plan Exam Blueprint
      ↓
    Human Confirm Blueprint
      ↓
    Generate Questions by Type
      ↓
    Validate Questions
      ↓
    Reflect & Repair
      ↓
    Export DOCX Files
      ↓
    Human Review
      ↓
    Approved Questions Write Back to KB

# 13. Harness Engineering 需求

## 13.1 Schema 校验

所有 LLM 输出必须定义 JSON schema，并进行自动校验。

适用对象：

- 教学设计；
- 课时规划；
- PPT 大纲；
- 试卷蓝图；
- 题目；
- 答案解析；
- 校验报告。

## 13.2 数量校验

出题模块必须校验：

1.  总题量；
2.  各题型题量；
3.  总分；
4.  各题型分值；
5.  每道题编号连续性。

## 13.3 引用校验

系统应检查：

1.  核心内容是否包含引用；
2.  引用 chunk_id 是否存在；
3.  引用是否来自当前 course_id；
4.  引用是否与生成内容语义相关。

## 13.4 重复度检测

题目生成后需要进行重复度检测。

MVP 可采用：

1.  文本相似度；
2.  embedding 相似度；
3.  同一知识点下题干相似度检测。

建议阈值：

    duplicate_similarity_threshold = 0.85

当相似度超过阈值时，标记为疑似重复。

## 13.5 异常重试机制

必须处理以下异常：

| 异常          | 处理方式               |
|---------------|------------------------|
| JSON 解析失败 | 调用格式修复节点       |
| 题量不足      | 根据缺失题型补生成     |
| 答案缺失      | 调用答案补全节点       |
| 引用缺失      | 重新检索并补引用       |
| 重复题过多    | 删除重复题并补题       |
| 文件导出失败  | 记录错误并允许重新导出 |

## 13.6 缓存隔离

每次生成任务必须使用独立 task_id 管理中间缓存，避免旧任务数据污染新任务。

缓存内容包括：

1.  检索结果；
2.  课时规划；
3.  教学设计草稿；
4.  试卷蓝图；
5.  题目缓存；
6.  答案缓存；
7.  解析缓存；
8.  导出文件路径。

# 14. 非功能性需求

## 14.1 性能要求

| 指标         | MVP 目标           |
|--------------|--------------------|
| 文档上传响应 | 5 秒内返回上传状态 |
| 知识库构建   | 可异步执行         |
| 教学设计生成 | 3 分钟内完成       |
| PPT 生成     | 3 分钟内完成       |
| 试卷生成     | 5 分钟内完成       |
| 文件导出     | 1 分钟内完成       |

## 14.2 可用性要求

1.  生成任务需要显示状态；
2.  失败时必须展示可理解的错误原因；
3.  用户可以重新生成；
4.  用户可以查看历史生成结果；
5.  用户可以下载导出文件。

## 14.3 可维护性要求

1.  各 Agent 节点应模块化；
2.  Prompt 模板应独立管理；
3.  JSON schema 应集中维护；
4.  校验器应可单独测试；
5.  文件导出器应与 LLM 生成逻辑解耦。

## 14.4 安全与隐私要求

1.  不同课程资料隔离；
2.  用户上传资料不应混入其他课程知识库；
3.  生成任务必须绑定 course_id；
4.  删除课程时应支持删除相关资料、chunk、生成结果；
5.  API key 不应写入代码仓库。

# 15. 评估指标

## 15.1 RAG 评估指标

| 指标              | 说明                             |
|-------------------|----------------------------------|
| Recall@K          | 目标知识点相关资料是否能被检索到 |
| Context Relevance | 检索片段与任务的相关性           |
| Citation Coverage | 生成内容中包含引用的比例         |
| Citation Accuracy | 引用是否能支持生成内容           |

## 15.2 教学设计评估指标

| 指标                     | 说明             |
|--------------------------|------------------|
| Session Count Accuracy   | 课时数量是否正确 |
| Time Allocation Accuracy | 时间分配是否合理 |
| Objective Coverage Rate  | 教学目标覆盖率   |
| Knowledge Coverage Rate  | 核心知识点覆盖率 |
| Human Score              | 人工质量评分     |

## 15.3 作业 / 试卷评估指标

| 指标                        | 说明             |
|-----------------------------|------------------|
| Question Count Accuracy     | 题量是否符合配置 |
| Score Distribution Accuracy | 分值是否符合配置 |
| Knowledge Coverage Rate     | 考点覆盖率       |
| Duplicate Rate              | 重复题比例       |
| Answer Completeness         | 答案完整率       |
| Explanation Completeness    | 解析完整率       |
| Schema Pass Rate            | 结构化输出通过率 |

## 15.4 系统工程指标

| 指标                    | 说明           |
|-------------------------|----------------|
| Generation Success Rate | 生成任务成功率 |
| Retry Count             | 平均重试次数   |
| Export Success Rate     | 文件导出成功率 |
| Average Generation Time | 平均生成耗时   |

# 16. MVP 验收标准

MVP 完成时，需要满足以下标准：

## 16.1 基础能力

- 用户可以创建课程；
- 用户可以上传教材和课程大纲；
- 系统可以解析资料并构建课程知识库；
- 系统可以基于知识库检索相关内容；
- 检索结果可以展示引用来源。

## 16.2 教学设计能力

- 用户可以配置章节、课时数、模板等参数；
- 系统可以生成课时规划；
- 系统可以生成完整教学设计；
- 教学设计包含目标、重点、难点、流程、互动、作业建议和引用；
- 用户可以进行局部修改；
- 系统可以导出教学设计文件。

## 16.3 PPT 能力

- 用户可以选择教学设计生成 PPT；
- 系统可以生成 PPT 大纲；
- 系统可以导出可编辑 pptx 文件；
- PPT 内容与教学设计一致。

## 16.4 作业 / 试卷能力

- 用户可以配置题型、题量、分值、难度；
- 系统可以生成考点与试卷蓝图；
- 用户可以确认 blueprint；
- 系统可以按题型生成题目；
- 系统可以校验题量、格式、答案、解析和重复度；
- 系统可以导出学生版试卷、教师版答案、详细解析和答题卡。

## 16.5 审核与知识库更新能力

- 生成内容默认是 draft；
- 用户可以确认内容；
- 只有确认内容可以写回知识库；
- 写回内容可以在后续生成任务中被检索到；
- 系统可以区分原始资料和已审核生成内容。

# 17. 开发优先级

## 17.1 P0：第一阶段必须实现

1.  课程创建；
2.  文档上传；
3.  文档解析与 chunk 切分；
4.  向量知识库构建；
5.  RAG 检索；
6.  教学设计生成；
7.  教学设计 JSON schema 校验；
8.  教学设计局部修改；
9.  作业 / 试卷参数配置；
10. 试卷 blueprint 生成；
11. 题目生成；
12. 题目质量校验；
13. docx 导出；
14. 基础历史记录；
15. PPT 大纲生成；
16. pptx 导出；



## 17.2 P1：第二阶段建议实现
1.  教师审核与写回知识库；
2.  引用准确性校验；
3.  embedding 重复度检测；
4.  生成任务状态可视化；
5.  评估指标统计。


# 18. 推荐技术实现边界

本 PRD 不强制具体技术选型，但建议 MVP 采用以下技术栈：

| 层级         | 推荐技术                           |
|--------------|------------------------------------|
| 前端         | Streamlit / Gradio / React 简化版  |
| 后端         | FastAPI                            |
| Agent 编排   | LangGraph                          |
| LLM 接入     | OpenAI / DeepSeek / Qwen           |
| RAG 框架     | LangChain / LlamaIndex             |
| 向量数据库   | Chroma / pgvector                  |
| 结构化数据库 | PostgreSQL / SQLite MVP            |
| 文件解析     | PyMuPDF、python-docx、unstructured |
| Word 导出    | python-docx                        |
| PPT 导出     | python-pptx                        |
| 部署         | Docker / Docker Compose            |

MVP 可以先使用：

    FastAPI + LangGraph + Chroma + SQLite/PostgreSQL + python-docx + python-pptx

Redis、Milvus、复杂权限系统、复杂前端可后续再加。

# 19. 关键风险与应对策略

| 风险               | 描述                           | 应对策略                                     |
|--------------------|--------------------------------|----------------------------------------------|
| 文档解析质量不稳定 | PDF 版式复杂，章节识别困难     | 先支持文本型 PDF，保留人工编辑 metadata 能力 |
| LLM 输出格式不稳定 | JSON 解析失败                  | 使用 schema、格式修复节点、重试机制          |
| 出题重复或质量差   | LLM 容易生成同质化题目         | 增加 blueprint、考点规划、重复度检测         |
| 引用不准确         | 生成内容可能和引用不匹配       | 引用校验，必要时只要求核心内容带引用         |
| PPT 美观度不足     | python-pptx 模板能力有限       | MVP 强调可编辑初稿，不强调商业级设计         |
| 业务范围膨胀       | 容易扩展到学生问答、批改、推荐 | MVP 坚持教师备课主线                         |
| 知识库污染         | 未审核内容写回后影响后续生成   | 只有 approved 内容允许写回                   |

# 20. 项目成功标准

该项目的成功不以“功能数量多”为标准，而以以下能力为核心标准：

1.  是否围绕高校教师备课形成完整闭环；
2.  是否能基于私有课程资料生成可追溯内容；
3.  是否具备稳定的 workflow 编排；
4.  是否体现 plan-and-solve、ReAct-style tool use 和 reflection；
5.  是否有结构化输出、校验、重试和导出能力；
6.  是否能通过 docx / pptx 文件展示真实可用成果；
7.  是否能通过评估指标证明系统质量。

最终项目应能够清晰展示：

    课程资料输入
    → 私有知识库构建
    → 教学设计生成
    → PPT 初稿生成
    → 作业 / 试卷生成
    → 教师审核
    → 知识库动态更新

# 21. MVP 推荐开发里程碑

## Milestone 1：课程知识库基础能力

目标：完成课程创建、资料上传、文档解析、chunk 切分、向量检索。

交付物：

- 课程管理接口；
- 文件上传接口；
- 文档解析脚本；
- chunk metadata 结构；
- 向量检索 demo；
- 检索结果带引用来源。

## Milestone 2：教学设计生成能力

目标：完成教学设计生成主流程。

交付物：

- 教学设计参数配置；
- 课时规划节点；
- 教学设计生成节点；
- 教学设计 JSON schema；
- 教学设计校验器；
- 局部修改能力；
- 教学设计导出文件。

## Milestone 3：作业 / 试卷生成能力

目标：完成作业和试卷生成主流程。

交付物：

- 出题参数配置；
- 考点规划节点；
- 试卷 blueprint；
- 分题型生成节点；
- 题目 JSON schema；
- 题量、答案、重复度校验；
- docx 导出；
- 学生版、答案版、解析版、答题卡。

## Milestone 4：PPT 生成与审核闭环

目标：完成 PPT 初稿生成和知识库动态更新。

交付物：

- PPT 大纲生成；
- pptx 导出；
- 教师审核状态流转；
- approved 内容写回知识库；
- 历史记录页面；
- 基础评估统计。

# 22. 简历呈现建议

项目完成后可概括为：

基于 FastAPI、LangGraph、RAG、向量数据库和文档生成工具，构建面向高校教师备课场景的 Teacher Assistant Agent 系统。系统支持教材/课程大纲上传、私有课程知识库构建、教学设计生成、PPT 初稿生成和作业/试卷生成。采用 workflow-first 架构，将教学设计、PPT 生成和试卷生成拆解为可控 Agent 子图，并在关键节点引入 plan-and-solve、ReAct-style tool use 和 reflection 校验机制。设计题型分流生成、考点规划、结构化输出、格式校验、题量校验、重复度检测、引用溯源和教师审核写回机制，实现课程资料到教学资源产出的闭环。
