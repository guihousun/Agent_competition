# Answer Checker Sub-agent

专门用于答案验证的 Sub-agent。

## 职责

1. **格式检查**：确保答案符合题目要求
2. **日期验证**：验证日期计算是否正确
3. **JSON 验证**：检查 JSON 格式和字段顺序
4. **列表验证**：检查排序和去重

## 使用方式

在主 Agent 的自检阶段调用：

```python
agent_delegate(
    agent_name="answer_checker",
    task="Check if the answer matches the required format",
    context_text="Question: ... Answer: ..."
)
```

## 检查规则

### 1. 格式规则

- 精确匹配：无多余文字
- JSON 字段匹配：按字母顺序
- 列表匹配：排序去重

### 2. 日期计算规则

- "下周二" = base_date + (1 - base_date.weekday()) % 7
- "上周四" = base_date - (base_date.weekday() - 3) % 7
- 工作日计算：跳过周末

### 3. 常见错误

- LLM 心算日期（应使用工具）
- JSON 字段顺序错误
- 列表包含重复元素
