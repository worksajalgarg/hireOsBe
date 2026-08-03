# HireOS AI Server 设计与验证方案

Document ID: HIREOS-AI-SERVER-VALIDATION-001  
Version: v1.2  
Date: 2026-08-03  
Status: 开发依据

## 1. 定位

AI Server 是 HireOS 的自然语言业务操作层，承接 HireAgent、Agent Retrieval 和 AI Command 的后端能力。它不是独立招聘业务系统，也不直接替代 Platform API、Workflow Engine 或数据库。

一句话定义：

AI Server 负责把用户自然语言转换为可解释、可引用、可确认、可审计的查询结果、业务建议和待执行动作。

在现有 HireOS 架构中：

- Web Frontend 负责用户交互、对话工作区、任务页和结果展示。
- Platform API 负责业务对象、权限、任务流转、状态写回和审计。
- AI Service / AI Server 负责意图识别、上下文解析、模型调用、Agent 推理、查询规划和动作计划。
- Worker / Async Jobs 负责异步导入、批处理、重试和自动任务。
- Data Layer 负责 Postgres、pgvector、Redis、对象存储、全文/向量索引。

## 2. 产品级业务场景

AI Server 需要覆盖三类核心场景。这里描述的是“场景族”和“通用能力”，不是固定岗位、固定候选人、固定页面或固定句式。

### 2.1 查询

用户通过自然语言查询招聘状态、候选人数量、任务进展或业务对象详情。

通用语义：

`read / aggregate + Job / Candidate / Application / WorkflowTask + status / count / time / owner / next_action + filters`

输出要求：

- 返回结构化答案。
- 标明引用来源，例如 Job、Candidate、Application、Task、Audit Event。
- 对不确定对象先追问。
- 查询不产生业务写回。

### 2.2 分析与建议

用户要求 AI 解释现状、总结候选人、指出风险或建议下一步。

通用语义：

`summarize / explain / compare + Candidate / Application / Job / Interview / Assessment + evidence / risk / missing_evidence / next_action + filters`

输出要求：

- 区分事实、推测和建议。
- 所有结论尽量绑定证据。
- 输出 supporting_evidence、missing_evidence、risks、next_actions。
- 不输出最终录用或拒绝决定。
- 建议动作必须来自当前业务状态允许的动作集合。

### 2.3 功能执行

用户通过自然语言请求推进状态、创建任务、更新内容或准备业务动作。

通用语义：

`preview_action + target object + desired action / desired state / patch intent + filters`

输出要求：

- Agent 先生成动作计划，不直接执行。
- 展示影响对象、状态变化前后、写回目标和风险。
- 用户确认后才调用 Platform API。
- 所有写操作必须写 Audit Event。
- 执行结果必须返回明确反馈，例如新状态、创建的任务、下一步入口。

## 3. 核心设计原则

### 3.1 查询可以直接返回，执行必须确认

查询和解释是只读行为，可以直接回答。任何改变 Job、Candidate、Application、Task、Interview、Assessment、Offer 或 Audit 的动作，都必须进入待确认动作计划。

### 3.2 AI Server 不直接写数据库

AI Server 不绕过 Platform API，不直接改数据库，不直接推进 Workflow 状态。写操作只能通过 Platform API 的受控接口执行。

### 3.3 Workflow Engine 是状态流转裁判

AI Server 可以提出 advance_application_stage 等动作，但是否合法由 Platform API / Workflow Engine 校验。Agent 不能跳过状态机。

### 3.4 Human Decision Layer 是责任边界

AI 可以建议 Shortlist、Need More Info、Next Round、Reject draft，但敏感招聘决策必须由人类确认。AI 输出应成为证据和建议，不成为最终责任主体。

### 3.5 每个结论和动作都需要来源

候选人摘要、岗位状态、推荐理由、风险提示和动作计划都应带引用来源。来源可以是 Candidate、Application、Interview Record、Assessment、Task、Audit Event、文件证据或用户对话。

### 3.6 歧义先澄清

当候选人、岗位、当前 Application、目标阶段或页面上下文存在歧义时，Agent 必须先追问或给出候选对象列表，不能直接执行。

