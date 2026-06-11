# Agent Contest - 核心能力增强设计文档

**版本**: 1.0  
**日期**: 2026-06-11  
**状态**: 实施中

---

## 1. 背景与动机

### 1.1 比赛评分机制

比赛答案检查有 **4 种严格匹配类型**：

| 匹配类型 | 要求 | 偏差后果 |
|----------|------|----------|
| **精确匹配** | 字符级完全一致（含标点、空格） | 多一个空格 = 零分 |
| **精确字段匹配** | JSON 字段名和值必须精确 | 字段顺序错 = 零分 |
| **列表精确匹配** | 列表元素完全一致 | 顺序错/有重复 = 零分 |
| **部分匹配** | 包含关键内容即可 | 相对宽松 |

**核心痛点**：LLM 生成的答案格式不稳定，即使"答对"也可能因格式问题得零分。

### 1.2 当前架构局限

```
ContestantAgent._run_native_tool_loop()
    ↓
最多 6 次迭代 (LLM → Tool → LLM)
    ↓
直接返回答案（无自检、无格式化）
```

**问题**：
- 无答案质量评估
- 无格式规范化
- 失败后无重试策略
- 固定 6 次迭代，不够灵活

### 1.3 调研结论（2026-06）

基于 4 个并行调研 agent 的发现：

| 调研方向 | 关键发现 | 我们的决策 |
|----------|----------|------------|
| Self-iteration | Reflect-and-Retry 模式最优 | 加自检步骤到现有循环 |
| Answer formatting | Format-first design + RFC 8785 JCS | answer_formatter 工具 + System Prompt |
| MCP ecosystem | 官方 servers 可复用，但需包装 | 暂不集成，优先自有工具 |
| Skill design | SWE-Skills-Bench: 80% skill 零提升 | 暂不做通用 Skill，聚焦核心能力 |

---

## 2. 核心改动设计

### 2.1 改动 1: `answer_formatter` 工具

**目标**：确定性格式化答案，不依赖 LLM。

**位置**：`source/solution/mcp/contestant_tools.py`

**工具签名**：
```python
@register_tool(name="answer_formatter")
def answer_formatter(
    raw_answer: str,
    format_type: str,
    options: dict | None = None
) -> str:
    """格式化答案为比赛要求的格式。
    
    format_type:
    - "exact": 精确匹配（去空白、统一换行）
    - "json_canonical": JSON 字段字母排序（用于字段匹配）
    - "list_canonical": 列表排序去重（用于列表匹配）
    - "number": 数字精度控制
    - "field_extract": 从复杂输出提取特定字段
    - "regex_extract": 正则提取关键内容
    """
```

**实现细节**：

```python
# exact 模式
def _format_exact(text: str) -> str:
    return text.strip()

# json_canonical 模式
def _format_json_canonical(text: str) -> str:
    data = json.loads(text)
    def sort_obj(obj):
        if isinstance(obj, dict):
            return {k: sort_obj(v) for k, v in sorted(obj.items())}
        elif isinstance(obj, list):
            return [sort_obj(i) for i in obj]
        return obj
    return json.dumps(sort_obj(data), ensure_ascii=False, indent=2)

# list_canonical 模式
def _format_list_canonical(text: str) -> str:
    items = json.loads(text)
    if isinstance(items, list):
        unique = list(set(str(i) for i in items))
        return json.dumps(sorted(unique), ensure_ascii=False)
    return text

# field_extract 模式
def _format_field_extract(text: str, options: dict) -> str:
    field = options.get("field")
    data = json.loads(text)
    return str(data.get(field, ""))

# regex_extract 模式
def _format_regex_extract(text: str, options: dict) -> str:
    pattern = options.get("pattern")
    match = re.search(pattern, text)
    return match.group(1) if match else text
```

**使用示例**：

```json
// 题目要求 JSON 字段匹配
{
  "tool": "answer_formatter",
  "arguments": {
    "raw_answer": "{\"supplier\": \"A\", \"amount\": 100}",
    "format_type": "json_canonical"
  }
}
// 输出：{"amount": 100, "supplier": "A"}  （字段按字母排序）

// 题目要求列表匹配
{
  "tool": "answer_formatter",
  "arguments": {
    "raw_answer": "[\"C\", \"A\", \"B\", \"A\"]",
    "format_type": "list_canonical"
  }
}
// 输出：["A", "B", "C"]  （排序 + 去重）
```

