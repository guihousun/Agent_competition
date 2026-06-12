# Agent Contest Python Demo

## 概述

**Skill 蒸馏攻防 Agent 大赛** Python 参考实现 + Dashboard + Skills 库。

**Python**: 3.11.0+  
**依赖**: openpyxl, pandas, numpy  
**模型**: qwen3.6-plus (DashScope Coding API)

## 快速开始

```bash
# 1. 配置环境
cp .env.example .env
# 编辑 .env，填入 MODEL_CHAT_COMPLETIONS_URL、MODEL_API_KEY、MODEL_NAME

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行测试
bash start.sh source/examples/questions.json source/outputs/result.json

# 4. 查看结果
python -m source.runtime.show_answers source/outputs/result.json

# 5. 打开 Dashboard
cd source/outputs && python -m http.server 8766
# 访问 http://localhost:8766/dashboard.html
```

## 项目结构

```
agent-contest-python-demo/
├── start.sh                    # 入口脚本
├── requirements.txt            # 依赖列表
├── .env.example                # 环境变量模板
├── README.md                   # 本文档
├── GUIDES.md                   # 使用指南
├── CAPABILITY_GAP.md           # 能力差距分析
├── P0_TOOLS.md                 # P0 工具文档
├── DESIGN_CORE_ENHANCEMENTS.md # 核心增强设计
└── source/
    ├── main.py                 # CLI 入口
    ├── runtime/                # 运行时框架
    │   ├── batch_runner.py     # 批量执行 + Tracing
    │   ├── tracing.py          # 追踪模块
    │   └── generate_dashboard.py  # Dashboard 生成
    ├── solution/               # 参赛者编辑区
    │   ├── contestant_agent.py # 主 Agent (ReAct + 自检)
    │   ├── mcp/contestant_tools.py  # 14 个工具
    │   └── skills/             # 3 个 Skill
    │       ├── mock_summary_skill/
    │       ├── data_analyzer/        # 自建，CSV/JSON/Excel 聚合
    │       └── document_searcher/    # 来自 Ansvar-Systems
    ├── examples/               # 测试案例
    │   ├── questions.json      # 5 题 Mock
    │   ├── case_questions.json # 3 题简单案例
    │   ├── case_complex.json   # 1 题复杂任务
    │   ├── case_archive.json   # 2 题压缩包测试
    │   ├── test_data_analyzer.json  # data_analyzer 测试
    │   ├── test_react_simple.json   # ReAct 框架测试
    │   ├── test_nested_zip.json      # 嵌套压缩包测试
    │   ├── question_1_1.json          # 真实比赛题
    │   └── files/              # 测试数据
    └── outputs/                # 输出结果
        ├── result.json
        ├── traces.json
        └── dashboard.html
```

## 工具列表（14 个）

### 平台内置（5 个）
- `text_read_file` - 读取题目附件
- `skill_load` / `skill_run` / `skill_read_resource` - Skill 生命周期
- `agent_delegate` - 委派 Sub-agent

### P0 比赛工具（5 个）
- `http_request` - HTTP GET/POST/PUT/DELETE
- `zip_extract` - ZIP 解压
- `tar_extract` - TAR.GZ/TGZ/TAR.BZ2 解压
- `csv_read` / `csv_aggregate` - CSV 读取 + 聚合
- `code_execute` - Python/Java/Node 代码执行
- `answer_formatter` - 答案格式化（6 种模式）

### Mock（2 个）
- `mock_order_lookup` / `mock_policy_check`

## Skills 列表（3 个）

| Skill | 来源 | 能力 |
|-------|------|------|
| `mock_summary_skill` | 示例 | 返回 mock 数据 |
| `data_analyzer` | 自建 | CSV/JSON/Excel 聚合分析 |
| `document_searcher` | Ansvar-Systems | FTS5 全文搜索 |

## 核心特性

### 1. ReAct 框架
System Prompt 使用 ReAct 思维模式：
```
Thought → Action → Observation → 重复 → Answer
```

### 2. 自检循环
- 默认 max_iter = 8，可配置
- 每轮迭代后自动验证答案

### 3. 答案格式化
- `answer_formatter` 支持 6 种格式
- System Prompt 包含详细规则和示例

### 4. 追踪系统
- ContextVar 传播
- 每个 span 记录：类型、参数、结果、耗时
- 自动生成 traces.json

### 5. Dashboard
- Summary Cards
- Waterfall Timeline
- Question 详情（含答案预览）
- Agent Capabilities

## 测试结果

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

## 比赛题目覆盖

| 题目 | 覆盖 | 工具/Skill |
|------|------|------------|
| 1_1 日期提取 | ✅ | text_read_file, code_execute |
| 1_3 问题定位 | ⚠️ | LLM 推理 |
| 1_4 接口测试 | ⚠️ | http_request |
| 2_1 数据清洗 | ✅ | csv_read, csv_aggregate, code_execute |
| 2_2 敏感扫描 | ✅ | zip_extract, tar_extract, code_execute |
| 2_3 Java 修复 | ✅ | code_execute |
| 3_2 PO 审计 | ⚠️ | csv_read, code_execute |
| 3_3 IDE 问答 | ⚠️ | http_request, document_searcher |

**当前覆盖**: 5/8 直接可用，3/8 需要本地服务

## 参考文档

- [GUIDE.md](GUIDE.md) - 详细使用指南
- [CAPABILITY_GAP.md](CAPABILITY_GAP.md) - 能力差距分析
- [P0_TOOLS.md](P0_TOOLS.md) - P0 工具文档
- [DESIGN_CORE_ENHANCEMENTS.md](DESIGN_CORE_ENHANCEMENTS.md) - 核心增强设计

## GitHub

https://github.com/guihousun/Agent_competition