### 3.7 权限与租户隔离优先

所有查询和动作计划都必须在租户、角色、可见对象范围内进行。AI Server 不得通过检索绕开 Platform API 的权限边界。

## 4. 能力模块

### 4.1 Intent Router

职责：

- 判断用户输入属于查询、分析、内容生成、内容修改、动作执行、确认执行或普通对话。
- 给后续模块提供稳定的 intent 和 confidence。

典型输出：

- query_status
- analyze_candidate
- create_or_update_artifact
- propose_action
- confirm_action
- clarify_context

### 4.2 Context Resolver

职责：

- 解析自然语言里的业务对象。
- 将用户文本和页面上下文映射到 Job、Candidate、Application、Task 等业务对象。
- 判断是否存在多候选对象或缺失上下文。

输出：

- resolved_context
- ambiguity
- clarification_question
- candidate_options

### 4.3 Retrieval / Query Planner

职责：

- 将自然语言查询转换为受控查询计划。
- 调用 Platform API 的读取接口，而不是直接访问数据库。
- 返回结构化数据和引用来源。

查询对象：

- Job / Role Context
- Candidate
- Application
- Workflow Task
- Interview Record
- Assessment
- Offer
- Audit Event
- Dashboard Metrics

### 4.4 Agent Reasoning

职责：

- 对查询结果进行摘要、解释、风险识别和下一步建议。
- 输出证据引用、缺失证据和建议动作。
- 对 JD、CV、Matching、Interview、Assessment、Decision 等场景调用对应 Agent 能力。

### 4.5 Action Planner

职责：

- 将用户请求转换为待确认动作计划。
- 标明动作类型、影响对象、前后状态、需要确认的原因、失败风险和写回目标。

典型动作：

- advance_application_stage
- create_task
- update_job_context
- update_jd_draft
- mark_candidate_need_info
- shortlist_application
- reject_application
- schedule_interview_task
- record_interview_result

### 4.6 Action Executor

职责：

- 在用户确认后调用 Platform API。
- 不自行判断状态机合法性，由 Platform API / Workflow Engine 校验。
- 处理执行结果、失败回滚提示和审计返回。

## 5. 技术选型与落地方案

本节只保留已经确定采用的落地方案。未选方案不再作为开发依据保留，避免实现阶段反复摇摆。

### 5.1 固定架构约束

| 约束项 | 固定方案 | 为什么不是选型 | 落地要求 |
| --- | --- | --- | --- |
| 业务数据读取边界 | AI Server 只能通过 Platform Read API 获取业务数据 | 这是租户、权限、业务口径边界，不是效率偏好 | 禁止 AI Server 直连业务库；Platform 提供 `objects/search` 和通用 `query` |
| 业务写回边界 | AI Server 只能通过 Platform Action API 发起写操作 | Workflow、状态机、审计责任必须在 Platform 侧闭环 | 禁止 AI Server 自己改 Job / Candidate / Application / Task |
| 模型调用边界 | 所有模型调用必须经过 Model Gateway | 已有架构红线；模型路由、fallback、审计、成本控制都依赖它 | Agent 模块不得直接 import OpenAI / Anthropic / Gemini SDK |
| 人类确认边界 | 状态推进、任务创建、内容写回等敏感动作必须先生成 ProposedAction | HireOS 的 Human Decision Layer 是产品责任边界 | 查询可直接返回；执行必须先计划、再确认、再写回 |
| 审计边界 | AI 输出、用户确认、状态变化都必须能进入 Audit Evidence Compliance | 招聘决策需要可追溯 | ProposedAction、执行结果、证据引用都要保留 |

### 5.2 已选落地方案

