# AI Server Phase 1 只读查询验证规格

Status: Draft for implementation  
Date: 2026-08-03  
Basis: `/Users/qmk/Documents/opc/HireOS开发依据/05_AI_SERVER设计与验证方案.pdf`

## 1. 目标

Phase 1 只验证 AI Server 的只读查询能力：用户用自然语言询问招聘状态、岗位进展、候选人情况或待处理任务时，AI Server 能识别意图、解析上下文、调用受控读取接口，并返回带来源引用的答案。

本阶段不执行任何业务写回，不推进候选人状态，不创建任务，不更新 JD，不发送消息。

本文中的自然语言问题都只作为场景样例，用于说明一类通用能力，不代表只针对某个固定岗位、固定候选人、固定页面或固定句式开发。实现时应面向 Job、Candidate、Application、Task 等通用业务对象和意图类型。

## 2. 主业务链

`User Message -> Intent Router -> Context Resolver -> Query Planner -> Platform Read API -> Evidence Pack -> Natural Language Answer`

本阶段到 `Natural Language Answer` 结束。任何可能改变业务状态的请求，都只返回 `proposed_action_preview` 或提示“需要进入确认执行阶段”，不调用写接口。

## 3. 查询语义模型

Phase 1 不按具体问法枚举能力，而是把用户问题解析成一个通用查询语义模型：

`Query Intent = Operation + Business Object + Metric / Attribute + Filter + Time Range + Evidence Requirement`

示例：

- “某岗位的人招到了吗？” = `read + Job/Application + hiring_outcome_status + job filter + current + evidence`
- “某岗位现在有多少候选人？” = `aggregate + Application + candidate_count_by_stage + job filter + current + evidence`
- “某候选人现在怎么样？” = `summarize + Candidate/Application + current_profile_and_stage + candidate filter + current + evidence`

这几句话看起来不同，但不应该变成三个独立功能；它们只是同一套查询模型里的不同组合。

### 3.1 Operation

| Operation | 含义 | Phase 1 处理方式 |
| --- | --- | --- |
| `read` | 读取某个对象的当前状态或字段 | 只读 |
| `aggregate` | 统计数量、分布、阶段、列表 | 只读 |
| `summarize` | 总结对象现状、最近进展、关键证据 | 只读 + 证据摘要 |
| `compare` | 比较多个对象或阶段差异 | 只读，复杂比较可返回部分能力 |
| `explain` | 解释某个状态、建议或风险的原因 | 只读 + 证据引用 |
| `preview_action` | 用户表达了执行意图，但尚未确认 | 只生成动作预览，不执行 |

### 3.2 Business Object

| Business Object | 说明 | Phase 1 处理方式 |
| --- | --- | --- |
| `Job` | 岗位、JD、Role Context、招聘目标 | 只读 |
| `Candidate` | 候选人主体档案 | 只读 |
| `Application` | 候选人针对某岗位的申请和流程状态 | 只读 |
| `WorkflowTask` | 人类待办、异常任务、下一步动作 | 只读 |
| `Interview` | 面试安排、反馈、结果记录 | 只读 |
| `Assessment` | 笔试、评分、Rubric 评估记录 | 只读 |
| `Offer` | Offer 状态和审批记录 | 只读 |
| `AuditEvent` | AI 输出、人类确认、状态变化和证据链 | 只读引用，不新增 |

### 3.3 Metric / Attribute

| 类别 | 例子 | 说明 |
| --- | --- | --- |
| 状态类 | current_stage、hiring_status、task_status、offer_status | 回答“到哪一步了 / 是否完成 / 是否卡住” |
| 数量类 | total_count、count_by_stage、overdue_count、waiting_count | 回答“有多少 / 分布如何” |
| 时间类 | last_activity_at、due_at、days_in_stage、time_to_fill | 回答“多久没动 / 今天要处理什么” |
| 质量类 | evidence_strength、missing_evidence、risk_flags、match_score | 回答“情况怎么样 / 风险在哪里” |
| 责任类 | owner、waiting_on、next_action | 回答“谁要处理 / 下一步是什么” |

### 3.4 Filter

Filter 用来限定查询范围，而不是定义新功能。

