---
name: java_tax_solver
description: Use when a contest question provides a broken Java personal income tax calculator source file such as JavaSource_*.java and asks for java -version plus hidden salary tax outputs. The skill deterministically decodes embedded tax parameters, computes hidden cases, and returns the final comma-separated answer.
---

# Java Tax Solver

Use this skill for Java personal income tax calculator contest tasks.

Run `skill_run` with:

```json
{
  "source_path": "absolute/path/to/JavaSource_7_1.java",
  "question": { "description": "...hidden cases..." }
}
```

The executable:

1. Runs `java -version` and keeps the first version line.
2. Reads the Java source.
3. Triple-decodes Base64 string literals to find the deduction point and tax bracket table.
4. Parses hidden salary cases from the question description.
5. Computes `taxableIncome = salary - deductionPoint`.
6. Applies the matching bracket as `tax = taxableIncome * rate - quickDeduction`.
7. Returns only `java-version,tax1,tax2,...` with two decimal places.

Do not manually repair the Java file unless the script reports an error.
