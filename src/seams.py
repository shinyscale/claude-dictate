"""
Text handling between dictations: the spoken "refine this" command and the
seam repair that joins one dictation onto the previous one.

Pure functions, kept apart from the tray daemon so they can be tested
without a display, a keyboard hook, or a microphone.
"""

import re

# Spoken at the very end of a dictation, this asks for the LLM pass on just
# this one dictation, regardless of the configured paste mode. Trailing-only
# and tightly worded so ordinary sentences can't trip it.
_REFINE_CMD = re.compile(r"\brefine\s+(?:this|that|it)\b[\s.!?]*$", re.IGNORECASE)


def strip_refine_command(text: str) -> tuple:
    """(refine_requested, text with the spoken command removed).

    Loops because the command can appear repeated at the tail ("Refine
    this. Refine this.") when the user says it more than once."""
    requested = False
    while True:
        m = _REFINE_CMD.search(text)
        if not m:
            return requested, text
        requested = True
        text = text[:m.start()].rstrip()


# Sentence-terminal punctuation, and the quote/bracket characters that may
# legitimately trail it ("...done.").
_SENT_END = ".!?…"
_WRAPPERS = "\"'”’)]}»"

# Words no English sentence ends on. Whisper transcribes each dictation in
# isolation and routinely appends a period to an unfinished sentence; a
# trailing "...and the." is a fake sentence break, not a real one.
_FUNCTION_WORDS = frozenset("""
    a an the and or but nor so yet to of in on at by for with from into onto
    over under about above below after before between during through against
    without within around because although though while if when whenever
    unless until since that which who whom whose where why how than as is are
    was were be been being am do does did have has had having will would
    shall should can could may might must not very really quite just also
    then even still only both either neither each every some any no my your
    his her its our their this these those it's don't doesn't isn't aren't
    won't wouldn't couldn't shouldn't
""".split())

_I_PRONOUN = re.compile(r"^[Ii](?:$|['’])")


def join_continuation(prev: str, new: str, vocab) -> tuple:
    """How to append `new` after previously-pasted `prev` in the same field.

    Returns (backspaces, text): press Backspace `backspaces` times, then
    paste `text`. Repairs the seam Whisper can't see: exactly one space
    between chunks; if `prev` broke off mid-sentence, erase the fake
    trailing period (dangling function word) and de-capitalize `new`'s
    first word — unless it's "I", an acronym, or a vocabulary proper noun.
    """
    prev_r = prev.rstrip()
    if not prev_r or not new:
        return 0, new

    core = prev_r.rstrip(_WRAPPERS)
    backspaces = 0
    if core and core[-1] not in _SENT_END:
        mid_thought = True  # ends on a bare word, comma, colon, dash...
    else:
        m = re.search(r"([A-Za-z'’]+)([.!?…]+)$", core)
        mid_thought = bool(
            m and m.group(1).lower().rstrip("'’") in _FUNCTION_WORDS)
        if mid_thought and core == prev_r:
            # No quotes in the way: erase the fake period (plus any
            # trailing whitespace) so the sentence reads straight through.
            backspaces = (len(prev) - len(prev_r)) + len(m.group(2))

    if mid_thought:
        first_word = re.match(r"[A-Za-z'’\-]+", new)
        w = first_word.group(0) if first_word else new[0]
        keep_capital = (
            _I_PRONOUN.match(w) is not None
            or (len(w) > 1 and any(c.isupper() for c in w[1:]))  # DeepSeek, ACX
            or any(v and v.split()[0].lower() == w.lower()
                   and v.split()[0][:1].isupper() for v in vocab)
        )
        if new[0].isupper() and not keep_capital:
            new = new[0].lower() + new[1:]
    elif new[0].islower():
        new = new[0].upper() + new[1:]

    return backspaces, " " + new
