# Answer Checker Sub-agent

只负责最终答案格式的后检查 Sub-agent，不负责重新解题或判断事实正确性。

## 职责

接收题目描述和待检查答案，清理包装并检查空答案、Markdown、`<think>`、JSON、分隔符和输出结构。

它不使用工具，不读取文件，不重新计算，也不能因为怀疑答案错误而增删答案项。

## 使用方式

```python
agent_delegate(
    agent_name="answer_checker",
    task="主 Agent 的最终候选答案",
    context_text=""
)
```

## 输出格式

```json
{
  "overall_valid": true/false,
  "cleaned_answer": "去除包装后的完整答案",
  "corrected_answer": "仅格式修复后的完整答案或空字符串",
  "format_issues": ["具体格式问题"],
  "summary": "一句话总结"
}
```

## 设计原则

- **主 Agent 负责正确性**：checker 不复算、不搜索、不使用工具
- **只修格式**：不得改变事实、数字、日期、ID 或列表成员
- **失败回退**：checker 失败或返回空内容时保留主 Agent 原答案
