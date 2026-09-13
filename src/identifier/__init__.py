"""
The Identifier: a folder of shots in, shot numbers out.

Takes **any** folder of single-shot video files. It may read a splitter sidecar
if one happens to be beside them, but never requires one — most batches arrive
from somewhere else, and nobody should have to run the splitter to use this.

Three model passes, and the split between them is the design:

    observe     frames  -> plain observations, no project knowledge at all
    interpret   text    -> the project's own vocabulary and character names
    match       text    -> a shot number, a derived confidence, and notes

Only `observe` needs images or a vision model, it runs once per shot, and its
result is cached. Everything a user iterates on — the terminology file, the
character sheet, a corrected shot list — re-runs the two text passes over that
cache in seconds.

Then one of two outputs: rename the files to carry their shot numbers, or
export a breakdown with thumbnails to seed a database from a blockout.

Unlike the splitter, this is judgement work and cannot be deterministic. That
is why a person reviews every row before anything is renamed.
"""
