# Local retrieval evaluation

local policy retrieval only; not a full-assistant evaluation.

| Configuration | Top-1 matches | LLM requests | LLM tokens | Provider cost |
|---|---:|---:|---:|---:|
| A: word TF-IDF | 23/26 (88.5%) | 0 | 0 | $0.00 |
| B: word + character TF-IDF | 24/26 (92.3%) | 0 | 0 | $0.00 |

## Method

The same frozen questions, five policies, query aliases and relevance threshold are used in both settings. A uses word unigrams/bigrams. B combines 70% word similarity and 30% character 3–5-gram similarity. The primary metric is whether the highest-ranked policy matches the expected source; the out-of-scope case must return no result.

These are small synthetic document-retrieval checks. They do not grade generated answers, fees, identity verification, approval or resistance to live model attacks. Zero requests/tokens/cost means no inference provider was used; local CPU work is still required.

## Mismatches

- A / sla-weekend: expected POL-03, retrieved no result.
- A / refund-arabic: expected POL-06, retrieved no result.
- A / identity-arabic: expected POL-08, retrieved POL-10.
- B / refund-arabic: expected POL-06, retrieved POL-10.
- B / identity-arabic: expected POL-08, retrieved POL-10.
