# Observed Rationalizations and Red Flags (file-ops)

The excuses and failure patterns below were observed defeating this skill's rules. Each is a red flag: catching yourself thinking the left column means the right column is what is actually happening.
Extracted verbatim from the walkthrough variant (`SuperWork`-style agents-skills text) so neither variant loses the counters.

## Rationalizations

| Excuse | Reality |
|--------|---------|
| "转换成功了，内容肯定没变" | Format conversion is translation; only reading the output back tells you what survived. |
| "OCR 结果看起来没问题" | Confident OCR errors on amounts and dates are the classic silent failure. The 人工确认清单 exists for exactly these. |
| "60 个文件逐个验证太慢" | Verify the first fully, then per-file structural checks in the loop — slow is still faster than re-doing 60. |
| "重命名直接跑，反正规律很清楚" | Dry-run listing is one command. The regex that eats 40 filenames also looks clear. |
