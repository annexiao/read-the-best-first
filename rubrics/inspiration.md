---
name: inspiration
dimensions:
  - key: insight
    weight: 1.0
    question: Does it tell you something true and important you had never articulated?
    anchors: "0 = restates common knowledge; 10 = something you had never put into words"
    veto_below: null    # set to e.g. 2 to disqualify any piece scoring under 2 here
  - key: contrarian
    weight: 1.0
    question: Does it challenge what most people believe, with substance behind the challenge?
    anchors: "0 = agrees with the crowd; 10 = convincingly overturns a broadly held belief"
    veto_below: null
  - key: reach
    weight: 1.0
    question: Does the idea generalize far beyond its immediate topic?
    anchors: "0 = stays inside its niche; 10 = changes how you think or live"
    veto_below: null
scoring: holistic        # holistic | weighted_mean | median | max | min
tie_break: source_order   # reserved, not implemented yet: ties currently keep the record's existing order
overall_anchors: "9-10 worldview-shifting; 7-8 strong original framework, high transfer; 5-6 solid but topic-bounded; 3-4 competent but conventional or era-bound; 1-2 announcements/occasional pieces"
---

# The inspiration rubric

> The rubric is not a config detail. The rubric is the product.

This is the author's rubric: it front-loads unique insight, contrarian depth, and
philosophical reach, because that is what she wants to hit first when time is scarce.
Yours is different. Edit this file, or copy it to a new file in this directory and
point the pipeline at yours.

## How the fields work

- **dimensions**: what the judges score, each 0-10, independently. Judges read each
  dimension's `question` and `anchors` verbatim. Add, remove, or reword dimensions
  freely; the mechanics don't care how many there are.
- **weight**: used only by the mechanical scoring policies (ignored under `holistic`).
- **veto_below**: a disqualifier. Any piece scoring under this value on this dimension
  is pulled out of the ranking entirely and listed in a separate "vetoed" section of
  the ranking record, regardless of how well it scores elsewhere. Off (`null`) by
  default. Use it for "I don't care how brilliant it is, if it fails X I don't want it."
- **scoring**: how per-dimension scores become the ranking order.
  - `holistic` (default): the judge assigns an overall (1-10) informed by the
    dimensions but not computed from them. Highest quality; changing the rubric means
    re-judging.
  - `weighted_mean`, `median`, `max`, `min`: mechanical aggregation over the recorded
    dimension scores. Changing weights or policy re-ranks in seconds from the ranking
    record with NO re-judging (`scripts/rerank.py`). `max` is the power-law option:
    one transcendent dimension is enough. `min` demands no weak dimensions.
- **tie_break**: reserved for a future version; the current script keeps the record's existing order on ties.

## Judge instructions (included verbatim in the judging prompt)

Judge primarily from the text given; weigh known reputation only lightly. Be
discriminating; use the full range on every dimension; dimensions should NOT be
uniformly equal for a given piece. The overall is your holistic call, not an average:
a spiky piece can deserve a high overall on the strength of one dimension.
