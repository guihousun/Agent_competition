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
```

---

### 2. 运行测试

#### 方式 1：使用 start.sh（推荐）

```bash
bash start.sh <题目文件> <结果文件> [package_id]

# 示例：运行 mock 题目
bash start.sh source/examples/questions.json source/outputs/result.json

# 示例：运行自定义题目
bash start.sh source/examples/test_react_simple.json source/outputs/my_result.json
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

输出示例：
```
result: source/outputs/result.json
items: 5

[1] id: mock_direct_001
answer:
  mock demo ready
--------------------------------------------------------------------------------
[2] id: mock_file_001
answer:
  mock-file-read-ok
--------------------------------------------------------------------------------
```

#### 打开 Dashboard

Dashboard 会自动生成在结果文件同目录：

```bash
# 直接用浏览器打开
start source/outputs/dashboard.html  # Windows
open source/outputs/dashboard.html   # Mac
xdg-open source/outputs/dashboard.html  # Linux

# 或者用 HTTP 服务器查看
cd source/outputs
python -m http.server 8766
# 浏览器访问 http://localhost:8766/dashboard.html
```

**Dashboard 功能**：
- **Summary Cards**：题目数、通过数、失败数、Token 消耗、总耗时
- **Waterfall Timeline**：每个题目的 LLM 调用和工具调用时间线
- **Question Details**：点击展开查看每个题目的详细 span 信息
- **Agent Capabilities**：System Prompt、已加载工具、Skills、Sub-agents

---

## 添加测试案例

### 题目格式

题目文件是 JSON 数组，每个题目包含以下字段：

```json
[
  {
    "id": "test_001",
    "title": "题目标题",
    "description": "题目描述（Agent 会看到这个）",
    "explanation": "题目说明（仅用于记录，Agent 不会看到）",
    "files": ["files/input.csv"],
    "level": 2,
    "tools": ["text_read_file", "csv_read"],
    "skills": ["data_analyzer"],
    "sub_agents": []
  }
]
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 题目唯一标识 |
| `title` | string | ✅ | 题目标题 |
| `description` | string | ✅ | 题目描述（Agent 会看到这个） |
| `explanation` | string | ❌ | 题目说明（仅记录用） |
| `files` | array | ❌ | 允许 Agent 读取的文件列表 |
| `level` | number | ❌ | 难度等级（1-5） |
| `tools` | array | ❌ | 允许使用的工具（空=全部允许） |
| `skills` | array | ❌ | 允许使用的 Skills（空=全部允许） |
| `sub_agents` | array | ❌ | 允许使用的 Sub-agents（空=全部允许） |

### 示例：创建新题目

**1. 创建题目文件** `source/examples/my_test.json`：

```json
[
  {
    "id": "my_test_001",
    "title": "CSV 数据分析",
    "description": "请分析 files/data.csv 文件，计算 amount 列的总和。\n\n输出格式：{\"total\": 数值}",
    "files": ["files/data.csv"],
    "tools": ["csv_read", "answer_formatter"],
    "skills": []
  }
]
```

**2. 创建数据文件** `source/examples/files/data.csv`：

```csv
id,name,amount
1,Alice,100
2,Bob,200
3,Charlie,300
```

**3. 运行测试**：

```bash
bash start.sh source/examples/my_test.json source/outputs/my_test_result.json
```

**4. 查看结果**：

```bash
python -m source.runtime.show_answers source/outputs/my_test_result.json
# 打开 dashboard 查看详细过程
```

---

## 提交结果

### 比赛提交流程

1. **运行所有题目**：
   ```bash
   bash start.sh questions.json result.json
   ```

2. **检查结果**：
   ```bash
   python -m source.runtime.show_answers result.json
   ```

3. **验证格式**：
   - 确保 `result.json` 是 JSON 数组
   - 每个元素包含 `id` 和 `answer`
   - 答案格式符合题目要求

4. **提交**：
   - 将 `result.json` 上传到比赛平台
   - 或推送到指定 Git 仓库

### 结果文件格式

```json
[
  {
    "id": "test_001",
    "answer": "{\"total\": 600}"
  },
  {
    "id": "test_002",
    "answer": "mock-file-read-ok"
  }
]
```

---

## 自定义工具

### 添加新工具

编辑 `source/solution/mcp/contestant_tools.py`：

```python
@register_tool(
    name="my_custom_tool",
    description="我的自定义工具",
    input_schema=object_schema(
        {
            "param1": {
                "type": "string",
                "description": "参数 1",
            }
        },
        ["param1"],  # 必填参数
    ),
    kind="mcp",
    risk="low",
)
def my_custom_tool(param1: str) -> str:
    """工具实现"""
    return json.dumps({"result": f"Processed: {param1}"}, ensure_ascii=False)