| 选型项 | 已选方案 | 落地方式 | 关键风险 | 控制方式 |
| --- | --- | --- | --- | --- |
| Agent 编排 | LangChain Agent 为主，Semantic Kernel 做验证对照 | LangChain 负责 tool orchestration；Semantic Kernel 用于验证 skill/planner 表达是否更适合业务能力沉淀 | Agent 框架容易吞掉业务边界 | Intent Router、Context Resolver、Query Planner、Action Planner 必须保留结构化接口 |
| RAG / 检索 | pgvector + OpenSearch / Elasticsearch + LlamaIndex | pgvector 承载向量证据；OpenSearch / Elasticsearch 承载全文检索和复杂过滤；LlamaIndex 负责编排 ingestion、retriever、citation mapping | 纯 RAG 容易替代业务状态查询口径 | 业务状态和数量仍走 Platform Query API；RAG 只负责非结构化证据召回 |
| 异步执行 | Platform 同步 Action API | 用户确认后由 AI Server 调 Platform Action API；Platform 校验状态机、写业务对象、写 Audit | 长耗时动作不适合同步 | P1 只处理短动作；外部副作用和长任务后续交给 Platform Worker |
| 会话状态 | Platform 持久化 Conversation / AgentTurn / ProposedAction，Redis 只做缓存 | Platform 作为事实源；AI Service 可短期缓存会话上下文和流式状态 | Redis 或内存状态不可审计 | 可审计数据必须落 Platform |

当前推荐组合：

- FastAPI AI Service + LangChain Agent / Semantic Kernel 方案验证；业务边界节点仍保持 Intent Router、Context Resolver、Query Planner、Action Planner 的结构化接口。
- Platform Read API 承担对象解析和结构化查询。
- Model Gateway 作为唯一模型出口。
- RAG / 检索采用 pgvector + OpenSearch / Elasticsearch + LlamaIndex 的组合：pgvector 承载向量证据，OpenSearch / Elasticsearch 承载全文检索和过滤，LlamaIndex 负责证据索引与 RAG pipeline 编排。
- 用户确认后调用 Platform Action API。
- Conversation / AgentTurn / ProposedAction 放 Platform 持久化，Redis 只做缓存。

暂不采用：

- AI Server 直连业务数据库。
- Agent 模块直接调用模型供应商 SDK。
- 纯向量 RAG 承担业务状态查询。
- AI Server 自行执行业务写逻辑。

## 6. 标准交互协议

### 6.1 统一请求

```json
{
  "conversation_id": "conv_001",
  "user_message": "用户请求将某个申请推进到目标阶段",
  "actor": {
    "tenant_id": "tenant_001",
    "actor_id": "user_hr_001",
    "role": "RECRUITER"
  },
  "page_context": {
    "current_page": "application_detail",
    "job_id": "job_001",
    "candidate_id": "candidate_001",
    "application_id": "application_001"
  }
}
```

### 6.2 查询或分析响应

```json
{
  "intent": "analyze_candidate",
  "answer": "目标候选人的当前申请处于面试后待决策状态，已有面试反馈支持进入下一步准备。",
  "resolved_context": {
    "candidate_id": "candidate_001",
    "application_id": "application_001",
    "job_id": "job_001"
  },
  "supporting_evidence": [
    {
      "source_type": "InterviewRecord",
      "source_id": "interview_001",
      "summary": "面试反馈记录支持当前判断"
    }
  ],
  "missing_evidence": [],
  "risks": [],
  "next_actions": [
    {
      "type": "advance_application_stage",
      "label": "推进到下一轮",
      "requires_confirmation": true
    }
  ]
}
```

### 6.3 待确认动作响应

```json
{
  "intent": "propose_action",
  "answer": "我理解你要把目标申请从当前阶段推进到目标阶段，需要你确认。",
  "resolved_context": {
    "candidate_id": "candidate_001",
    "application_id": "application_001",
    "current_stage": "CURRENT_STAGE"
  },
  "proposed_actions": [
    {
      "action_id": "act_advance_001",
      "type": "advance_application_stage",
      "from": "CURRENT_STAGE",
      "to": "TARGET_STAGE",
      "target_type": "Application",
      "target_id": "application_001",
      "requires_confirmation": true
    },
    {
      "action_id": "act_task_001",
      "type": "create_task",
      "task_type": "Next Workflow Task",
      "owner": "HR",
      "target_type": "Application",
      "target_id": "application_001",
      "requires_confirmation": true
    }
  ],
  "confirmation_required": true
}
```

### 6.4 确认执行请求

```json
{
  "conversation_id": "conv_001",
  "confirmed_action_ids": ["act_advance_001", "act_task_001"],
  "actor_id": "user_hr_001"
}
```