**风险评估**：
- ✅ 确定性代码，不依赖 LLM
- ✅ 纯标准库实现，无第三方依赖
- ⚠️ JSON 解析失败时返回原文（降级处理）

---

### 2.2 改动 2: System Prompt 强化

**目标**：在生成阶段预防格式错误。

**位置**：`source/solution/contestant_agent.py` → `SYSTEM_PROMPT`

**新增内容**：

```python
SYSTEM_PROMPT += """

【答案格式规则】（必须严格遵守，违反则不得分）

1. 只输出答案正文，不要：
   - 解释说明（"答案是..."、"根据分析..."）
   - Markdown 代码块（```json ... ```）
   - <think> 标签
   - 结果对象包装（{"answer": "..."}）

2. 根据题目类型选择格式：

   a) 精确匹配题：
      - 直接输出文本本身
      - ✓ mock-file-read-ok
      - ✗ "mock-file-read-ok"
      - ✗ 答案是：mock-file-read-ok

   b) JSON 字段匹配题：
      - 输出严格 JSON，字段按字母顺序排列
      - ✓ {"amount": 100, "supplier": "A"}
      - ✗ {"supplier": "A", "amount": 100}

   c) 列表匹配题：
      - 输出 JSON 数组，元素排序去重
      - ✓ ["A", "B", "C"]
      - ✗ ["C", "A", "B"]
      -  ["A", "B", "B", "C"]

   d) 数字答案：
      - 不要单位，不要千分位
      - 保留题目要求的精度
      - ✓ 1234.56
      -  1,234.56
      - ✗ 1234.56 元

3. 如果不确定格式，调用 answer_formatter 工具格式化

4. 最终输出前自检：
   - 是否有遗漏的字段？
   - 列表是否完整？
   - 数字精度是否正确？
"""
```

**设计原则**：
- 每种匹配类型都给出 ✓/✗ 示例（LLM 对示例敏感）
- 明确"不要做什么"（负面约束比正面约束更有效）
- 提供降级方案（不确定时调用 answer_formatter）

---

### 2.3 改动 3: 自检循环

**目标**：在返回答案前自动验证质量。

**位置**：`source/solution/contestant_agent.py` → `_run_native_tool_loop()`

**改动逻辑**：

```python
# 原代码（第 94-97 行）：
if not tool_calls:
    if content.strip():
        return self._clean_final_answer(content)

# 改为：
if not tool_calls:
    if content.strip():
        # 自检：多一轮验证
        if step < max_iter:
            messages.append({
                "role": "user", 
                "content": (
                    "自检：请验证上述答案是否满足题目要求。\n"
                    "检查点：\n"
                    "1. 是否直接回答了问题？\n"
                    "2. 是否满足格式要求？\n"
                    "3. 是否遗漏关键信息？\n"
                    "如果发现问题，继续调用工具修正；"
                    "如果确认无误，回复 VERIFIED。"
                )
            })
            continue  # 进入下一轮迭代
        return self._clean_final_answer(content)
```

**配套改动**：

```python
# env_config.py 新增配置项
AGENT_DEMO_MAX_ITER=8  # 从 6 增到 8（为自检留 2 轮）
```

**自检流程**：

```
第 1-6 轮：正常解题（LLM → Tool → LLM）
    ↓
第 7 轮：自检（LLM 评估答案质量）
    ↓ 发现问题
第 8 轮：修正（LLM 带着反馈重新解题）
    ↓
返回最终答案
```

**关键权衡**：
- ✅ 每次自检多消耗 1 次 API 调用
- ✅ 但能抓住大部分格式/遗漏错误
- ️ LLM 自检对事实性错误效果差（需要外部验证信号）

---

## 3. 实施计划

### Phase 1: answer_formatter 工具（1 小时）

**文件**：`source/solution/mcp/contestant_tools.py`

