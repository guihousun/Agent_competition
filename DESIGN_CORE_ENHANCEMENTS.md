# Agent Contest - 核心能力设计文档

**版本**: 4.0
**日期**: 2026-06-12
**状态**: 已实施

---

## 1. 架构总览

```
main.py → BatchRunner
  ├── LocalMCPClient (工具调度 + 权限沙箱 + 路径解析)
  │     ├── 5 框架工具 (text_read_file, skill_*, agent_delegate)
  │     ├── 12 参赛工具 (csv, http, code, date, sql, image, formatter...)
  │     ├── 3 Skills (data_analyzer, document_searcher, huawei_coding_standard)
  │     └── 2 Sub-agents (answer_checker, data_reader)
  │
  ├── ContestantAgent (Plan → Execute → Verify)
  │     ├── Phase 1: 规划（内部推理，不输出）
  │     ├── Phase 2: 执行（工具调用）
  │     ├── Phase 3: 验证（answer_checker 清理 + 校验）
  │     └── Context Compression（自动 hook，LLM 摘要）
  │
  ├── Tracing (ContextVar, 零开销)
  └── Dashboard (单文件 HTML)
```

---

## 2. 核心流程

### 2.1 Plan → Execute → Verify 框架

**Phase 1: 规划**（内部，不输出）
- 题目类型判断（日期/API/代码/数据/审计/问答）
- 文件识别 + 数据量评估
- 执行步骤拆解
- 预期答案格式

**Phase 2: 执行**
- 按步骤调用工具
- 大文件先用 data_reader 预读
- 结果存入上下文

**Phase 3: 验证**（LangGraph 风格流水线）
```
候选答案 → answer_checker →
  ├─ overall_valid=true → 返回 cleaned_answer
  ├─ 格式问题 → 代码直接修复
  └─ 内容/逻辑错误 → 返回主循环修正（无上限）
```

### 2.2 answer_checker（验证 + 清理器）

**双重职责**：
1. **验证**：检查答案是否满足题目要求（格式、内容、排序、数值）
2. **清理**：从答案中去掉 Thought/Action/Observation 等推理文字

**返回格式**：
```json
{
  "overall_valid": true/false,
  "cleaned_answer": "清理后的纯净答案",
  "fix_suggestions": ["修改建议"],
  "summary": "一句话总结"
}
```

**设计原则**：主 agent 可以自由输出推理过程，answer_checker 统一负责清理。

### 2.3 data_reader（数据接口层）

**两阶段设计**：

阶段 1: `mode="overview"`（不做筛选）
```
→ 返回 schema、行数、字段、值域、关联、数据问题
→ 主 agent 基于全貌决定查什么
```

阶段 2: `mode="query"`（精确执行）
```
→ 主 agent 指定查询条件
→ data_reader 执行并返回结果（≤50 条）
```

**设计原则**：不猜、不筛、不假设——只负责"读"和"查"。

---

## 3. 工具体系（17 个）

### 3.1 框架工具（5 个）

| 工具 | 用途 |
|------|------|
| text_read_file | 读取小文件（<50 行） |
| skill_load | 加载 skill 说明 |
| skill_run | 执行 skill |
| skill_read_resource | 读取 skill 资源 |
| agent_delegate | 调用子代理 |

### 3.2 参赛工具（12 个）

| 工具 | 用途 |
|------|------|
| csv_read | 读取 CSV（支持路径解析） |
| csv_aggregate | CSV 聚合（SUM/AVG/COUNT/MIN/MAX） |
| code_execute | 执行 Python/Java/Node.js |
| http_request | HTTP 请求 |
| sql_query | SQLite 查询（SELECT only） |
| date_compute | 自然语言日期解析 |
| workday_calc | 工作日计算 |
| image_read | 图片读取（返回 base64） |
| answer_formatter | 答案格式化（6 种模式） |
| zip_extract | ZIP 解压 |
| tar_extract | TAR 解压 |
| mock_order_lookup | Mock 订单查询 |

### 3.3 路径解析

所有文件读取工具统一经过 `_resolve_allowed_file()`：
- 相对路径 → 基于 question_dir 解析
- 权限检查 → 只允许题目声明的文件
- 支持工具：text_read_file, csv_read, sql_query, zip_extract, tar_extract, image_read

---

## 4. 多模态支持

### 4.1 image_read 工具

```
读取图片 → 返回 base64 + __image__ 标记
         → Agent loop 检测标记
         → 注入 image_url 到下一轮 LLM 消息
         → LLM 直接"看到"图片
```