### 6.5 执行结果

```json
{
  "status": "success",
  "message": "目标申请已进入目标阶段，并已创建下一步任务。",
  "updated_objects": [
    {
      "type": "Application",
      "id": "application_001",
      "stage": "TARGET_STAGE"
    },
    {
      "type": "Task",
      "id": "task_next_interview_001",
      "task_type": "Next Workflow Task"
    }
  ],
  "audit_event_ids": ["audit_001", "audit_002"]
}
```

## 7. 与现有 HireOS 模块的关系

| HireOS 模块 | 与 AI Server 的关系 |
| --- | --- |
| HireAgent Workspace | 用户自然语言入口，承载对话、查询结果、建议和确认动作 |
| Agent Retrieval | 跨对象检索、证据召回和上下文整理能力，由 AI Server 编排 |
| Tasks OS | 状态改变后的执行入口和任务承接面 |
| Workflow & Task Engine | 判断动作是否合法，创建任务，推进状态 |
| Job & Role Context | JD、Role Brief、Scorecard、招聘计划的保存和版本管理 |
| Candidate & Application | 候选人档案、申请状态、阶段推进和证据归属 |
| Interview / Assessment | 面试记录、评估记录、下一轮建议和证据输入 |
| Audit Evidence Compliance | 记录 AI 输出、人类确认、状态变化和证据链 |
| Dashboard | 查询聚合指标和招聘健康状态 |
| Settings | Prompt、AI 策略、Workflow 规则和权限配置 |

## 8. 技术验证路径

### Phase 1: 只读查询验证

目标：证明 Agent 能正确理解招聘数据并返回可引用答案。

验证场景族：

- 招聘进展状态查询。
- 聚合数量查询。
- 单对象摘要查询。
- 待办和异常查询。
- 上下文歧义处理。

验收标准：

- 能识别 Job、Candidate、Application、Task。
- 查询结果有来源引用。
- 对歧义对象会追问。
- 不产生任何写操作。
- 不跨租户、不越权。

### Phase 2: 解释与建议验证

目标：证明 Agent 能基于证据给出业务解释和下一步建议。

验证场景族：

- 候选人证据解释。
- 岗位进展阻塞原因解释。
- 候选人质量和风险摘要。
- 证据缺口识别。
- 下一步建议生成。

验收标准：

- 区分事实、推测和建议。
- 输出 supporting_evidence、missing_evidence、risks。
- 不输出最终录用或拒绝决定。
- next_actions 来自 allowed_actions。

### Phase 3: 待确认动作验证

目标：证明 Agent 能把自然语言转换为安全的业务动作计划。

验证场景族：

- 推进候选人申请阶段。
- 标记候选人需要补充资料。
- 创建面试或下一步任务。
- 更新岗位或 JD 内容草稿。
- 暂停、恢复或调整招聘流程。

验收标准：

- 返回动作计划，不直接执行。
- 展示影响对象、状态变化前后和写回目标。
- 高风险动作必须要求确认。
- 歧义时必须追问。

### Phase 4: 确认后写回验证

目标：证明 AI Server、Platform API、Workflow Engine、Audit 的闭环成立。

确认后执行：

- 更新 Application 状态。
- 创建下一轮 Task。
- 写入 Interview / Assessment 结果。
- 记录 Audit Event。
- 返回 Toast / 成功反馈。
- 前端页面同步刷新。

验收标准：

- 所有写操作只通过 Platform API。
- Workflow 状态合法流转。
- Audit Event 记录 actor、原状态、新状态、证据、Agent 推荐和用户确认。
- 执行失败时不产生半更新。
- 用户能看到明确结果。

## 9. 推荐最小 POC

先做三条代表性能力链路，不先覆盖所有招聘动作。每条链路用可替换 fixture 数据验证，不能依赖固定姓名、固定岗位或固定句式。

### 9.1 聚合查询链路

输入类型：

- 任意岗位、阶段、Owner 或时间范围下的数量和分布查询。

验证：

- 解析查询范围。
- 查询候选人和 Application 数量。
- 返回总数、分阶段数量、引用来源。