**步骤**：
1. 在文件末尾添加 `answer_formatter` 函数
2. 使用 `@register_tool` 装饰器注册
3. 实现 6 种 format_type 的格式化逻辑
4. 添加错误处理（JSON 解析失败 → 返回原文）
5. 测试验证（手动调用工具，检查输出）

**验收标准**：
- [ ] `answer_formatter("  hello  ", "exact")` → `"hello"`
- [ ] `answer_formatter('{"b": 2, "a": 1}', "json_canonical")` → `'{"a": 1, "b": 2}'`
- [ ] `answer_formatter('["C", "A", "B", "A"]', "list_canonical")` → `'["A", "B", "C"]'`
- [ ] `answer_formatter('{"answer": "42"}', "field_extract", {"field": "answer"})` → `"42"`

---

### Phase 2: System Prompt 强化（30 分钟）

**文件**：`source/solution/contestant_agent.py`

**步骤**：
1. 在 `SYSTEM_PROMPT` 末尾追加格式规则
2. 每种匹配类型给出 ✓/✗ 示例
3. 添加自检指令

**验收标准**：
- [ ] Prompt 长度 < 500 行
- [ ] 每种匹配类型都有示例
- [ ] 包含"不要做什么"的负面约束

---

### Phase 3: 自检循环（30 分钟）

**文件**：
- `source/solution/contestant_agent.py`
- `.env`（或 `env_config.py`）

**步骤**：
1. 修改 `_run_native_tool_loop()` 第 94-97 行
2. 添加自检 user message
3. 在 `.env` 中设置 `AGENT_DEMO_MAX_ITER=8`

**验收标准**：
- [ ] 简单题（mock_direct_001）仍 1 轮完成
- [ ] 复杂题能看到自检步骤（通过 dashboard 观察）
- [ ] 结果与改动前一致（非侵入性）

---

### Phase 4: 端到端测试（30 分钟）

**步骤**：
1. 运行 demo：`bash start.sh source/examples/questions.json source/outputs/result.json`
2. 检查 `result.json` 答案正确
3. 打开 `dashboard.html` 观察自检步骤
4. 手动测试 `answer_formatter` 的 6 种模式

**验收标准**：
- [ ] 5/5 mock 题目全部正确
- [ ] Dashboard 显示自检步骤
- [ ] `answer_formatter` 工具可用

---

## 4. 预期效果

### 4.1 得分率提升预估

| 题目类型 | 改动前 | 改动后 | 提升 |
|----------|--------|--------|------|
| 精确匹配题 | ~30% | ~80% | +50% |
| JSON 字段匹配 | ~40% | ~85% | +45% |
| 列表匹配题 | ~35% | ~80% | +45% |
| 多步骤推理题 | ~50% | ~70% | +20% |
| **综合** | **~40%** | **~75%** | **+35%** |

### 4.2 成本分析

| 改动 | API 调用增加 | 延迟增加 |
|------|-------------|----------|
| answer_formatter | 0（确定性代码） | ~10ms |
| System Prompt | 0（prompt 变长 ~200 tokens） | ~50ms |
| 自检循环 | +1~2 次/题 | +1~2s |

**总延迟增加**：约 2-3 秒/题（可接受）

---

## 5. 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| LLM 不遵循 System Prompt | 中 | 中 | answer_formatter 作为兜底 |
| 自检循环误判（把好答案改坏） | 低 | 高 | 限制最多 2 轮自检 |
| answer_formatter 解析失败 | 低 | 低 | 返回原文（降级处理） |
| API 调用超时 | 低 | 中 | 自检步骤设置较短 timeout |

---

## 6. 后续优化方向

### 6.1 短期（比赛前 1 周）

- [ ] 为每类比赛题目创建 mock question
- [ ] 运行 SWE-Skills-Bench 方法论评估（5 个多样任务）
- [ ] 根据评估结果调整 Skill 设计

### 6.2 中期（如有时间）

- [ ] 集成 `modelcontextprotocol/filesystem`（增强文件处理）
- [ ] 创建 1-2 个高领域适配 Skill（如 `code_auditor`）
- [ ] 多模态支持（6.1 图片分类）

### 6.3 长期（比赛后复盘）

