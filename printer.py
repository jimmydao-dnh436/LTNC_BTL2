from __future__ import annotations

from ifp_ast import CHARS, CHARS_DECODED, TBinOp, TBool, TIf, TInt, TLam, TString, TUnOp, TVar, Term, TLet


# Reverse map: decoded char -> encoded char (for string output)
_ENCODE_MAP = {dst: src for src, dst in zip(CHARS, CHARS_DECODED)}


def to_base94(x: int) -> str | None:
    """Encode a non-negative integer as a base-94 string.

    '!' (ASCII 33) = digit 0
    '~' (ASCII 126) = digit 93

    Returns None for negative numbers.
    """
    if x < 0:
        return None
    if x == 0:
        return chr(33)   # single digit '!'

    out: list[str] = []
    n = x
    while n > 0:
        n, m = divmod(n, 94)
        out.append(chr(m + 33))
    out.reverse()
    return "".join(out)


def encode_string(s: str) -> str:
    """Encode a decoded string back to IFP token body."""
    out: list[str] = []
    for ch in s:
        encoded = _ENCODE_MAP.get(ch)
        if encoded is None:
            raise ValueError(f"Cannot encode character: {ch!r}")
        out.append(encoded)
    return "".join(out)


def pp_term(term: Term) -> str:
    """Pretty-print an AST term back to IFP-encoded token string."""

    # Integer: I + base-94 encoded number
    # Negative integers are represented as U- I<positive>
    if isinstance(term, TInt):
        if term.value >= 0:
            b94 = to_base94(term.value)
            return "I" + b94
        else:
            # Negative: U- I<abs>
            return "U- " + pp_term(TInt(-term.value))

    # String: S + encoded body
    if isinstance(term, TString):
        return "S" + encode_string(term.value)

    # Boolean: T or F  (per spec — NOT B1/B0)
    if isinstance(term, TBool):
        return "T" if term.value else "F"

    # Variable: v + base-94 id  (lowercase v, per spec)
    if isinstance(term, TVar):
        b94 = to_base94(term.value)
        if b94 is None:
            raise ValueError("Negative variable id")
        return "v" + b94

    # Lambda: L + base-94 var id + space + body
    if isinstance(term, TLam):
        b94 = to_base94(term.var)
        if b94 is None:
            raise ValueError("Negative variable id in lambda")
        return "L" + b94 + " " + pp_term(term.body)

    # Unary op: U<op> <term>
    if isinstance(term, TUnOp):
        return "U" + term.op + " " + pp_term(term.term)

    # Binary op: B<op> <left> <right>
    if isinstance(term, TBinOp):
        return "B" + term.op + " " + pp_term(term.left) + " " + pp_term(term.right)

    # Conditional: ? <cond> <true> <false>
    if isinstance(term, TIf):
        return (
            "? "
            + pp_term(term.cond)
            + " " + pp_term(term.true_branch)
            + " " + pp_term(term.false_branch)
        )

    # Let (internal use only — not part of public IFP format)
    if isinstance(term, TLet):
        b94 = to_base94(term.var)
        return "= " + b94 + " " + pp_term(term.value) + " " + pp_term(term.body)

    raise TypeError(f"Unknown term type: {type(term).__name__}")
