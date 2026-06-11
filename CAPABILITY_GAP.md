# Agent Contest - Capability Gap Analysis

## 比赛题目需求 vs Demo 现有能力对比

### 一、文本处理类（2 题）

| 题目 | 核心需求 | Demo 现状 | 差距 |
|------|----------|-----------|------|
| 1.1 日期提取标准化 | 多语言日志解析、日期格式统一、正则匹配 | ✅ LLM 可处理 | 无 |
| 1.2 敏感信息扫描 | **ZIP 解压**、多模式正则扫描（手机/邮箱/身份证/API Key） | ❌ 无 ZIP 解压工具 | **需补充 `zip_extract`** |

**缺失工具**: `zip_extract` - 解压 ZIP 文件到临时目录

---

### 二、编程规范类（2 题）

| 题目 | 核心需求 | Demo 现状 | 差距 |
|------|----------|-----------|------|
| 2.1 华为规范问答 | **规范文档检索**、知识问答 |  无文档检索能力 | **需 Skill: `huawei_coding_standard`** |
| 2.2 代码审计 | **代码静态分析**、安全漏洞检测 | ❌ 无代码分析工具 | **需 Skill: `code_auditor`** |

**缺失能力**: 
- 华为编程规范知识库（可作为 Skill 的 references/）
- 代码静态分析工具（可调用外部 linter 或 LLM 分析）

---

### 三、系统分析类（2 题）

| 题目 | 核心需求 | Demo 现状 | 差距 |
|------|----------|-----------|------|
| 3.1 依赖鉴定与风险 | **跨文件依赖分析**、证据链推理 | ⚠️ LLM 可推理但无工具辅助 | **需 Skill: `dependency_analyzer`** |
| 3.2 API 测试场景 | **HTTP 客户端**、API 认证、响应验证 | ❌ 无 HTTP 工具 | **需补充 `http_request`** |

**缺失工具**: `http_request` - 发送 HTTP 请求（GET/POST/PUT/DELETE）

---

### 四、数据清洗类（2 题）

| 题目 | 核心需求 | Demo 现状 | 差距 |
|------|----------|-----------|------|
| 4.1 采购数据清洗 | **CSV 读写**、数据聚合、金额计算 | ❌ 无 CSV 工具 | **需补充 `csv_read`/`csv_aggregate`** |
| 4.2 PO 合规审计 | CSV 筛选、**合规规则校验**、审批流验证 | ❌ 无合规检查工具 | **需 Skill: `compliance_checker`** |

**缺失工具**: 
- `csv_read` - 读取 CSV 文件为 JSON
- `csv_aggregate` - 按列聚合（SUM/AVG/COUNT/GROUP BY）
- `data_filter` - 按条件筛选数据行

---

### 五、代码精修类（1 题）

| 题目 | 核心需求 | Demo 现状 | 差距 |
|------|----------|-----------|------|
| 5.1 Java 源码修复 | **Java 编译**、**运行测试**、错误定位 | ❌ 无代码执行工具 | **需补充 `code_execute`** |

**缺失工具**: `code_execute` - 执行代码（Python/Java/Node.js）并返回输出

---

### 六、智能推荐类（1 题）

| 题目 | 核心需求 | Demo 现状 | 差距 |
|------|----------|-----------|------|
| 6.1 图片分类推理 | **图片读取**、**视觉模型推理**、批量处理 | ❌ 无多模态能力 | **需多模态模型 + `image_read`** |

**缺失能力**:
- 多模态模型支持（qwen-vl-max 或类似）
- `image_read` - 读取图片为 base64
- 批量推理脚本（可作为 Skill）

---

### 七、智能问答类（1 题）

| 题目 | 核心需求 | Demo 现状 | 差距 |
|------|----------|-----------|------|
| 7.1 IDE 插件问答 | **本地服务调用**（:18080）、上下文构建 | ⚠️ 有 `http_request` 后可解决 | 依赖 `http_request` |

---

## 优先级排序

### P0 - 必须补充（影响 50%+ 题目）

