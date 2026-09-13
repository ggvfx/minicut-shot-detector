# Golden Set

Hand-labelled ground truth: one CSV per test video, listing the frame number of
every true cut.

```
# reel_01.csv
frame,note
143,
       
612,camera flash two frames earlier
1544,whip pan into next shot
```

The videos themselves are **not** committed — they live in `tests/media/`,
which is gitignored. The CSVs are the tracked part.

## What this is for

Not to validate the detectors. Their accuracy on hard cuts is a known quantity.

This validates *our pipeline*: off-by-one errors between detector output and
frame index, frame rate conversion mistakes at 23.976 and 29.97, the cutter
landing on the wrong side of a boundary, mezzanine frames dropped or duplicated.
A correct model wired up slightly wrong produces output that looks fine in a
thumbnail and is wrong in every clip.

## How it is scored

Precision and recall with a ±2 frame tolerance. Tune against this, never by
eye, and re-run it on every parameter change — it is the regression suite.
