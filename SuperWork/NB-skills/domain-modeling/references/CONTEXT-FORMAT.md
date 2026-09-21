# 术语表格式 (Glossary Format)

The glossary lives as a section inside `docs/技术依据.md` (not a standalone `CONTEXT.md`). The rest of `技术依据.md` holds official sources and pending standards; the glossary is one titled section there. Register the file in 文档导航 (per doc-index) once when it is first created.

## Section structure

```md
## 术语表

**Order**:
{A one or two sentence description of the term}
_Avoid_: Purchase, transaction

**Invoice**:
A request for payment sent to a customer after delivery.
_Avoid_: Bill, payment request

**Customer**:
A person or organization that places orders.
_Avoid_: Client, buyer, account
```

## Rules

- **Be opinionated.** When multiple words exist for the same concept, pick the best one and list the others under `_Avoid_`.
- **Keep definitions tight.** One or two sentences max. Define what it IS, not what it does.
- **Only include terms specific to this project's domain.** General programming concepts (timeouts, error types, utility patterns) don't belong even if the project uses them extensively. Before adding a term, ask: is this a concept unique to this domain, or a general programming concept? Only the former belongs.
- **Group terms under subheadings** when natural clusters emerge. If all terms belong to a single cohesive area, a flat list is fine.

## Single vs multi-context

- **Single context (most repos):** one glossary section in `docs/技术依据.md`.
- **Multiple contexts:** if `docs/文档导航.md` declares per-context glossary homes (a context map), each context gets its own glossary file; the map lists where each lives and how they relate. If no map is declared, keep one glossary and tag terms with their context.
