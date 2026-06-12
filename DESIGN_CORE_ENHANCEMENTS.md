# Agent Contest - 核心能力增强设计文档

**版本**: 2.0  
**日期**: 2026-06-12  
**状态**: 已实施

---

## 1. 背景与动机

### 1.1 比赛评分机制

比赛答案检查有 **4 种严格匹配类型**：

| 匹配类型 | 要求 | 偏差后果 |
|----------|------|----------|
| **精确匹配** | 字符级完全一致 | 多一个空格 = 零分 |
| **精确字段匹配** | JSON 字段名和值必须精确 | 字段顺序错 = 零分 |
| **列表精确匹配** | 列表元素完全一致 | 顺序错/有重复 = 零分 |
| **部分匹配** | 包含关键内容即可 | 相对宽松 |

**核心痛点**：LLM 生成的答案格式不稳定，即使"答对"也可能因格式问题得零分。

### 1.2 调研结论（2026-06）

基于 4 个并行调研 agent 的发现：

| 调研方向 | 关键发现 | 我们的决策 |
|----------|----------|------------|
| Self-iteration | Reflect-and-Retry 模式最优 | 加自检步骤到现有循环 |
| Answer formatting | Format-first design + RFC 8785 JCS | answer_formatter 工具 + System Prompt |
| MCP ecosystem | 官方 servers 可复用，但需包装 | 暂不集成，优先自有工具 |
| Skill design | SWE-Skills-Bench: 80% skill 零提升 | 聚焦核心能力 |

---

## 2. 核心改动

### 2.1 改动 1: `answer_formatter` 工具

**目标**：确定性格式化答案，不依赖 LLM。

**位置**：`source/solution/mcp/contestant_tools.py`

**6 种 format_type**：
- `exact` - 去空白
- `json_canonical` - JSON 字段排序
- `list_canonical` - 列表排序去重
- `number` - 数字精度
- `field_extract` - 字段提取
- `regex_extract` - 正则提取

**实现**：纯 Python，try-except 降级到原文

### 2.2 改动 2: System Prompt 强化（ReAct 框架）

**目标**：在生成阶段预防格式错误 + 结构化推理。

**位置**：`source/solution/contestant_agent.py` → `SYSTEM_PROMPT`

**ReAct 流程**：
```
Thought → Action → Observation → 重复 → Answer
```

**关键原则**：
- 每次只调用一个工具
- 不重复调用相同参数
- 使用声明的文件路径
- 失败时分析原因

### 2.3 改动 3: 自检循环

**目标**：在返回答案前自动验证质量。

**位置**：`source/solution/contestant_agent.py` → `_run_native_tool_loop()`

**逻辑**：
```python
if not tool_calls:
    if content.strip():
        # 多一轮验证
        if step < max_iter - 1:
            final_answer = content  # 保存候选
            messages.append({"role": "user", "content": "自检：..."})
            continue
        # 第二轮：LLM 回复 VERIFIED 或新答案
        if content.upper() == "VERIFIED":
            return final_answer
        return self._clean_final_answer(content)
```

**配置**：
- `AGENT_DEMO_MAX_ITER=8`（默认）
- `AGENT_DEMO_TIMEOUT_SECONDS=600`（10 分钟）
- `AGENT_DEMO_STREAM=true`（流式输出）

---

## 3. Skills 体系

### 3.1 `data_analyzer`（自建）

**来源**：基于比赛需求自建  
**位置**：`source/solution/skills/data_analyzer/`

**能力**：
- CSV/JSON/Excel 多格式
- 智能聚合（SUM/AVG/COUNT/MIN/MAX）
- 自动格式检测
- 纯标准库实现（无 pandas 依赖）

### 3.2 `document_searcher`（集成）

**来源**：[Ansvar-Systems/Document-Index-MCP](https://github.com/Ansvar-Systems/Document-Index-MCP) (Apache-2.0)  
**位置**：`source/solution/skills/document_searcher/`

**能力**：
- SQLite FTS5 全文搜索
- BM25 排序
- 多文档索引
- 章节级检索

**适配**：
- 复制核心模块（fts.py, database.py, parsers/）
- 简化为同步接口
- 适配 stdin/stdout 协议

### 3.3 `mock_summary_skill`（示例）

**来源**：demo 内置  
**能力**：返回 mock 数据

---

## 4. Dashboard 系统

### 4.1 追踪系统

**位置**：`source/runtime/tracing.py`

**机制**：
- `ContextVar` 传播
- `QuestionTrace` 收集 spans
- 每个 span 包含：类型、参数、结果、耗时

### 4.2 Dashboard 生成

**位置**：`source/runtime/generate_dashboard.py`

**特性**：
- 自包含 HTML（嵌入数据）
- 暗色主题（LangSmith 风格）
- 4 个区域：Summary / Timeline / Questions / Capabilities
- 答案预览（80 字符）直接显示在 header

---

## 5. 测试验证

### 5.1 测试结果

| 测试 | 状态 | 耗时 |
|------|------|------|
| Mock 5 题 | ✅ 5/5 | 44.8s |
| 数据分析 3 题 | ✅ 3/3 | 52.2s |
| 复杂任务 1 题 | ✅ 1/1 | 97.2s |
| 压缩包 2 题 | ✅ 2/2 | 101.7s |
| Excel/CSV 2 题 | ✅ 2/2 | 104.2s |
| 嵌套 ZIP 1 题 | ✅ 1/1 | 41.8s |
| ReAct 简单测试 | ✅ 1/1 | 26.9s |
| 真实比赛题 1_1 | ✅ 1/1 | ~120s |

### 5.2 比赛覆盖

| 题目 | 覆盖 | 工具 |
|------|------|------|
| 1_1 日期提取 | ✅ | text_read_file + code_execute |
| 2_2 敏感扫描 | ✅ | zip_extract + tar_extract + code_execute |
| 2_3 Java 修复 | ✅ | code_execute |
| 2_1 数据清洗 | ✅ | csv_read + csv_aggregate + code_execute |
| 1_4 接口测试 | ⚠️ | http_request（需本地服务） |
| 3_3 IDE 问答 | ⚠️ | document_searcher + http_request（需服务） |

---

## 6. 已知问题

1. **路径解析**：Agent 容易尝试多种路径，System Prompt 已强化
2. **重复调用**：ReAct 框架已部分缓解
3. **超时控制**：复杂任务可能超过 10 分钟
4. **格式验证**：answer_formatter 作为兜底

---

## 7. 下一步

### 短期
- 测试更多真实比赛题
- 优化 System Prompt 减少重复调用
- 添加多源知识检索 Skill

### 长期
- 多模态图片理解
- 并行工具调用
- 长期记忆管理

---

## 8. 参考文档

- [README.md](README.md) - 项目总览
- [GUIDE.md](GUIDE.md) - 使用指南
- [CAPABILITY_GAP.md](CAPABILITY_GAP.md) - 能力差距
- [P0_TOOLS.md](P0_TOOLS.md) - P0 工具文档
- [GitHub](https://github.com/guihousun/Agent_competition)
