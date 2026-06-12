# P0 Tools - 比赛工具文档

## 概述

为比赛场景新增的 6 个核心工具，覆盖数据处理、网络请求、代码执行、答案格式化等关键能力。

---

## 1. `http_request` - HTTP 客户端

**用途**：调用本地/远程 API（比赛题 3.2 API 测试、7.1 IDE 问答）

```python
http_request(
    url="http://localhost:18080/api/question",
    method="POST",  # GET, POST, PUT, DELETE, PATCH
    headers={"Content-Type": "application/json"},
    body='{"question": "..."}',
    timeout=30
)
```

**返回**：
```json
{
  "status": 200,
  "headers": {...},
  "body": "...",
  "success": true
}
```

**错误处理**：自动捕获 HTTPError、URLError、其他异常

---

## 2. `zip_extract` - ZIP 解压

**用途**：解压 ZIP 附件（比赛题 2.2 敏感扫描、3.1 缺陷定位）

```python
zip_extract(zip_path="sensitive_data.zip", output_dir="")
```

**返回**：
```json
{
  "output_dir": "/tmp/zip_extract_xxx",
  "files": ["/tmp/.../file1.txt", ...],
  "count": 5
}
```

**特性**：支持嵌套解压（递归调用即可）

---

## 3. `tar_extract` - TAR 解压

**用途**：解压 TAR.GZ/TGZ/TAR.BZ2 附件

```python
tar_extract(tar_path="reports.tar.gz", output_dir="")
```

**支持格式**：`.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`

---

## 4. `csv_read` - CSV 读取

**用途**：读取 CSV 数据文件

```python
csv_read(
    path="data.csv",
    delimiter=",",
    encoding="utf-8",
    max_rows=0  # 0 = all
)
```

**返回**：
```json
{
  "path": "data.csv",
  "rows": 150,
  "columns": ["supplier", "amount", "currency"],
  "data": [{"supplier": "A", "amount": "100", ...}, ...]
}
```

---

## 5. `csv_aggregate` - CSV 聚合

**用途**：数据汇总计算

```python
csv_aggregate(
    data=[...],  # csv_read 的输出
    operation="SUM",  # SUM, AVG, COUNT, MIN, MAX
    column="amount",
    group_by="supplier"  # 可选
)
```

**返回**：
```json
{
  "operation": "SUM",
  "column": "amount",
  "result": 15000.0,
  "count": 50
}
```

---

## 6. `code_execute` - 代码执行

**用途**：编译运行代码（比赛题 2.3 Java 修复、复杂计算）

```python
code_execute(
    language="java",  # python, java, node
    code="public class Main { ... }",
    stdin="",
    timeout=30
)
```

**返回**：
```json
{
  "language": "java",
  "exit_code": 0,
  "stdout": "Test passed: 10/10",
  "stderr": ""
}
```

**特性**：
- Java：自动编译 + 运行
- Python：直接执行
- Node.js：直接执行
- 超时保护

---

## 7. `answer_formatter` - 答案格式化

**用途**：确定性格式化答案（确保符合比赛评分）

```python
answer_formatter(
    raw_answer='{"b": 2, "a": 1}',
    format_type="json_canonical",
    options={}
)
```

**6 种格式类型**：

| 类型 | 用途 | 示例 |
|------|------|------|
| `exact` | 精确匹配 | `"  hello  "` → `"hello"` |
| `json_canonical` | JSON 字段匹配 | `{"b":2,"a":1}` → `{"a":1,"b":2}` |
| `list_canonical` | 列表匹配 | `["C","A","B"]` → `["A","B","C"]` |
| `number` | 数字精度 | `3.14159` → `3.14` |
| `field_extract` | 字段提取 | 提取指定字段 |
| `regex_extract` | 正则提取 | 提取匹配部分 |

**返回**：格式化后的字符串

---

## 工具总数：14 个

### 平台内置（5）
- `text_read_file`
- `skill_load` / `skill_run` / `skill_read_resource`
- `agent_delegate`

### P0 比赛工具（7）
- `http_request`
- `zip_extract`
- `tar_extract`
- `csv_read` / `csv_aggregate`
- `code_execute`
- `answer_formatter`

### Mock（2）
- `mock_order_lookup`
- `mock_policy_check`

---

## 安装

工具依赖在 `requirements.txt` 中：

```
openpyxl>=3.1.0    # Excel 读写
pandas>=2.0.0      # 数据分析（可选）
numpy>=1.24.0      # 数值计算
```

其余工具（zip, tar, http, csv）使用 Python 标准库。
