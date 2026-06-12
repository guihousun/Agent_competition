# Dashboard 使用教程

## 快速开始

### 1. 生成 Dashboard

Dashboard 会在运行测试时**自动生成**：

```bash
bash start.sh source/examples/questions.json source/outputs/result.json
```

运行结束后，Dashboard 会自动生成在结果文件同目录：
- `source/outputs/dashboard.html` ← 打开这个文件

### 2. 本地查看

**方式 A：直接打开（推荐）**

```bash
# Windows
start source/outputs/dashboard.html

# Mac
open source/outputs/dashboard.html

# Linux
xdg-open source/outputs/dashboard.html
```

**方式 B：HTTP 服务器（分享给其他人）**

```bash
cd source/outputs
python -m http.server 8766
# 浏览器访问 http://localhost:8766/dashboard.html
# 局域网其他人访问 http://<你的IP>:8766/dashboard.html
```

### 3. 分享给朋友

**方法 1：直接发送 HTML 文件**

Dashboard 是**自包含**的单 HTML 文件（约 40KB），直接发送给朋友，用浏览器打开即可。

```bash
# 发送 dashboard.html 给朋友
# 朋友用浏览器打开即可，无需服务器
```

**方法 2：部署到 GitHub Pages**

```bash
# 1. 将 dashboard.html 重命名为 index.html
cp source/outputs/dashboard.html docs/index.html

# 2. 推送到 GitHub
git add docs/index.html
git commit -m "Add dashboard"
git push

# 3. 在仓库 Settings → Pages → 启用 GitHub Pages
# 4. 分享链接：https://guihousun.github.io/Agent_competition/
```

**方法 3：部署到静态网站托管**

- 上传 `dashboard.html` 到：
  - Netlify（拖拽上传）
  - Vercel（拖拽上传）
  - 任何静态网站托管服务

---

## 主要功能

### 1. Summary Cards（顶部卡片）

显示整体统计：
- **Questions**: 题目总数
- **Passed**: 通过数
- **Failed**: 失败数
- **Total Spans**: 工具/LLM 调用总数
- **Tokens**: 总 Token 消耗
- **Duration**: 总耗时

### 2. Waterfall Timeline（时间线）

每个题目的调用时间线：
- **蓝色 AI** = LLM 调用
- **绿色 TL** = 工具调用
- **紫色 SK** = Skill 调用
- **橙色 AG** = Sub-agent 调用

**交互**：点击时间线跳转到该题目的详情

### 3. Question Details（题目详情）

点击题目卡片展开：
- **Span 列表**：每一步的调用详情
  - 参数
  - 结果
  - 耗时
  - Token 消耗
- **Token 分布条**：prompt vs completion 比例
- **Final Answer**：最终答案

**答案预览**：题目 header 直接显示前 80 字符，无需展开

### 4. Agent Capabilities（能力面板）

显示当前 Agent 的能力：
- **System Prompt**：完整提示词
- **MCP Tools**：已加载工具列表
- **Skills**：已加载 Skill 列表
- **Sub-Agents**：已加载 Sub-agent 列表
- **Configuration**：关键配置（模型、温度、迭代次数）

---

## 自定义 Dashboard

### 修改样式

编辑 `source/runtime/generate_dashboard.py` 中的 CSS 部分：

```python
# 颜色变量
:root {
  --accent-blue: #58a6ff;
  --accent-green: #3fb950;
  --accent-red: #f85149;
  ...
}
```

### 添加新功能

在 `generate_dashboard.py` 中添加：

1. **新的渲染函数**：
```python
function renderNewFeature(data) {
  // 你的代码
}
```

2. **调用新函数**：
```python
render(data) {
  renderHeader(data)
  renderSummary(data)
  renderNewFeature(data)  // ← 添加这里
  ...
}
```

---

## 常见问题

### Q: Dashboard 打开是空白？

A: 确保 traces.json 存在：
```bash
ls source/outputs/traces.json
```
如果不存在，重新运行测试生成。

### Q: 答案没显示？

A: 答案现在直接显示在题目 header（80 字符预览），展开查看完整答案。

### Q: 如何查看历史测试？

A: 每次运行会覆盖 traces.json，建议保留不同版本：
```bash
cp source/outputs/traces.json source/outputs/traces_20260612.json
```

### Q: Dashboard 文件太大？

A: 当前约 40KB，如果数据量大可以：
1. 压缩 traces.json 数据
2. 使用 gzip 压缩 HTML
3. 按需加载（点击时加载详情）

---

## 技术架构

### 文件结构

```
source/runtime/
├── generate_dashboard.py  # Dashboard 生成器
├── tracing.py             # 追踪系统
└── batch_runner.py        # 批量执行器
```

### 数据流

```
测试运行 → batch_runner.py
         ↓
    tracing.py (收集 spans)
         ↓
    traces.json (持久化)
         ↓
generate_dashboard.py (生成 HTML)
         ↓
   dashboard.html (自包含)
```

### 关键技术

- **ContextVar**：线程安全的追踪上下文
- **自包含 HTML**：所有数据嵌入 HTML，无需服务器
- **零依赖**：纯 HTML/CSS/JS，无框架

---

## 示例

### 完整运行示例

```bash
# 1. 运行测试
bash start.sh source/examples/question_1_1.json source/outputs/q1_1.json

# 2. 查看结果
python -m source.runtime.show_answers source/outputs/q1_1.json

# 3. 打开 Dashboard
cd source/outputs && python -m http.server 8766

# 4. 浏览器访问
# http://localhost:8766/dashboard.html
```

### 批量测试示例

```bash
# 运行多个测试
for f in source/examples/test_*.json; do
  bash start.sh "$f" "source/outputs/$(basename $f .json)_result.json"
done

# 查看最新的 Dashboard
start source/outputs/dashboard.html
```

---

## 贡献

欢迎提交 Dashboard 改进建议：
- 新图表类型
- 更好的移动端适配
- 数据导出功能
- 实时流式更新