- [ ] 分析实际比赛数据，找出失败模式
- [ ] 针对性优化（如特定题目类型的专用 Skill）
- [ ] 建立 Skill 评估体系（pass-rate 指标）

---

## 7. 参考文档

- [CAPABILITY_GAP.md](CAPABILITY_GAP.md) — 能力差距分析
- [P0_TOOLS.md](P0_TOOLS.md) — P0 工具文档
- 调研报告（4 份）：
  - Self-iteration frameworks
  - Answer formatting validation
  - MCP ecosystem
  - Generalizable skill patterns

---

## 附录 A: answer_formatter 完整实现

```python
@register_tool(
    name="answer_formatter",
    description="Format answer for competition scoring. Supports exact match, JSON canonical, list canonical, number precision, field extraction, and regex extraction.",
    input_schema=object_schema(
        {
            "raw_answer": {
                "type": "string",
                "description": "Raw answer text from LLM",
            },
            "format_type": {
                "type": "string",
                "description": "Format type: exact, json_canonical, list_canonical, number, field_extract, regex_extract",
            },
            "options": {
                "type": "object",
                "description": "Optional parameters (field for field_extract, pattern for regex_extract, precision for number)",
                "default": {},
            },
        },
        ["raw_answer", "format_type"],
    ),
    kind="mcp",
    risk="low",
)
def answer_formatter(
    raw_answer: str,
    format_type: str,
    options: dict | None = None
) -> str:
    """Format answer for competition scoring."""
    options = options or {}
    
    try:
        if format_type == "exact":
            return raw_answer.strip()
        
        elif format_type == "json_canonical":
            data = json.loads(raw_answer)
            def sort_obj(obj):
                if isinstance(obj, dict):
                    return {k: sort_obj(v) for k, v in sorted(obj.items())}
                elif isinstance(obj, list):
                    return [sort_obj(i) for i in obj]
                return obj
            return json.dumps(sort_obj(data), ensure_ascii=False, indent=2)
        
        elif format_type == "list_canonical":
            items = json.loads(raw_answer)
            if isinstance(items, list):
                unique = list(set(str(i) for i in items))
                return json.dumps(sorted(unique), ensure_ascii=False)
            return raw_answer
        
        elif format_type == "number":
            precision = options.get("precision", 2)
            num = float(raw_answer)
            return str(round(num, precision))
        
        elif format_type == "field_extract":
            field = options.get("field")
            data = json.loads(raw_answer)
            return str(data.get(field, ""))
        
        elif format_type == "regex_extract":
            pattern = options.get("pattern")
            match = re.search(pattern, raw_answer)
            return match.group(1) if match else raw_answer
        
        else:
            return raw_answer
    
    except Exception as exc:
        # 降级：解析失败返回原文
        return raw_answer
```

---

## 附录 B: System Prompt 完整新增内容

```
【答案格式规则】（必须严格遵守，违反则不得分）

1. 只输出答案正文，不要：
   - 解释说明（"答案是..."、"根据分析..."）
   - Markdown 代码块（```json ... ```）
   - <think> 标签
   - 结果对象包装（{"answer": "..."}）

2. 根据题目类型选择格式：

   a) 精确匹配题：
      - 直接输出文本本身
      - ✓ mock-file-read-ok
      - ✗ "mock-file-read-ok"
      - ✗ 答案是：mock-file-read-ok

   b) JSON 字段匹配题：
      - 输出严格 JSON，字段按字母顺序排列
      - ✓ {"amount": 100, "supplier": "A"}
      - ✗ {"supplier": "A", "amount": 100}

   c) 列表匹配题：
      - 输出 JSON 数组，元素排序去重
      - ✓ ["A", "B", "C"]
      - ✗ ["C", "A", "B"]
      - ✗ ["A", "B", "B", "C"]

   d) 数字答案：
      - 不要单位，不要千分位
      - 保留题目要求的精度
      - ✓ 1234.56
      - ✗ 1,234.56
      - ✗ 1234.56 元

3. 如果不确定格式，调用 answer_formatter 工具格式化

4. 最终输出前自检：
   - 是否有遗漏的字段？
   - 列表是否完整？
   - 数字精度是否正确？
```

---

**文档结束**
