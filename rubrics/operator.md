---
name: operator
dimensions:
  - key: actionable
    weight: 1.0
    question: Could a builder change what they do THIS WEEK because of it?
    anchors: "0 = pure worldview; 10 = directly executable"
    veto_below: null
  - key: concrete
    weight: 1.0
    question: Is it built from real cases, numbers, named specifics?
    anchors: "0 = armchair reasoning; 10 = dense with lived, specific evidence"
    veto_below: null
  - key: evergreen
    weight: 1.0
    question: Will it still be true in 20 years?
    anchors: "0 = bound to its era's tech or moment; 10 = permanently true"
    veto_below: null
scoring: holistic
tie_break: source_order   # reserved, not implemented yet: ties currently keep the record's existing order
overall_anchors: "9-10 changes how you operate immediately and forever; 7-8 strong usable playbook; 5-6 useful but situational; 3-4 interesting, not usable; 1-2 nothing to use"
---

# The operator rubric

> The rubric is not a config detail. The rubric is the product.

A deliberately different taste from [inspiration.md](inspiration.md): this one is for a
hands-on builder who wants operating knowledge first, philosophy later. Same corpus,
same judges, different rubric — a visibly different book. See
[examples/paul-graham/rubric-comparison.md](../examples/paul-graham/rubric-comparison.md)
for the two rankings side by side.

Judge instructions: judge primarily from the text given; use the full range; dimensions
should NOT be uniformly equal for a given piece. The overall is your holistic call, not
an average.
