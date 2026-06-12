# Agent Contest 使用指南

## 快速开始

### 1. 环境准备

```bash
# 安装 Python 3.11.0+
# https://www.python.org/downloads/release/python-3110/

# 进入项目目录
cd D:\Research_vault\raw\writing\agent-contest-python-demo

# 创建虚拟环境（可选）
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入：
# MODEL_CHAT_COMPLETIONS_URL=https://coding.dashscope.aliyuncs.com/v1/chat/completions
# MODEL_API_KEY=sk-xxx
# MODEL_NAME=qwen3.6-plus
# AGENT_DEMO_TIMEOUT_SECONDS=600  # 10 分钟
# AGENT_DEMO_STREAM=true  # 流式输出
```

---

### 2. 运行测试

#### 方式 1：使用 start.sh（推荐）

```bash
bash start.sh <题目文件> <结果文件> [package_id]

# 示例：运行 mock 题目
bash start.sh source/examples/questions.json source/outputs/result.json

# 示例：运行真实比赛题
bash start.sh source/examples/question_1_1.json source/outputs/q1_1.json
```

#### 方式 2：直接 Python 运行

```bash
python -u -m source.main \
  --question source/examples/questions.json \
  --output source/outputs/result.json
```

---

### 3. 查看结果

#### 查看答案

```bash
python -m source.runtime.show_answers source/outputs/result.json
```

#### 打开 Dashboard

```bash
cd source/outputs
python -m http.server 8766
# 浏览器访问 http://localhost:8766/dashboard.html
```

**Dashboard 功能**：
- **Summary Cards**：题目数、通过数、失败数、Token、总耗时
- **Waterfall Timeline**：每个题目的 LLM + 工具调用时间线
- **Question Details**：包含**答案预览**（80 字符），展开查看完整 span
- **Agent Capabilities**：System Prompt、已加载工具、Skills、Sub-agents

---

## 现有测试案例

| 文件 | 题目数 | 用途 |
|------|--------|------|
| `questions.json` | 5 | Mock 基础能力测试 |
| `case_questions.json` | 3 | 简单案例（数据分析、API、代码执行） |
| `case_complex.json` | 1 | 超级复杂任务（6 步多工具） |
| `case_archive.json` | 2 | ZIP + TAR.GZ 压缩包处理 |
| `test_data_analyzer.json` | 2 | data_analyzer skill 测试 |
| `test_react_simple.json` | 1 | ReAct 框架验证 |
| `test_nested_zip.json` | 1 | 4 层嵌套压缩包 |
| `question_1_1.json` | 1 | 真实比赛题（日期提取） |
| `batch_test_simple.json` | 2 | 批量测试（1_1 + 2_3） |

---

## 添加测试案例

### 题目格式

```json
[
  {
    "id": "test_001",
    "title": "题目标题",
    "description": "题目描述",
    "files": ["files/input.csv"],
    "level": 2,
    "tools": ["text_read_file", "csv_read"],
    "skills": ["data_analyzer"],
    "sub_agents": []
  }
]
```

### 字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `id` | ✅ | 题目唯一标识 |
| `title` | ✅ | 题目标题 |
| `description` | ✅ | 题目描述（Agent 会看到） |
| `files` | ❌ | 允许读取的文件列表 |
| `level` | ❌ | 难度（1-5） |
| `tools` | ❌ | 允许的工具（空=全部） |
| `skills` | ❌ | 允许的 Skills（空=全部） |
| `sub_agents` | ❌ | 允许的 Sub-agents |

### 完整示例

**1. 创建题目文件** `source/examples/my_test.json`：

```json
[
  {
    "id": "my_test_001",
    "title": "CSV 数据分析",
    "description": "请分析 files/data.csv，计算 amount 总和。\n\n输出格式：{\"total\": 数值}",
    "files": ["files/data.csv"],
    "tools": ["csv_read", "answer_formatter"],
    "skills": ["data_analyzer"]
  }
]
```

**2. 准备数据** `source/examples/files/data.csv`：

```csv
id,name,amount
1,Alice,100
2,Bob,200
```

**3. 运行测试**：

```bash
bash start.sh source/examples/my_test.json source/outputs/my_test.json
```

**4. 查看结果**：

```bash
python -m source.runtime.show_answers source/outputs/my_test.json
```

---

## 配置选项 (.env)