### 9.2 单对象摘要链路

输入类型：

- 任意候选人、申请、岗位或任务的现状摘要查询。

验证：

- 解析目标业务对象和当前上下文。
- 汇总 Candidate、Application、Interview、Assessment、Task。
- 输出摘要、证据、风险、缺失项、建议动作。

### 9.3 动作预览链路

输入类型：

- 任意合法业务对象上的状态推进、内容修改或任务创建请求。

验证：

- 解析 Candidate / Application。
- 校验当前阶段。
- 生成待确认动作。
- 用户确认后调用 Platform API。
- 更新状态、创建任务、写审计。

## 10. 最小数据契约

### 10.1 Agent Turn

```json
{
  "turn_id": "turn_001",
  "conversation_id": "conv_001",
  "intent": "propose_action",
  "user_message": "用户自然语言输入",
  "resolved_context": {},
  "answer": "",
  "supporting_evidence": [],
  "missing_evidence": [],
  "risks": [],
  "proposed_actions": [],
  "confirmation_required": true,
  "created_at": "2026-08-03T00:00:00+08:00"
}
```

### 10.2 Proposed Action

```json
{
  "action_id": "act_001",
  "type": "advance_application_stage",
  "target_type": "Application",
  "target_id": "application_001",
  "from": "CURRENT_STAGE",
  "to": "TARGET_STAGE",
  "requires_confirmation": true,
  "allowed": true,
  "blocked_reason": null
}
```

### 10.3 Evidence Reference

```json
{
  "source_type": "InterviewRecord",
  "source_id": "interview_001",
  "entity_type": "Application",
  "entity_id": "application_001",
  "summary": "业务证据摘要",
  "confidence": "high"
}
```

## 11. 测试清单

### 11.1 意图识别

- 查询岗位状态。
- 查询候选人情况。
- 询问原因和建议。
- 请求推进候选人阶段。
- 确认执行动作。
- 普通闲聊。

### 11.2 上下文解析

- 单一匹配对象能正确解析。
- 多个相似匹配对象时必须追问。
- 岗位别名能映射到 Job。
- 缺少 Application 时必须追问。
- 当前页面上下文优先于全局搜索，但不能越权。

### 11.3 查询与证据

- 返回结果包含 source_type 和 source_id。
- 无结果时给出明确空状态。
- 查询不产生 Audit 写操作。
- 无权限对象不可见。

### 11.4 动作计划

- 状态推进必须包含 from / to。
- 创建任务必须包含 owner、task_type、target_id。
- 高风险动作必须 requires_confirmation=true。
- 非法状态流转返回 blocked_reason。

### 11.5 执行与审计

- 确认后才调用 Platform API 写操作。
- 执行成功写 Audit Event。
- 执行失败不产生半更新。
- 返回前端 Toast 文案和更新对象。

## 12. 开发顺序建议

1. 定义 Agent Turn、Evidence Reference、Proposed Action 的数据契约。
2. 在 AI Service 增加统一 Agent Command 入口。
3. 在 Platform API 增加受控只读查询接口。
4. 实现只读查询链路。
5. 实现候选人解释链路。
6. 实现动作计划链路。
7. 实现确认后执行链路。
8. 接入 Audit Event。
9. 接入前端 HireAgent 工作区。
10. 扩展到 JD、CV、Interview、Assessment、Offer 等场景。

## 13. 任务规划

### 13.1 Phase A: 技术骨架与契约

| 任务 | 产出 | 依赖 | 验收 |
| --- | --- | --- | --- |
| A1 定义 Agent Command 契约 | `AgentTurnRequest`、`AgentTurnResponse`、`QueryIntent`、`EvidenceReference`、`ProposedAction` | 05 号开发依据 | 契约能覆盖 read / aggregate / summarize / explain / preview_action |
| A2 建立 AI Service 模块骨架 | `agent_command` router、service、schemas、tests | FastAPI AI Service | `/agent-command/turn` 可返回 mock 响应 |
| A3 接入 Model Gateway 调用边界 | use_case、prompt payload、response schema | 现有 Model Gateway | Agent 模块不直接 import 模型 SDK |
| A4 引入 LangChain Agent / Semantic Kernel 验证层 | tool adapter POC、方案对比记录 | A1 / A2 | 至少一个 Platform Read tool 可被 Agent 调用；保留结构化 fallback |

