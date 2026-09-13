"""
Reading a Model's Freehand Reply.

Shared by the observation and interpretation passes. Both ask for `field:
answer` and both get back whatever the model felt like writing, so both need
the same tolerances — and when they each had their own copy, a gap in one was
a gap in both, found in one and left in the other.

Every allowance here is the shape of something a model actually returned. None
of it is defensive programming in the abstract: a batch of forty shots must not
fail because one reply arrived bolded, fenced or prefaced.
"""

import re
from typing import Iterable

# Stripped from the front of an answer after the label. Markdown emphasis
# routinely wraps the whole label — `**shot_size:** CU` — and the closing
# asterisks land in the value. Restricted to emphasis characters rather than
# any non-word character, because a legitimate answer can open with a bracket.
LEADING_MARKUP = "*_`"


def field_value(text: str, name: str, others: Iterable[str]) -> str:
    """
    One field's answer: everything after its label, up to the next label.

    Args:
        text: The reply, already unfenced.
        name: The field to read.
        others: Every other field name, which is what bounds the answer.

    Returns:
        The answer with its label and any markup stripped, or "" if the field
        was not answered.

    Notes:
        Bounded by the other field names rather than by the end of the line.
        A model asked for one figure per line will answer `appearance` over
        four lines and then start the next field, and taking only the first
        line would throw away three quarters of a useful answer.
    """
    boundary = "|".join(re.escape(other) for other in others)
    match = re.search(
        rf"^\W*{re.escape(name)}\W*:[{re.escape(LEADING_MARKUP)}\s]*(.*?)"
        rf"(?=^\W*(?:{boundary})\W*:|\Z)",
        text,
        re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )

    return match.group(1).strip() if match else ""


def unfence(reply: str) -> str:
    """
    The reply without the code fence some models wrap it in.

    Asked for plain `field: answer` lines, a model will decide that is
    structured output and fence it as though it were code.
    """
    return re.sub(r"^```[a-z]*\n?|```$", "", reply.strip(), flags=re.MULTILINE)


def strip_bullet(line: str) -> str:
    """
    One line of a list, without its bullet or numbering.

    Asked for one entry per line, models number them, dash them, or do neither,
    and all three have to arrive downstream looking the same.
    """
    return re.sub(r"^[-*\d.)\s]+", "", line).strip()
