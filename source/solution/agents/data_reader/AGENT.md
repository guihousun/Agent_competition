# Data Reader Sub-agent

数据预读子代理。读取原始数据文件，返回结构化摘要或精准查询链，避免大量原始数据污染主 agent 上下文。

## 职责

- 读取 CSV/DB/日志/邮件等大文件
- 返回数据摘要（结构、关键发现、相关片段）
- 或返回精准查询链（精确的工具调用步骤）

## 使用方式

```python
agent_delegate(
    agent_name="data_reader",
    task="具体问题，如：找出所有金额超过5万的PO",
    context_text="文件路径，如：files/采购PO合规审计/purchase_orders_raw.csv"
)
```

## 返回格式

**模式 A：摘要**（小数据或需要全貌）
```json
{"mode": "summary", "data_overview": "...", "key_findings": [...], "relevant_data": [...]}
```

**模式 B：查询链**（大数据需要精确定位）
```json
{"mode": "query_chain", "chain": [{"step": 1, "tool": "csv_read", "params": {...}}]}
```

## 何时使用

- CSV > 50 行
- SQLite 数据库
- 多封邮件/日志文件
- 需要理解数据结构再查询的场景
