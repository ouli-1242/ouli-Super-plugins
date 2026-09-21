# Common Rationalizations (tdd)

The excuses below have all been observed defeating the Iron Law on capable models. Each is a red flag: catching yourself thinking the left column means the right column is what is actually happening.

| Excuse | Reality |
|--------|---------|
| "Too simple to test" | Simple code breaks. A test takes 30 seconds. |
| "I'll test after" | Tests written after pass immediately, which proves nothing — you never watched them fail, so you never proved they can catch the bug. |
| "Already manually tested" | Manual testing is ad-hoc: no record of what you covered, no way to re-run it when code changes. |
| "Deleting X hours of work is wasteful" | Sunk cost. Keeping code you can't trust is the real waste. |
| "Need to explore first" | Fine. Throw the exploration away, start the real change with TDD. |
| "TDD will slow me down" | TDD is the pragmatic path: catches bugs before commit, prevents regressions, makes refactoring safe. "Pragmatic" shortcuts mean debugging later — slower, not faster. |
