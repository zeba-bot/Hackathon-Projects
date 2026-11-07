# Development datasets — public-expanded-1

This packet replaces the small demonstration pool with 60 ordinary training examples and 20 separate ordinary practice examples. `smoke.json` is the first two training examples for a quick setup check; it is deliberately a subset, not a third independent dataset. `dataset_info.json` records counts, provenance and a group_index mapping each file row to its source group for tuning folds. `baseline_results.json` records the supplied starter's scores; it is a reference, not a target or a claim of optimal performance.

Keep all examples from one customer/world/source shard/source day together when making your own tuning folds. Changed variants remain in the same partition as their ordinary counterparts. The twist supplement contains changed training and changed practice only after release. Private official cohorts are unchanged.

## Run locally

Use Python 3.12; AIML additionally requires NumPy. Run commands from the extracted packet directory.

```sh
python local_check.py solution.py smoke.json
python local_check.py solution.py training.json
python local_check.py solution.py practice.json
```
