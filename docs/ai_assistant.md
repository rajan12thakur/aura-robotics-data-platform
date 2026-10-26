# AURA assistant

## Implemented mode

The deterministic local assistant is always available. Supported intents
include validation/error/quality status, project summary and label counts,
approved-export behavior, and policy explanations. The response includes an
interaction ID, mode, tool summary, evidence references, and suggested actions.
Unsupported questions receive a limitation message rather than a fabricated
answer.

## Tools and evidence

Internal operations are fixed and typed: policy section search, project
quality/summary reads, and annotation/validation evidence reads. The assistant
does not accept arbitrary SQL, shell, Python, or unrestricted file access.
Evidence is bounded before it is returned. Policy references point to
`annotation_policy_v1.md`; validation references contain persisted run IDs and
real issue details.

The retrieval method splits only the canonical policy at headings, then ranks
sections by keyword overlap. It is a small deterministic lexical retriever,
not embeddings or a semantic vector index.

## Provider, safety and evaluation

No LLM provider adapter is implemented. `AURA_LLM_*` values are reserved
configuration placeholders and do not enable provider calls. No video bytes or
whole datasets are sent externally. Assistant suggestions never modify or
approve annotations.

Later evaluation should measure tool-call correctness, factual answer
accuracy, evidence support, unsupported-claim rate, task completion,
latency/cost, retrieval relevance, and human correction rate. No evaluation
scores are available yet.
