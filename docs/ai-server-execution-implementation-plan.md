# AI Server 执行落地文档

Status: Draft for execution  
Date: 2026-08-03  
Basis:

- `/Users/qmk/Documents/opc/HireOS开发依据/05_AI_SERVER设计与验证方案.md`
- `/Users/qmk/Documents/opc/HireOS/hireOsBe/docs/ai-server-phase-1-readonly-query-spec.md`

## 1. 落地目标

本阶段目标不是继续扩展概念设计，而是把 AI Server 做成可开发、可测试、可验收的后端能力。

优先打通两条闭环：

1. 只读查询闭环：自然语言输入 -> 对象解析 -> Platform 只读查询 -> 证据答案。
2. 动作确认闭环：自然语言执行请求 -> ProposedAction -> 用户确认 -> Platform Action API -> Audit。

## 2. 已定技术方案

| 领域 | 已定方案 | 落地说明 |
| --- | --- | --- |
| Agent 编排 | LangChain Agent 为主，Semantic Kernel 做验证对照 | LangChain 负责 tool orchestration；Semantic Kernel 只做验证，不阻塞主链路 |
| RAG / 检索 | pgvector + OpenSearch / Elasticsearch + LlamaIndex | 结构化业务状态仍走 Platform Query API；RAG 只处理非结构化证据召回 |
| 异步执行 | Platform 同步 Action API | P1 阶段用户确认后同步写回；外部副作用和长耗时任务后续进入 Worker |
| 模型调用 | Model Gateway | Agent 模块不得直接调用模型供应商 SDK |
| 状态持久化 | Platform 持久化 Conversation / AgentTurn / ProposedAction | Redis 只做缓存，不做事实源 |

## 3. 系统边界

### 3.1 AI Service 负责

- `/agent-command/turn` 统一入口。
- Query Intent 解析。
- Context Resolver。
- Platform Read tool 调用。
- Evidence answer 生成。
- ProposedAction 生成。
- 用户确认后调用 Platform Action API。
- LangChain tool orchestration。
- Semantic Kernel 对照验证。

### 3.2 Platform API 负责

- 租户、用户、权限。
- `agent-read` 只读查询接口。
- `agent-actions` 写操作接口。
- Workflow 状态机校验。
- Conversation / AgentTurn / ProposedAction 持久化。
- Audit Event 写入。

### 3.3 RAG / 检索层负责

- Evidence Chunk 数据模型。
- pgvector 向量索引。
- OpenSearch / Elasticsearch 全文索引。
- LlamaIndex ingestion / retriever / citation mapping。
- 非结构化证据召回，不承担业务状态事实源。

## 4. 模块拆解

### 4.1 AI Service 模块

| 模块 | 文件建议 | 职责 |
| --- | --- | --- |
| Agent Command Router | `app/agent_command/router.py` | 暴露 `/agent-command/turn` 和 `/agent-command/confirm` |
| Schemas | `app/agent_command/schemas.py` | 定义请求、响应、QueryIntent、EvidenceReference、ProposedAction |
| Intent Router | `app/agent_command/intent_router.py` | 将自然语言解析成 operation / object / metric / filters |
| Context Resolver | `app/agent_command/context_resolver.py` | 调 Platform Read API 搜索对象、处理歧义 |
| Query Planner | `app/agent_command/query_planner.py` | 生成 Platform query payload |
| Answer Composer | `app/agent_command/answer_composer.py` | 根据 evidence 生成回答 |
| Action Planner | `app/agent_command/action_planner.py` | 生成 ProposedAction，不写回 |
| Platform Client | `app/agent_command/platform_client.py` | 调 Platform Read / Action API |
| LangChain Adapter | `app/agent_command/langchain_adapter.py` | 将 Platform Read、RAG、Action Preview 包成 tools |
| Semantic Kernel Adapter | `app/agent_command/semantic_kernel_adapter.py` | 做 skill/planner 表达验证 |

### 4.2 Platform API 模块

| 模块 | 文件建议 | 职责 |
| --- | --- | --- |
| Agent Read Controller | `src/agent-read/agent-read.controller.ts` | 对象解析和只读查询 |
| Agent Read Service | `src/agent-read/agent-read.service.ts` | 权限内查询 Job / Candidate / Application / Task |
| Agent Actions Controller | `src/agent-actions/agent-actions.controller.ts` | 确认后执行动作 |
| Agent Actions Service | `src/agent-actions/agent-actions.service.ts` | 调 Workflow / Audit 完成状态推进和任务创建 |
| Agent State Module | `src/agent-state/` | Conversation / AgentTurn / ProposedAction 持久化 |

## 5. 接口契约

### 5.1 AI Service: Agent Turn

`POST /agent-command/turn`

输入：

