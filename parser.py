from __future__ import annotations

from dataclasses import dataclass

from ifp_ast import (
    CHARS,
    CHARS_DECODED,
    TBinOp,
    TBool,
    TIf,
    TInt,
    TLam,
    TString,
    TUnOp,
    TVar,
    Term,
    TLet,
)


@dataclass(frozen=True)
class ParseError(Exception):
    kind: str
    index: int | None = None
    ch: str | None = None

    def __str__(self) -> str:
        if self.kind == "UnexpectedChar":
            return f"UnexpectedChar({self.ch!r}, {self.index})"
        if self.kind == "UnusedInput":
            return f"UnusedInput({self.index})"
        return "UnexpectedEOF"


# Decoding map: CHARS (printable ASCII 33–126) → CHARS_DECODED (alphabet order)
_DECODE_MAP = {src: dst for src, dst in zip(CHARS, CHARS_DECODED)}


def from_base94(s: str) -> int:
    """Convert base-94 encoded string to integer.

    Encoding rule (per spec):
        '!' (ASCII 33) = 0
        '"' (ASCII 34) = 1
        ...
        '~' (ASCII 126) = 93

    Example: '/6'  →  (14)*94 + (21) = 1337
    """
    result = 0
    for ch in s:
        digit = ord(ch) - 33          # map ASCII 33-126 → 0-93
        result = result * 94 + digit
    return result


def decode_string(s: str) -> str:
    """Decode each character of a string body via the IFP alphabet mapping."""
    out: list[str] = []
    for i, ch in enumerate(s):
        decoded = _DECODE_MAP.get(ch)
        if decoded is None:
            raise ParseError("UnexpectedChar", i, ch)
        out.append(decoded)
    return "".join(out)


def p_term(inp: str) -> Term:
    """Parse an IFP-encoded program string into an AST term.
    
    Tokens are space-separated. Each token starts with an indicator character
    that determines the type of the term.
    """
    tokens = inp.split()          # IFP tokens are separated by spaces
    if not tokens:
        raise ParseError("UnexpectedEOF")
    term, pos = _parse_term(tokens, 0)
    if pos < len(tokens):
        raise ParseError("UnusedInput", pos)
    return term


# ---------------------------------------------------------------------------
# Core recursive-descent parser
# ---------------------------------------------------------------------------

def _parse_term(tokens: list[str], pos: int) -> tuple[Term, int]:
    """Parse one term from *tokens* starting at index *pos*.

    Returns (term, next_pos) where next_pos is the first unconsumed token.
    """
    if pos >= len(tokens):
        raise ParseError("UnexpectedEOF")

    tok = tokens[pos]
    if not tok:
        raise ParseError("UnexpectedEOF")

    indicator = tok[0]   # first character -> determines token type
    body      = tok[1:]  # remaining chars -> payload

    # ------------------------------------------------------------------
    # T / F  —  Boolean constants  (body must be empty per spec)
    # ------------------------------------------------------------------
    if indicator == 'T':
        return TBool(True), pos + 1

    if indicator == 'F':
        return TBool(False), pos + 1

    # ------------------------------------------------------------------
    # I  —  Integer literal
    # Body is a non-empty base-94 encoded number
    # Example: I/6 -> 1337
    # ------------------------------------------------------------------
    if indicator == 'I':
        if not body:
            raise ParseError("UnexpectedEOF")
        return TInt(from_base94(body)), pos + 1

    # ------------------------------------------------------------------
    # S  —  String literal
    # Body is decoded character-by-character via IFP alphabet
    # Example: SB%,,/}Q/2,$_ -> "Hello World!"
    # ------------------------------------------------------------------
    if indicator == 'S':
        return TString(decode_string(body)), pos + 1

    # ------------------------------------------------------------------
    # v  —  Variable reference  (LOWERCASE v, per spec)
    # Body is a base-94 encoded variable identifier
    # Example: v# -> var id 2
    # ------------------------------------------------------------------
    if indicator == 'v':
        if not body:
            raise ParseError("UnexpectedEOF")
        return TVar(from_base94(body)), pos + 1

    # ------------------------------------------------------------------
    # L  —  Lambda abstraction
    # Format: L<var_id> <body_expr>
    # Example: L# v#  ->  \v2 -> v2  (identity function)
    # ------------------------------------------------------------------
    if indicator == 'L':
        if not body:
            raise ParseError("UnexpectedEOF")
        var_id = from_base94(body)
        body_term, new_pos = _parse_term(tokens, pos + 1)
        return TLam(var_id, body_term), new_pos

    # ------------------------------------------------------------------
    # U  —  Unary operator
    # Format: U<op>  followed by one expression
    # Supported: -  !  #  $
    # ------------------------------------------------------------------
    if indicator == 'U':
        if len(body) != 1:
            raise ParseError("UnexpectedChar", pos, tok)
        op = body
        operand, new_pos = _parse_term(tokens, pos + 1)
        return TUnOp(op, operand), new_pos

    # ------------------------------------------------------------------
    # B  —  Binary operator
    # Format: B<op>  followed by two expressions
    # Supported: + - * / %  < > =  | &  .  T D  $
    # Note: B$ is function application (call-by-name)
    # ------------------------------------------------------------------
    if indicator == 'B':
        if len(body) != 1:
            raise ParseError("UnexpectedChar", pos, tok)
        op = body
        left,  pos1    = _parse_term(tokens, pos + 1)
        right, new_pos = _parse_term(tokens, pos1)
        return TBinOp(left, op, right), new_pos

    # ------------------------------------------------------------------
    # ?  —  Conditional expression
    # Format: ? <cond> <then_branch> <else_branch>
    # Only the selected branch is evaluated (lazy)
    # Example: ? B> I# I$ Syes Sno  ->  "no"
    # ------------------------------------------------------------------
    if indicator == '?':
        cond,     pos1    = _parse_term(tokens, pos + 1)
        true_br,  pos2    = _parse_term(tokens, pos1)
        false_br, new_pos = _parse_term(tokens, pos2)
        return TIf(cond, true_br, false_br), new_pos

    raise ParseError("UnexpectedChar", pos, tok)
