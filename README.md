# Agent Contest Python Demo - 比赛准备版

## 概述

**Skill 蒸馏攻防 Agent 大赛** Python 参考实现。主 Agent 接收赛题，自主编排 MCP-style tools、Skills 和 Sub-agents 来解题。

**Python 版本**: 3.11.0+（不使用 conda）  
**依赖**: 无第三方依赖（纯标准库）

## 快速开始

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 MODEL_BASE_URL, MODEL_API_KEY, MODEL_NAME

# 2. 运行 demo
bash start.sh source/examples/questions.json source/outputs/result.json

# 3. 查看结果
python -m source.runtime.show_answers source/outputs/result.json

# 4. 打开仪表盘
source/outputs/dashboard.html  # 直接在浏览器打开
```

## 工具列表（12 个）

### 平台内置（5 个）
| 工具 | 用途 |
|---|---|
| `text_read_file` | 读取题目附件（文件不自动进 prompt） |
| `skill_load` | 加载 Skill 的 SKILL.md 指令 |
| `skill_read_resource` | 读取 Skill 包内 references/assets |
| `skill_run` | 执行 Skill 脚本 |
| `agent_delegate` | 委派任务给 Sub-agent |

### P0 比赛工具（5 个）⭐
| 工具 | 用途 | 覆盖题目 |
|---|---|---|
| `http_request` | HTTP API 调用 | 3.2 API 测试、7.1 IDE 问答 |
| `zip_extract` | ZIP 文件解压 | 1.2 敏感信息扫描 |
| `csv_read` | CSV 数据读取 | 4.1, 4.2 数据清洗 |
| `csv_aggregate` | CSV 聚合（SUM/AVG/COUNT） | 4.1 采购总额 |
| `code_execute` | 代码执行（Python/Java/Node） | 5.1 Java 修复 |

### Mock 工具（2 个）
`mock_order_lookup`, `mock_policy_check`

## 比赛题目覆盖

| 类别 | 题目 | 状态 |
|---|---|---|
| 文本处理 | 1.1 日期提取 | ✅ LLM |
| 文本处理 | 1.2 敏感扫描 | ✅ `zip_extract` |
| 编程规范 | 2.1 华为规范 |  Skill (P1) |
| 编程规范 | 2.2 代码审计 | ⏳ Skill (P1) |
| 系统分析 | 3.1 依赖鉴定 | ⚠️ 部分 |
| 系统分析 | 3.2 API 测试 | ✅ `http_request` |
| 数据清洗 | 4.1 数据汇总 | ✅ `csv_*` |
| 数据清洗 | 4.2 PO 合规 | ⚠️ 部分 |
| 代码精修 | 5.1 Java 修复 | ✅ `code_execute` |
| 智能推荐 | 6.1 图片分类 |  P2 |
| 智能问答 | 7.1 IDE 问答 | ✅ `http_request` |

**当前覆盖**: 7/11 题（64%）  
**P1 后覆盖**: 9/11 题（82%）

## 目录结构

```
├── start.sh                    # 入口脚本
├── requirements.txt            # Python 3.11.0+
── .env.example                # 环境变量模板
── CAPABILITY_GAP.md           # 能力差距分析
├── P0_TOOLS.md                 # P0 工具文档
└── source/
    ├── runtime/                # 运行时框架
    │   ├── tracing.py          # 非侵入式追踪
    │   └── generate_dashboard.py  # Dashboard 生成器
    ├── solution/               # 参赛者编辑区
    │   ├── contestant_agent.py # 主 Agent
    │   ├── mcp/contestant_tools.py  # 自定义工具
    │   ├── skills/             # Skill 包
    │   └── agents/             # Sub-agent 包
    └── outputs/
        ├── result.json         # 答题结果
        ├── traces.json         # 追踪数据
        └── dashboard.html      # 可视化仪表盘
```

## Dashboard 功能

- **Summary Cards**: Questions / Passed / Failed / Spans / Tokens / Duration
- **Waterfall Timeline**: Span 序列可视化（LLM=蓝，Tool=绿，Skill=紫，Agent=橙）
- **Question Details**: 点击展开查看 span 详情、token 分布、final answer
- **Search**: 按题目 ID、工具名搜索过滤

## 下一步

1. **P1 Skill 包**: `huawei_coding_standard`, `code_auditor`, `compliance_checker`
2. **System Prompt 优化**: 任务类型识别 + 工具选择策略
3. **Mock 题目**: 为每类比赛题目创建测试用例

## 参考文档

- [CAPABILITY_GAP.md](CAPABILITY_GAP.md) - 比赛题目 vs demo 能力差距分析
- [P0_TOOLS.md](P0_TOOLS.md) - P0 工具详细文档