| 工具/Skill | 影响题目 | 实现方式 |
|------------|----------|----------|
| `http_request` | 3.2, 7.1 | 内置工具（contestant_tools.py） |
| `zip_extract` | 1.2 | 内置工具 |
| `csv_read` + `csv_aggregate` | 4.1, 4.2 | 内置工具 |
| `code_execute` | 5.1 | 内置工具 |

### P1 - 重要补充（提升解题质量）

| 工具/Skill | 影响题目 | 实现方式 |
|------------|----------|----------|
| Skill: `huawei_coding_standard` | 2.1 | Skill 包（references/ 放规范文档） |
| Skill: `code_auditor` | 2.2 | Skill 包（调用 LLM + 规则库） |
| Skill: `compliance_checker` | 4.2 | Skill 包（合规规则 + 校验逻辑） |

### P2 - 可选增强

| 工具/Skill | 影响题目 | 实现方式 |
|------------|----------|----------|
| `image_read` + 多模态模型 | 6.1 | 内置工具 + 模型切换 |
| Skill: `dependency_analyzer` | 3.1 | Skill 包（代码解析 + 依赖图） |

---

## 实施方案

### 阶段 1: 补充内置工具（1-2 小时）

在 `source/solution/mcp/contestant_tools.py` 中添加：

```python
@register_tool(name="http_request", ...)
def http_request(url, method, headers, body, timeout=30) -> str:
    """发送 HTTP 请求，返回响应状态码 + 正文"""

@register_tool(name="zip_extract", ...)
def zip_extract(zip_path, output_dir=None) -> str:
    """解压 ZIP 文件，返回解压后的文件列表"""

@register_tool(name="csv_read", ...)
def csv_read(path, max_rows=1000) -> str:
    """读取 CSV 文件，返回 JSON 数组"""

@register_tool(name="csv_aggregate", ...)
def csv_aggregate(data, group_by, operation, column) -> str:
    """CSV 数据聚合：SUM/AVG/COUNT/MIN/MAX"""

@register_tool(name="code_execute", ...)
def code_execute(language, code, stdin="", timeout=30) -> str:
    """执行代码（python/java/node），返回 stdout/stderr/exit_code"""
```

### 阶段 2: 构建 Skill 包（2-3 小时）

为每个 Skill 创建：
- `SKILL.md` - 使用说明 + 示例
- `skill.json` - 元数据
- `scripts/run.py` - 执行逻辑
- `references/` - 参考文档（如华为规范）

### 阶段 3: 优化 System Prompt（30 分钟）

在 `contestant_agent.py` 的 `SYSTEM_PROMPT` 中添加：
- 任务类型识别策略
- 工具选择指南
- 多步骤任务编排模板

### 阶段 4: 端到端测试（1 小时）

为每类题目创建 mock question，验证完整 pipeline。

---

## 现有能力复用

以下现有能力可直接用于比赛：

| 能力 | 应用场景 |
|------|----------|
| LLM 推理（qwen3.6-plus） | 所有题目的核心推理 |
| `text_read_file` | 读取题目附件（文本文件） |
| `skill_load` / `skill_run` | 调用 Skill 包 |
| `agent_delegate` | 复杂任务委派给 Sub-agent |
| 工具调用循环（max 6 次） | 多步骤任务编排 |
| JSON Tool Loop fallback | 兼容不同模型网关 |

---

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 本地服务不可用（18080/18081） | 3.2, 7.1 无法完成 | 添加超时 + 错误处理 |
| 多模态模型不可用 | 6.1 无法完成 | 降级为文本描述 + LLM 推理 |
| 代码执行超时 | 5.1 卡住 | 严格 timeout（30s） |
| CSV 文件过大 | 4.1, 4.2 内存溢出 | `max_rows` 限制 + 流式处理 |

---

## 下一步行动

1. **立即实施**: P0 内置工具（http_request, zip_extract, csv_*, code_execute）
2. **随后实施**: P1 Skill 包（huawei_coding_standard, code_auditor, compliance_checker）
3. **最后优化**: System Prompt + 端到端测试

预计总工时: **4-6 小时**