```json
{
  "conversation_id": "conv_001",
  "message": "用户自然语言输入",
  "actor": {
    "tenant_id": "tenant_001",
    "actor_id": "user_001",
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

输出：

```json
{
  "turn_id": "turn_001",
  "mode": "readonly",
  "query_intent": {
    "operation": "summarize",
    "business_object": "Application",
    "metric_or_attribute": "current_profile_and_stage",
    "filters": [],
    "time_range": "current",
    "evidence_requirement": "required"
  },
  "answer": "基于证据生成的回答",
  "resolved_context": {},
  "evidence": [],
  "clarification_required": false,
  "clarification_question": null,
  "proposed_actions": []
}
```

### 5.2 Platform API: Read Query

`POST /agent-read/query`

输入：

```json
{
  "query_intent": {
    "operation": "aggregate",
    "business_object": "Application",
    "metric_or_attribute": "count_by_stage",
    "filters": []
  },
  "page_context": {},
  "actor": {}
}
```

输出：

```json
{
  "result": {},
  "evidence": [
    {
      "source_type": "ApplicationAggregate",
      "source_id": "aggregate_001",
      "entity_type": "Job",
      "entity_id": "job_001",
      "summary": "聚合结果来源"
    }
  ]
}
```

### 5.3 Platform API: Confirm Action

`POST /agent-actions/confirm`

输入：

```json
{
  "conversation_id": "conv_001",
  "turn_id": "turn_001",
  "confirmed_action_ids": ["action_001"],
  "actor_id": "user_001"
}
```

输出：

```json
{
  "status": "success",
  "updated_objects": [],
  "audit_event_ids": []
}
```

## 6. 数据模型

### 6.1 Platform 持久化表

| 表 | 关键字段 | 用途 |
| --- | --- | --- |
| Conversation | id, tenant_id, owner_id, created_at, updated_at | 会话事实源 |
| AgentTurn | id, conversation_id, intent, answer, evidence, created_at | 每轮 AI 输出 |
| ProposedAction | id, turn_id, type, target_type, target_id, payload, status | 待确认动作 |
| EvidenceChunk | id, source_type, source_id, entity_type, entity_id, text, embedding_ref | RAG 证据切片 |

### 6.2 状态枚举

ProposedAction status:

- `proposed`
- `confirmed`
- `executed`
- `blocked`
- `failed`
- `cancelled`

## 7. 开发任务规划

### Phase A: 技术骨架与契约

| 编号 | 任务 | 产出 | 验收 |
| --- | --- | --- | --- |
| A1 | 定义 AI Service schemas | Pydantic schemas + tests | 覆盖 read / aggregate / summarize / explain / preview_action |
| A2 | 增加 agent_command router | `/agent-command/turn` mock | health 和 mock turn 测试通过 |
| A3 | Platform Client seam | Fake client + HTTP client interface | 单测可替换 fake |
| A4 | LangChain Adapter POC | Platform Read tool | Agent 能调用一个只读 tool |
| A5 | Semantic Kernel 验证 | skill/planner POC | 形成与 LangChain 的职责分工和对照结论 |

### Phase B: 只读查询闭环

| 编号 | 任务 | 产出 | 验收 |
| --- | --- | --- | --- |
| B1 | Platform `agent-read` 模块 | objects/search + query | 租户权限在 Platform 生效 |
| B2 | Context Resolver | resolved_context / clarification | 多匹配对象必须追问 |
| B3 | Query Planner | Platform query payload | 不生成写调用 |
| B4 | Answer Composer | answer + evidence | 关键结论都有 evidence |
| B5 | AI Service 测试 | 只读查询测试集 | 5 类能力覆盖通过 |

### Phase C: RAG / 检索闭环

| 编号 | 任务 | 产出 | 验收 |
| --- | --- | --- | --- |
| C1 | EvidenceChunk 模型 | Platform schema / migration | 证据可回溯业务对象 |
| C2 | pgvector 索引 | embedding pipeline | 可召回相似证据 |
| C3 | OpenSearch / Elasticsearch POC | 全文索引和过滤 | 支持关键词 + 对象过滤 |
| C4 | LlamaIndex pipeline | ingestion / retriever / citation | RAG 输出带 citation |

### Phase D: 动作预览与同步写回

| 编号 | 任务 | 产出 | 验收 |
| --- | --- | --- | --- |
| D1 | Action Planner | ProposedAction payload | 不直接写回 |
| D2 | Platform `agent-actions` | confirm endpoint | 状态机由 Platform 校验 |
| D3 | Audit 接入 | audit_event_ids | 用户确认和执行结果可追溯 |
| D4 | 失败处理 | blocked_reason / failed status | 失败不产生半更新 |

### Phase E: 前端接入

| 编号 | 任务 | 产出 | 验收 |
| --- | --- | --- | --- |
| E1 | HireAgent 对话接入 | answer / evidence 展示 | 用户可看到来源 |
| E2 | 澄清交互 | candidate options / job options | 歧义可闭环 |
| E3 | 动作确认 UI | ProposedAction preview + confirm | 确认后显示结果 |
| E4 | 端到端验收 | Playwright / API tests | 查询、歧义、动作确认全链路通过 |

## 8. 第一轮最小切片

第一轮只做 P0，不接真实 RAG，不做真实状态推进。

范围：

1. AI Service `/agent-command/turn`。
2. Platform fake read client。
3. Intent Router 规则版。
4. Context Resolver fake 数据。
5. Answer Composer 返回 evidence。
6. 动作请求只返回 ProposedAction，不执行。

验收：

- 自然语言查询可返回 answer + evidence。
- 单对象可解析。
- 多对象返回澄清。
- 动作请求返回 ProposedAction。
- 不产生任何写操作。

## 9. 测试要求

| 层级 | 测试 |
| --- | --- |
| AI Service unit | intent router、context resolver、query planner、action planner |
| AI Service API | `/agent-command/turn` |
| Platform unit | agent-read、agent-actions、audit |
| Contract | AI Service 和 Platform payload schema |
| Frontend | answer / evidence / clarification / confirmation |

## 10. 明确不做

- 不让 AI Server 直连数据库。
- 不让 Agent 直接调用模型 SDK。
- 不让 RAG 替代业务状态查询。
- 不在 P0 执行真实写回。
- 不在 P0 接入额外复杂工作流引擎。
