---
description: Build or query a kb-core knowledge graph
---

Invoke the `kb-core` skill immediately.

Pass the full `/kb-core` argument string through unchanged.
If no arguments were supplied, treat the target path as `.`.

Examples:
- `/kb-core`
- `/kb-core src --update`
- `/kb-core query "what connects auth to billing?"`

Do not answer from raw files before handing off to the `kb-core` skill.
