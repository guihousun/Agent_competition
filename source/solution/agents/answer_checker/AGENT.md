# Answer Checker Sub-agent

Prompt 驱动的答案验证 Sub-agent。不依赖硬编码规则，由 LLM 推理验证答案是否满足题目要求。

## 职责

接收题目描述 + 待验证答案，返回结构化验证结果和修改建议。

## 使用方式

```python
agent_delegate(
    agent_name="answer_checker",
    task="题目描述 + 你的答案",
    context_text="工具返回的原始结果"
)
```

## 输出格式

```json
{
  "overall_valid": true/false,
  "fix_suggestions": ["具体修改建议"],
  "summary": "一句话总结"
}
```

## 设计原则

- **不写死规则**：格式类型、日期表达式、字段名称等不做硬编码匹配
- **LLM 推理**：由模型理解题目要求并判断答案是否符合
- **泛化能力**：适用于任意题型，不依赖预定义的检查模式