### 13.2 Phase B: 只读查询与对象解析

| 任务 | 产出 | 依赖 | 验收 |
| --- | --- | --- | --- |
| B1 Platform Read API | `objects/search`、`query` 只读接口 | Platform API | 权限和租户校验在 Platform 生效 |
| B2 Context Resolver | 对象解析、歧义候选、澄清问题 | B1 | 多匹配对象不擅自选择 |
| B3 Query Planner | read / aggregate 查询计划 | A1 / B1 | 不生成写调用；查询结果带 evidence |
| B4 Answer Composer | 自然语言答案 + evidence 引用 | B3 | 关键结论都有来源 |

### 13.3 Phase C: RAG / 检索层

| 任务 | 产出 | 依赖 | 验收 |
| --- | --- | --- | --- |
| C1 证据数据模型 | Evidence Chunk、source_type、source_id、entity_ref | Candidate / Interview / Assessment 数据 | 每条证据可回溯业务对象 |
| C2 pgvector 向量索引 | embedding、vector column、相似度查询 | Postgres / pgvector | 可召回简历、面试、评估文本证据 |
| C3 OpenSearch / Elasticsearch 评估 | 全文索引、过滤、排序 POC | 文本数据规模评估 | 能处理关键词、阶段、对象过滤组合 |
| C4 LlamaIndex pipeline | ingestion、retriever、citation mapping | C1 / C2 / C3 | RAG 输出必须带 citation，不替代结构化状态查询 |

### 13.4 Phase D: 动作预览与同步执行

| 任务 | 产出 | 依赖 | 验收 |
| --- | --- | --- | --- |
| D1 Action Planner | ProposedAction 生成、from/to、target、risk | A1 / B2 | 执行动作不直接写回 |
| D2 Platform Action API | 状态推进、任务创建、内容写回接口 | Workflow / Audit | 状态机由 Platform 校验 |
| D3 Confirmation Executor | 用户确认后调用 Platform Action API | D1 / D2 | 成功返回 updated_objects 和 audit_event_ids |
| D4 失败处理 | blocked_reason、partial failure 防护 | D2 / D3 | 执行失败不产生半更新 |

### 13.5 Phase E: 前端与验收

| 任务 | 产出 | 依赖 | 验收 |
| --- | --- | --- | --- |
| E1 HireAgent 接入 | 对话入口、answer、evidence 展示 | A2 / B4 | 用户可看到答案和引用来源 |
| E2 澄清交互 | 候选对象列表、追问、重新解析 | B2 | 歧义场景可闭环 |
| E3 动作确认 UI | ProposedAction preview、确认按钮、结果反馈 | D1 / D3 | 用户确认后看到状态和下一步任务 |
| E4 自动化测试 | AI Service tests、Platform tests、前端交互测试 | 全链路 | 覆盖查询、摘要、歧义、动作预览、确认执行 |

### 13.6 优先级

| 优先级 | 工作 |
| --- | --- |
| P0 | A1-A3、B1-B4：打通只读查询和证据答案 |
| P1 | D1-D3、E1-E3：打通动作预览、确认和同步写回 |
| P2 | C1-C4、D4、E4：接入 RAG、全文/向量检索和完整验收 |
| P3 | 后续复杂编排和长事务能力另行立项评估 |

## 14. 当前阶段边界

当前阶段只把 AI Server 作为开发依据设计，不代表所有模块已在代码中实现。

已具备的代码基础：

- FastAPI AI Service 骨架。
- Model Gateway 边界。
- Use Case Policy。
- Role Intelligence / JD Agent 初步接口。
- Platform API 的 Tenant、User、Audit 基础能力。

仍需实现：

- Agent Command 统一入口。
- Context Resolver。
- Platform 受控查询接口。
- Workflow 状态流转接口。
- Candidate / Application 数据模型。
- Proposed Action 持久化。
- Confirmation 执行接口。
- 审计链路和前端确认交互。
