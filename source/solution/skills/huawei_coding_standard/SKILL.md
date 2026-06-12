---
name: huawei_coding_standard
description: 华为编程规范查询与代码审查。输入代码片段或规范关键词，返回对应的华为编程规范要求和修改建议。
entrypoint: scripts/run.py
---

# 华为编程规范 Skill

查询华为编程规范，对代码进行合规性审查。

## 使用场景

- 查询特定语言的华为编程规范（C/C++/Java/Python 等）
- 审查代码是否符合华为规范
- 获取规范的具体条款和修改建议

## 调用方式

通过 `skill_run` 调用，传入 JSON 参数：

```json
{
  "action": "query",
  "language": "java",
  "keyword": "命名规范"
}
```

```json
{
  "action": "review",
  "language": "java",
  "code": "public class MyService { ... }"
}
```

## 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| action | string | 是 | `query` 查询规范 / `review` 审查代码 |
| language | string | 是 | 编程语言：c, cpp, java, python, go 等 |
| keyword | string | 否 | 查询关键词（query 模式） |
| code | string | 否 | 待审查代码（review 模式） |

## 参考文档

`references/` 目录下存放华为编程规范文档，按语言组织：

- `references/c_cpp.md` - C/C++ 编程规范
- `references/java.md` - Java 编程规范
- `references/python.md` - Python 编程规范
- `references/general.md` - 通用规范（命名、注释、格式等）

请将相关规范文档放入 `references/` 目录，skill 会自动检索。