```env
# 必需：模型配置
MODEL_CHAT_COMPLETIONS_URL=https://coding.dashscope.aliyuncs.com/v1/chat/completions
MODEL_API_KEY=sk-xxx
MODEL_NAME=qwen3.6-plus

# 性能调优
AGENT_DEMO_MAX_ITER=8          # 最大迭代次数
AGENT_DEMO_TEMPERATURE=0.2     # 温度参数
AGENT_DEMO_TIMEOUT_SECONDS=600 # 请求超时（秒）
AGENT_DEMO_STREAM=true         # 流式输出

# 高级选项
AGENT_DEMO_USE_LLM=true         # 是否使用 LLM
AGENT_DEMO_NATIVE_TOOLS=true    # 使用原生 tools 字段
AGENT_DEMO_JSON_TOOL_FALLBACK=true  # 失败时回退到 JSON prompt
```

---

## 自定义工具

编辑 `source/solution/mcp/contestant_tools.py`：

```python
@register_tool(
    name="my_tool",
    description="我的工具",
    input_schema=object_schema(
        {"param": {"type": "string"}},
        ["param"],
    ),
    kind="mcp",
    risk="low",
)
def my_tool(param: str) -> str:
    return json.dumps({"result": f"Processed: {param}"}, ensure_ascii=False)
```

---

## 自定义 Skill

### 目录结构

```
source/solution/skills/my_skill/
├── SKILL.md              # 使用说明（YAML frontmatter + Markdown）
├── skill.json            # 元数据
├── scripts/
│   ── run.py            # stdin/stdout JSON 通信
└── references/           # 参考资源（可选）
```

### skill.json

```json
{
  "name": "my_skill",
  "description": "Skill 描述",
  "entrypoint": "scripts/run.py",
  "timeout_seconds": 60,
  "input_schema": {
    "type": "object",
    "properties": {
      "action": {"type": "string"}
    },
    "required": ["action"]
  }
}
```

### scripts/run.py

```python
import json, sys
def main():
    params = json.loads(sys.stdin.read())
    # 业务逻辑
    print(json.dumps({"result": "ok"}, ensure_ascii=False))
if __name__ == "__main__":
    main()
```

---

## 调试技巧

### 1. 查看 Traces

```bash
python -c "
import json
with open('source/outputs/traces.json') as f:
    d = json.load(f)
for q in d['questions']:
    print(f'{q[\"id\"]}: {len(q[\"spans\"])} spans, {q[\"duration_ms\"]}ms')
    for s in q['spans']:
        if s['type'] == 'tool_call':
            print(f'  Tool: {s[\"data\"][\"tool_name\"]}')
"
```

### 2. 限制迭代次数

```env
AGENT_DEMO_MAX_ITER=4  # 减少迭代，加快调试
```

### 3. 关闭流式输出

```env
AGENT_DEMO_STREAM=false  # 非流式（更稳定）
```

---

## 常见问题

### Q: 测试超时？

A: 
1. 检查文件路径是否正确
2. 减少 `AGENT_DEMO_MAX_ITER`
3. 增加 `AGENT_DEMO_TIMEOUT_SECONDS`

### Q: 答案为空？

A: 
1. 检查 `.env` 中的 API key
2. 查看 traces.json 中的 error
3. 简化题目描述

### Q: Dashboard 答案没显示？

A: 答案现在直接显示在 question header（80 字符预览），完整答案在展开后查看

### Q: 文件路径不对？

A: 题目 `files` 字段的路径是相对于 `source/outputs/` 目录的，如 `"files/data.csv"` 实际指向 `source/outputs/files/data.csv`

---

## 提交结果

### 结果格式

```json
[
  {"id": "test_001", "answer": "..."}
]
```

### 验证结果

```bash
python -m source.runtime.show_answers result.json
```

### 上传

```bash
git add source/outputs/result.json
git commit -m "Submit results"
git push github main
```

---

## 参考文档

- [README.md](README.md) - 项目总览
- [CAPABILITY_GAP.md](CAPABILITY_GAP.md) - 能力差距分析
- [P0_TOOLS.md](P0_TOOLS.md) - P0 工具文档
- [DESIGN_CORE_ENHANCEMENTS.md](DESIGN_CORE_ENHANCEMENTS.md) - 核心增强设计
- [GitHub](https://github.com/guihousun/Agent_competition)