```

---

## 自定义 Skill

### 创建 Skill 包

```
source/solution/skills/my_skill/
├── SKILL.md              # 使用说明
├── skill.json            # 元数据
├── scripts/
│   ── run.py            # 执行逻辑
└── references/           # 参考文档（可选）
    └── examples/
```

**skill.json 示例**：

```json
{
  "name": "my_skill",
  "description": "我的 Skill 描述",
  "entrypoint": "scripts/run.py",
  "timeout_seconds": 60,
  "input_schema": {
    "type": "object",
    "properties": {
      "task": {"type": "string"}
    },
    "required": ["task"]
  }
}
```

**scripts/run.py 示例**：

```python
#!/usr/bin/env python3
import json
import sys

def main():
    input_data = sys.stdin.read().strip()
    params = json.loads(input_data) if input_data else {}
    
    task = params.get('task', '')
    # 实现你的逻辑
    result = {"status": "ok", "task": task}
    
    print(json.dumps(result, ensure_ascii=False))

if __name__ == '__main__':
    main()
```

---

## 调试技巧

### 1. 查看详细日志

```bash
# 设置调试模式
export AGENT_DEMO_DEBUG=true

# 运行测试
python -u -m source.main --question test.json --output result.json
```

### 2. 查看 Traces

Traces 文件包含完整的执行过程：

```bash
# 查看 traces
python -c "
import json
with open('source/outputs/traces.json') as f:
    d = json.load(f)
for q in d['questions']:
    print(f'{q[\"id\"]}: {len(q[\"spans\"])} spans')
"
```

### 3. 使用 Dashboard 调试

Dashboard 会显示：
- 每个工具调用的参数和结果
- 每个 LLM 调用的耗时和 token
- 错误信息（如果有）

### 4. 限制迭代次数

```bash
# 编辑 .env
AGENT_DEMO_MAX_ITER=4  # 减少迭代次数，加快调试
```

---

## 常见问题

### Q: 测试超时怎么办？

A: 检查是否有重复调用或路径问题：
1. 打开 Dashboard 查看工具调用序列
2. 确认文件路径正确
3. 减少 `AGENT_DEMO_MAX_ITER`

### Q: 答案为空白？

A: 可能是 LLM 调用失败或格式错误：
1. 检查 `.env` 配置是否正确
2. 查看 traces 中的 error 信息
3. 简化题目描述

### Q: 如何添加新模型？

A: 编辑 `.env`：
```env
MODEL_CHAT_COMPLETIONS_URL=https://api.openai.com/v1/chat/completions
MODEL_API_KEY=sk-xxx
MODEL_NAME=gpt-4
```

### Q: Dashboard 无法打开？

A: 确保使用 HTTP 服务器：
```bash
cd source/outputs
python -m http.server 8766
# 访问 http://localhost:8766/dashboard.html
```

---

## 项目结构

```
agent-contest-python-demo/
├── start.sh                    # 入口脚本
├── requirements.txt            # 依赖列表
├── .env.example                # 环境变量模板
├── .env                        # 环境变量（不提交 Git）
├── source/
│   ├── main.py                 # CLI 入口
│   ├── runtime/                # 运行时框架
│   │   ├── batch_runner.py     # 批量执行
│   │   ├── tracing.py          # 追踪模块
│   │   └── generate_dashboard.py  # Dashboard 生成
│   ├── solution/               # 参赛者编辑区
│   │   ├── contestant_agent.py # 主 Agent
│   │   ├── mcp/contestant_tools.py  # 自定义工具
│   │   └── skills/             # Skill 包
│   ├── examples/               # 示例题目
│   └── outputs/                # 输出结果
└── README.md                   # 本文档
```

---

## 参考文档

- [DESIGN_CORE_ENHANCEMENTS.md](DESIGN_CORE_ENHANCEMENTS.md) - 核心增强设计
- [CAPABILITY_GAP.md](CAPABILITY_GAP.md) - 能力差距分析
- [P0_TOOLS.md](P0_TOOLS.md) - P0 工具文档
- [GitHub](https://github.com/guihousun/Agent_competition) - 代码仓库
