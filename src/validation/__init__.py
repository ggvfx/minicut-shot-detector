"""
Correctness checks that can block a job.

Split on whether a check needs ffmpeg: `integrity.py` is arithmetic on the shot
list and needs nothing, while `validator.py` decodes frames to compare pixels.
"""