常见 Filter：

- job title / job id
- candidate name / candidate id
- application id
- owner
- stage
- source channel
- status
- priority
- date range
- current page context

### 3.5 场景分类

| 场景 | 查询语义 | Phase 1 处理方式 |
| --- | --- | --- |
| 招聘进展查询 | `read / aggregate + Job/Application + status/count/time + filters` | 只读查询 |
| 候选人情况查询 | `summarize + Candidate/Application + status/evidence/risk + filters` | 只读 + 证据摘要 |
| 待办和异常查询 | `read / aggregate + WorkflowTask + owner/status/due_at + filters` | 只读查询 |
| 证据与原因查询 | `explain + Application/Interview/Assessment/AuditEvent + evidence/risk + filters` | 只读 + 证据引用 |
| 执行动作请求 | `preview_action + target object + desired state/action + filters` | 本阶段只生成动作预览，不执行 |
| 内容创建或修改请求 | `preview_action + Job/JD/Scorecard + patch intent + filters` | 本阶段只生成动作预览，不执行 |
| 上下文歧义 | 缺少对象、多个匹配、页面上下文冲突 | 返回澄清问题 |

## 4. Phase 1 接口

### 4.1 AI Server 统一查询入口

建议接口：

`POST /agent-command/turn`

请求：

```json
{
  "conversation_id": "conv_001",
  "message": "用户自然语言问题",
  "actor": {
    "tenant_id": "tenant_001",
    "actor_id": "user_hr_001",
    "role": "RECRUITER"
  },
  "page_context": {
    "current_page": "hire_agent",
    "job_id": null,
    "candidate_id": null,
    "application_id": null
  }
}
```

响应：

```json
{
  "turn_id": "turn_001",
  "query_intent": {
    "operation": "aggregate",
    "business_object": "Application",
    "metric_or_attribute": "count_by_stage",
    "filters": [
      {
        "type": "job",
        "value": "resolved_job_id"
      }
    ],
    "time_range": "current",
    "evidence_requirement": "required"
  },
  "mode": "readonly",
  "answer": "返回面向用户的自然语言答案，内容必须来自 evidence。",
  "resolved_context": {
    "job_id": "resolved_job_id",
    "candidate_id": null,
    "application_id": null
  },
  "evidence": [
    {
      "source_type": "Job",
      "source_id": "resolved_job_id",
      "summary": "用于回答的岗位来源"
    },
    {
      "source_type": "ApplicationAggregate",
      "source_id": "aggregate_result_id",
      "summary": "用于回答的聚合统计来源"
    }
  ],
  "clarification_required": false,
  "clarification_question": null,
  "proposed_action_preview": []
}
```

### 4.2 Platform 受控读取接口

AI Server 本阶段不直接访问数据库。Platform API 需要提供最小只读接口，后续可以再优化为更细粒度模块接口。

建议最小接口不要按每一种问法继续拆散，而是按“对象解析 + 只读查询”拆：

| 接口 | 用途 |
| --- | --- |
| `GET /agent-read/objects/search?type=&q=` | 解析 Job、Candidate、Application、Task 等业务对象 |
| `POST /agent-read/query` | 按 Query Intent 执行只读查询，支持 read / aggregate / summarize / explain |
| `GET /agent-read/context?current_page=&object_id=` | 读取当前页面上下文可见的业务对象 |

这些接口必须继承 Platform API 的租户和角色权限，不接受 AI Server 自行传入任意跨租户条件。

## 5. 节点契约

### 5.1 Intent Router

输入：

- 用户消息
- 页面上下文

输出：

- operation
- business_object
- metric_or_attribute
- filters
- evidence_requirement
- confidence
- mode: `readonly | action_preview`

验收：

- 招聘进展类问题能解析为 `read` 或 `aggregate`，对象通常是 `Job` / `Application`。
- 候选人情况类问题能解析为 `summarize`，对象通常是 `Candidate` / `Application`。
- 待办和异常类问题能解析为 `read` 或 `aggregate`，对象通常是 `WorkflowTask`。
- 证据与原因类问题能解析为 `explain`，并要求返回 evidence。
- 执行动作类请求能解析为 `preview_action`，本阶段不执行。

