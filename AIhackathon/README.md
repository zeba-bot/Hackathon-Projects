# Hackmatrix 1.0 - FinTech payment reconciliation

```
hackmatrix_fintech/
  submission/        <- the code that gets uploaded (solution.py, feats.py, model.json)
  tools/
    local_eval.py    <- score + integrity check on training data
    train.py         <- retrain model.json
    make_zip.py      <- build submission.zip for the portal
  data/              <- training.json, SCHEMA.md, OBSERVATIONS.md
  requirements.txt   <- numpy, scipy (portal also provides pandas, scikit-learn)
```

Commands (run from this folder, Python 3.12):
```
pip install -r requirements.txt
python tools/local_eval.py     # expect ~95 mean score, 0 integrity failures
python tools/train.py          # optional: refit weights after changing features
python tools/make_zip.py       # creates submission.zip -> upload to the portal
```

Where to edit:
- `submission/feats.py`    candidate rules + features (add new clues here, then retrain)
- `submission/solution.py` decision rule (PARAMS: match_threshold=0.8), query choice, posting
Note: if you add/remove features in feats.py you MUST run tools/train.py to refresh model.json.