**支持格式**：PNG, JPG, JPEG, BMP, GIF, WebP
**大小限制**：10MB

### 4.2 消息注入

```python
if img_data.get("__image__"):
    messages.append({
        "role": "user",
        "content": [
            {"type": "text", "text": question},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        ],
    })
```

---

## 5. 上下文压缩

### 5.1 触发条件

- 估计 token > 200k 时自动触发
- 每次 LLM 调用前检查（自动 hook，主 agent 无感）

### 5.2 压缩策略

**保留**：system prompt + 最近 10 轮消息

**压缩**：旧消息 → LLM 生成详细摘要
- 保留每步操作结果
- 保留所有关键数据（ID、数值、状态）
- 保留工具返回的重要内容
- 保留已做出的决策
- 丢弃：重复内容、工具调用参数、失败重试中间步骤

**降级**：LLM 调用失败时，规则截断（保留前 2000 字符）

### 5.3 参数

| 参数 | 值 | 说明 |
|------|------|------|
| 触发阈值 | 200k token | 估计值 |
| 保留最近 | 10 轮 | 不压缩 |
| 目标 token | 150k | 压缩后 |
| 单条消息 | 2000 字符 | 传给 LLM |
| 总上下文 | 50k 字符 | 传给 LLM |

---

## 6. Skills

### 6.1 data_analyzer（自建）

CSV/JSON/Excel 多格式数据分析，支持聚合、筛选、汇总。

### 6.2 document_searcher（集成）

SQLite FTS5 全文搜索，BM25 排序，多文档索引。

### 6.3 huawei_coding_standard（自建）

华为编程规范查询，references/ 目录放规范文档，agent 通过 skill_read_resource 读取。

---

## 7. Dashboard

### 7.1 追踪系统

- `ContextVar` 传播（async 安全，零开销）
- `QuestionTrace` 收集 spans（llm_call / tool_call）
- Token 统计（prompt / completion）

### 7.2 Dashboard 生成

- 自包含 HTML（嵌入 traces.json）
- 暗色主题（LangSmith 风格）
- Summary Cards / Waterfall Timeline / Question Details / Agent Capabilities

---

## 8. 测试结果

| 题目 | 类型 | 耗时 | Prompt | Completion | 状态 |
|------|------|------|--------|------------|------|
| Mock 5 题 | 基础 | <10s | - | - | ✅ 5/5 全对 |
| 1_1 日期提取 | 文本+日期 | 30s | 31k | 1.7k | ✅ |
| 1_4 接口测试 | API 验证 | 67s | 395k | 2.1k | ✅ |
| 2_2 敏感扫描 | 压缩包+正则 | 35s | - | - | ✅ |
| 2_3 Java 修复 | 代码调试 | 63s | 93k | 3k | ✅ |
| 3_2 PO 审计 | 数据+合规 | 52s | 463k | 1.2k | ✅ |
| 3_3 IDE 问答 | DB+API+推理 | 106s | 329k | 4.8k | ✅ |
| 多模态图片 | 图片识别 | 3s | 16k | - | ✅ |

以上记录表示案例执行流程完成，不等同于官方答案全部正确；正式正确率必须与官方参考答案逐项比对。

---

## 9. 关键优化效果

| 优化项 | 之前 | 之后 | 效果 |
|--------|------|------|------|
| Completion tokens | 33k | 1.2k | -96% |
| PO 审计耗时 | 300s | 52s | -83% |
| 上下文膨胀 | 158 万 token | 46 万 | -71% |
| answer_checker | 硬编码脚本 | LLM 推理 | 泛化 |
| 数据读取 | 全文塞入 | data_reader 预读 | 隔离 |
| 压缩策略 | 无 | LLM 摘要 | 自动 |

---

## 10. 配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| MODEL_BASE_URL | - | 模型 API 地址 |
| MODEL_API_KEY | - | API Key |
| MODEL_NAME | - | 模型名称 |
| AGENT_DEMO_MAX_ITER | 100 | 最大迭代次数 |
| AGENT_DEMO_TIMEOUT_SECONDS | 300 | 模型请求超时时间 |
| AGENT_DEMO_TOOL_OUTPUT_MAX_CHARS | 65536 | 单次工具结果写入模型历史的最大字符数 |
| AGENT_DEMO_STREAM | false | 流式输出 |

---

## 11. 参考

- [GitHub](https://github.com/guihousun/Agent_competition)
- [Dashboard 教程](docs/dashboard_tutorial.md)
