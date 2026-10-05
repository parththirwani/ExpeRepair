"""
Provenance gate: lexical overlap between candidate content and issue text.

If a candidate patch or test is mostly a paraphrase of the issue statement,
it's untrusted — it may contain hallucinated or planted content.
"""

import re
from typing import Sequence


def tokenize(text: str) -> set[str]:
    """Lowercase, split on non-alnum, return non-empty token set."""
    tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    return {t for t in tokens if len(t) > 1}


def token_jaccard(a: str, b: str) -> float:
    """Jaccard similarity of token sets of two strings. 0.0 = disjoint, 1.0 = identical."""
    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def compute_issue_overlap(issue_text: str, candidate_code: str) -> float:
    """
    Fraction of candidate code tokens that also appear in the issue text.

    This is asymmetric (issue_overlap) rather than symmetric (Jaccard):
    we want to know how much of the *candidate* is derivable from the issue.
    Returns 0.0 to 1.0.
    """
    issue_tokens = tokenize(issue_text)
    code_tokens = tokenize(candidate_code)
    if not code_tokens:
        return 0.0
    supported = code_tokens & issue_tokens
    return len(supported) / len(code_tokens)


def test_patch_overlap(issue_text: str, patch_content: str, threshold: float = 0.65) -> tuple[bool, float]:
    """
    Returns (is_overly_similar, score).

    True means the patch overlaps too much with the issue and should
    be quarantined as untrusted.  Default threshold of 0.65 is a
    starting value — tune on a dev slice.
    """
    # Only check added/modified lines in the patch (lines starting with +)
    added = "\n".join(
        line[1:] for line in patch_content.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )
    if not added.strip():
        return False, 0.0
    score = compute_issue_overlap(issue_text, added)
    return score > threshold, score