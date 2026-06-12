---
name: huawei_coding_standard
description: 华为编程规范查询。当需要查找华为编码规范、代码风格要求、命名规则时使用。
---

# 华为编程规范 Skill

提供华为编程规范文档的查阅能力。

## 使用场景

- 代码审查时需要确认华为编码规范
- 编写代码前查询命名、格式、注释等要求
- 修复不符合华为规范的代码

## 调用方式

1. 先用 `skill_load` 加载本 skill，获取文档列表
2. 用 `skill_read_resource` 或 `text_read_file` 读取对应语言的规范文档
3. 根据文档内容回答问题或修复代码

## 规范文档列表

`references/` 目录下的文档：

| 文件 | 覆盖语言 |
|------|----------|
| general.md | 通用规范（所有语言适用） |
| c_cpp.md | C/C++ 规范 |
| java.md | Java 规范 |
| python.md | Python 规范 |
| go.md | Go 规范 |
| javascript.md | JavaScript 规范 |
| typescript.md | TypeScript 规范 |

根据题目涉及的编程语言选择对应文档读取。如果不确定语言，先读 `general.md`。
