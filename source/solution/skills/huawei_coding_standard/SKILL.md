---
name: huawei_coding_standard
description: 华为编程规范查询。当需要查找华为编码规范、代码风格要求、命名规则时使用。
version: "1.0"
---

# 华为编程规范 Skill

查询华为编程规范文档，返回与关键词匹配的规范条目。

## 使用场景

- 代码审查时需要确认华为编码规范
- 编写代码前查询命名、格式、注释等要求
- 修复不符合华为规范的代码

## 调用方式

通过 `skill_run` 调用，参数：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| language | string | 否 | 编程语言（java/python/c/cpp/go/javascript/typescript），默认 java |
| keyword | string | 是 | 查询关键词（如"命名""注释""异常处理""长度"） |

## 示例

```
skill_run(skill="huawei_coding_standard", args={"language": "java", "keyword": "命名规范"})
skill_run(skill="huawei_coding_standard", args={"language": "python", "keyword": "注释"})
skill_run(skill="huawei_coding_standard", args={"language": "c++", "keyword": "内存管理"})
```

## 返回格式

```json
{
  "status": "ok",
  "language": "java",
  "keyword": "命名",
  "matches": [{"source": "java", "content": "匹配的规范段落..."}],
  "total_matches": 3
}
```

如果 references/ 目录下没有对应语言的文档，返回 `status: "no_references"`。

## 规范文档结构

将规范文档放入 `references/` 目录：

| 文件 | 覆盖语言 |
|------|----------|
| general.md | 通用规范（所有语言适用） |
| c_cpp.md | C/C++ 规范 |
| java.md | Java 规范 |
| python.md | Python 规范 |
| go.md | Go 规范 |
| javascript.md | JavaScript 规范 |
| typescript.md | TypeScript 规范 |

文档格式：Markdown，使用 `#`/`##`/`###` 分节，skill 会按段落检索关键词匹配。