### 5.2 Context Resolver

输入：

- intent
- 用户消息
- 页面上下文
- Platform search 结果

输出：

- resolved_context
- ambiguity candidates
- clarification question

验收：

- 只有一个匹配对象时直接解析。
- 多个候选对象或多个相似岗位时返回澄清问题。
- 页面已有 `application_id` 时优先使用页面上下文。
- 页面上下文和用户消息冲突时返回澄清问题。

### 5.3 Query Planner

输入：

- intent
- resolved_context

输出：

- Platform read calls
- evidence pack

验收：

- 不生成写调用。
- 所有查询都有租户上下文。
- 查询为空时返回明确空状态。

### 5.4 Answer Composer

输入：

- intent
- evidence pack
- ambiguity state

输出：

- answer
- evidence references
- next readable suggestion

验收：

- 答案中不声称没有证据支持的事实。
- 每个关键结论至少有一个 evidence reference。
- 涉及执行动作时只显示“可进入确认执行”，不写回。

## 6. 验收用例

以下用例是能力覆盖类别，不是固定问法清单。每个类别可以派生大量自然语言表达，实际实现不得依赖固定姓名、固定岗位名或固定页面文案。

### Case 1: 招聘进展状态查询

Given 系统中存在任意 Job，且有 Application 数据。  
When 用户询问该岗位是否完成招聘、当前进展、是否有人进入 Offer / Hired。  
Then AI Server 返回岗位当前状态、候选人阶段分布、是否已有 Offer / Hired 状态。  
And 响应包含 Job 和 ApplicationAggregate 的 evidence。  
And 不产生任何写操作。

### Case 2: 聚合数量查询

Given 系统中存在任意 Job 或筛选条件。  
When 用户询问候选人数量、分阶段数量、待处理数量或超时数量。  
Then AI Server 返回候选人总数和分阶段数量。  
And 如果岗位名有多个匹配，返回澄清问题。

### Case 3: 单对象摘要查询

Given 系统中存在唯一匹配的 Candidate，且存在当前 Application。  
When 用户询问该候选人的情况、当前阶段、风险、缺失证据或下一步。  
Then AI Server 返回候选人摘要、当前申请阶段、最近任务、关键证据和缺失项。  
And 不输出最终录用或拒绝决定。

### Case 4: 上下文歧义处理

Given 系统中存在多个相似候选人、多个相似岗位，或页面上下文与用户文本冲突。  
When 用户的自然语言无法唯一定位对象。  
Then AI Server 返回候选项列表和澄清问题。  
And 不擅自选择一个对象。

### Case 5: 执行动作请求预览

Given 用户请求推进流程、修改内容、创建任务或改变业务状态。  
When 用户的自然语言表达包含目标对象和期望动作。  
Then AI Server 识别为动作请求。  
And Phase 1 只返回 `proposed_action_preview`。  
And 不调用 Platform 写接口，不创建 Audit Event。

## 7. 最小实现顺序

1. 在 AI Service 增加 `agent_command` 模块和 `POST /agent-command/turn`。
2. 先用规则实现 Intent Router，不急着依赖模型。
3. 定义 `AgentTurnResponse`、`EvidenceReference`、`ResolvedContext`、`ActionPreview`。
4. 在 AI Service 增加一个 Platform Read Client seam，先接内存 fake，再接 Platform HTTP。
5. 增加 Phase 1 的单元测试，覆盖 5 个验收用例。
6. 在 Platform API 增加最小 `agent-read` stub 或 fake fixtures。
7. 前端 HireAgent 先接 AI Service，展示 answer、evidence、clarification question。

## 8. 不在本阶段做

- 不做真实状态推进。
- 不创建任务。
- 不更新 JD。
- 不发送候选人消息。
- 不做 Offer / Reject 最终决策。
- 不做复杂向量检索。
- 不做多模型路由优化。

## 9. 后续 Phase 2 入口

Phase 1 验证通过后，Phase 2 增加解释与建议能力：

- candidate evidence summary
- missing evidence detection
- risks
- allowed next actions
- proposed action preview

Phase 3 再进入待确认动作计划；Phase 4 再做确认后写回。
