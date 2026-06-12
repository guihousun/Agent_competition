# Data Reader Sub-agent

数据接口层。不做初筛，不做假设——返回完整数据全貌，由主 agent 决定查什么。

## 设计原则

- **不筛选**：overview 模式返回全部字段、值域、关联，不做任何过滤
- **不假设**：不基于题目猜测主 agent 需要什么
- **两阶段**：先全貌（overview），再精确查询（query）

## 阶段 1：数据探查

```python
agent_delegate(
    agent_name="data_reader",
    task="探查数据结构",
    context_text="files/data.csv"
)
```

返回：schema、行数、字段类型、值域范围、枚举值、文件间关联、数据问题

## 阶段 2：精确查询

```python
agent_delegate(
    agent_name="data_reader",
    task="找出 status=已完成 且 amount>=50000 的所有行，返回 po_id, vendor_id, amount",
    context_text="files/data.csv"
)
```

返回：查询结果数组（≤50条）、结果总数、注意事项

## 返回格式

**overview 模式**：
```json
{
  "mode": "overview",
  "data_landscape": {
    "filename.csv": {
      "structure": "45行 x 8列",
      "fields": [{"name": "po_id", "type": "string", "sample": "PO-001", "unique_count": 45}],
      "value_ranges": {"status": ["已完成", "草稿", "取消"]},
      "notable": ["amount 有 3 行为空值"]
    }
  },
  "connections": ["purchase_orders.vendor_id → vendors.vendor_id"]
}
```

**query 模式**：
```json
{
  "mode": "query",
  "result_count": 12,
  "results": [{"po_id": "PO-001", "amount": 80000}],
  "caveats": ["currency 字段有混用 CNY/USD 的情况"]
}
```
