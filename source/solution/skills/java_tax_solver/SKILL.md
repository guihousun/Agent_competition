---
name: java_tax_solver
description: Use when a contest question involves a broken Java personal income tax calculator source file, JavaSource_*.java, java -version output, salary tax cases, hidden examples, Base64 encoded tax parameters, or 修复个人所得税 Java 程序.
---

# Java Tax Solver

Use this skill as a repair guide. Do not use it as a direct answer generator.
The main Agent remains responsible for reading the actual source, repairing or
simulating it, running checks, and producing the final answer.
这是修复 Java 源码和校验计算逻辑的指南，不要把官方样例答案写死。

## Workflow

1. Read the Java source with `text_read_file`.
2. Run `java -version` through `code_execute` with Python subprocess if the answer requires the runtime version. Do not use unsupported `shell` or `bash` languages.
3. Inspect the source before compiling. Broken contest files often contain multiple small defects; fixing only the first compiler error is not enough.
4. Decode tax parameters from the actual source when present. Do not hardcode official sample answers, salary values, tax brackets, or deduction points.
5. Repair the Java logic or write a small verification script that exactly mirrors the repaired logic.
6. Test public examples first, then compute hidden salaries from the question text.
7. Return only the format requested by the question, usually `java-version,tax1,tax2,...`.

## Common Defects

Check for these patterns in broken Java individual income tax calculators:

- Missing imports such as `java.util.Base64`.
- `main` reads `args[1]` when only one salary argument is supplied.
- Argument count checks like `args.length < 0` instead of checking for no arguments.
- Helper methods called from `static main` but declared non-static.
- Typo such as `sout` instead of `System.out`.
- Taxable income computed as `salary + deductionPoint`; it should usually be `salary - deductionPoint`.
- Zero-tax branch uses `>= 0`; it should usually handle `taxableIncome <= 0`.
- Bracket loop uses `<= brackets.length`, causing out-of-bounds.
- Bracket bounds or deduction indexes are swapped.
- Range condition uses `||` instead of `&&`.
- Quick deduction is added instead of subtracted.
- Output precision does not match the question, usually two decimals.

## Parameter Decoding Pattern

If the source stores tax tables or deduction points in repeated Base64 strings,
decode the strings from the source dynamically. Example Python helper to adapt:

Use this tool shape for Java version and deterministic calculations:

```json
{
  "language": "python",
  "code": "import subprocess\\nr = subprocess.run(['java', '-version'], capture_output=True, text=True)\\nprint((r.stderr or r.stdout).splitlines()[0])"
}
```

```python
import ast, base64, re

for literal in re.findall(r'"([A-Za-z0-9+/=]{16,})"', java_source):
    data = literal.encode("ascii")
    try:
        for _ in range(3):
            data = base64.b64decode(data, validate=True)
        value = data.decode("utf-8")
    except Exception:
        continue
    if value.startswith("[["):
        brackets = ast.literal_eval(value)
    elif re.fullmatch(r"\d+(?:\.\d+)?", value):
        deduction_point = float(value)
```

## Tax Formula Pattern

For each salary:

```python
taxable = salary - deduction_point
if taxable <= 0:
    tax = 0.0
else:
    for lower, upper, rate, quick in brackets:
        if lower <= taxable <= upper:
            tax = taxable * rate - quick
            break
tax = max(0.0, tax)
```

Keep this as a reasoning and validation pattern. The final implementation must
still follow the actual Java source and the exact question wording.

## Output Checks

- Include `java -version` only if the question asks for it.
- Preserve the order of salary cases as written in the question.
- Use two decimal places when the examples use `0.00` style output.
- Do not include Markdown, explanations, code blocks, or intermediate reasoning in the final answer.
