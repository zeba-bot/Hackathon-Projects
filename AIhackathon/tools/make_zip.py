"""Build the portal upload: python tools/make_zip.py  -> submission.zip (files at ZIP root)"""
import os, zipfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = os.path.join(ROOT, 'submission')
out = os.path.join(ROOT, 'submission.zip')
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for f in ('solution.py', 'feats.py', 'model.json', 'README.md'):
        z.write(os.path.join(src, f), f)
print('wrote', out)
