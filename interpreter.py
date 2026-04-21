from __future__ import annotations

from dataclasses import dataclass

from ifp_ast import (
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
from printer import to_base94, encode_string
from ifp_ast import CHARS, CHARS_DECODED


MAX_STEPS = 10_000_000


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------

class InterpreterError(Exception):
    """Base class for interpreter errors."""
    pass

class BetaReductionLimit(InterpreterError):
    """Raised when evaluation step count exceeds MAX_STEPS."""
    pass

class ScopeError(InterpreterError):
    """Raised when a variable is not found in environment."""
    pass

class TypeError_(InterpreterError):
    """Raised when operation receives wrong value types."""
    pass

class ArithmeticError_(InterpreterError):
    """Raised for arithmetic errors like division by zero."""
    pass

class UnknownUnOp(InterpreterError):
    def __init__(self, op: str):
        super().__init__(f"Unknown unary operator: {op}")
        self.op = op

class UnknownBinOp(InterpreterError):
    def __init__(self, op: str):
        super().__init__(f"Unknown binary operator: {op}")
        self.op = op


# ---------------------------------------------------------------------------
# Runtime value types
# ---------------------------------------------------------------------------

@dataclass
class VInt:
    value: int
    def __repr__(self): return f"VInt({self.value})"

@dataclass
class VBool:
    value: bool
    def __repr__(self): return f"VBool({self.value})"

@dataclass
class VString:
    value: str
    def __repr__(self): return f"VString({self.value!r})"

@dataclass
class VClosure:
    var:  int
    body: Term
    env:  dict[int, "Thunk"]
    def __repr__(self): return f"VClosure(var={self.var}, ...)"


Value = VInt | VBool | VString | VClosure


# ---------------------------------------------------------------------------
# Thunk — delayed / memoised computation
# ---------------------------------------------------------------------------

@dataclass
class Thunk:
    """Delayed computation holder for call-by-name / call-by-need evaluation.

    kind:
        "value"  — already evaluated; use .value
        "thunk"  — not yet evaluated; use .term + .env
    """
    kind:  str
    value: Value | None          = None
    steps: int                   = 0
    term:  Term | None           = None
    env:   dict[int, "Thunk"] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_term(v: Value) -> Term:
    """Convert a runtime value back to an AST term (for final output)."""
    if isinstance(v, VInt):    return TInt(v.value)
    if isinstance(v, VBool):   return TBool(v.value)
    if isinstance(v, VString): return TString(v.value)
    if isinstance(v, VClosure):return TLam(v.var, v.body)
    raise TypeError(f"Unknown value type: {type(v).__name__}")


def _lookup(env: dict[int, Thunk], var: int) -> Thunk:
    if var not in env:
        raise ScopeError(f"Variable {var} not found in scope")
    return env[var]


def _force(thunk: Thunk) -> Value:
    """Force a thunk to obtain its value (with memoisation for call-by-need)."""
    if thunk.kind == "value":
        return thunk.value

    global _current_steps
    _current_steps += 1
    if _current_steps > MAX_STEPS:
        raise BetaReductionLimit("Maximum evaluation steps exceeded")

    value = _eval_term(thunk.term, thunk.env)

    # Memoise (call-by-need behaviour)
    thunk.kind  = "value"
    thunk.value = value
    thunk.term  = None
    thunk.env   = None
    return value


# ---------------------------------------------------------------------------
# String <-> integer conversion helpers (U# and U$)
# ---------------------------------------------------------------------------

_DECODE_MAP = {src: dst for src, dst in zip(CHARS, CHARS_DECODED)}
_ENCODE_MAP = {dst: src for src, dst in zip(CHARS, CHARS_DECODED)}


def _string_to_int(s: str) -> int:
    """U# — interpret string characters as base-94 digits."""
    result = 0
    for ch in s:
        # The string is already decoded; we need to re-encode to get the digit
        encoded = _ENCODE_MAP.get(ch)
        if encoded is None:
            raise TypeError_(f"Cannot convert character {ch!r} to base-94 digit")
        digit = ord(encoded) - 33
        result = result * 94 + digit
    return result


def _int_to_string(n: int) -> str:
    """U$ — convert integer to string using base-94 encoding."""
    if n < 0:
        raise TypeError_("Cannot convert negative integer to string")
    if n == 0:
        encoded = chr(33)   # '!' = digit 0
        return _DECODE_MAP[encoded]

    digits: list[str] = []
    m = n
    while m > 0:
        m, r = divmod(m, 94)
        encoded_ch = chr(r + 33)
        digits.append(_DECODE_MAP[encoded_ch])
    digits.reverse()
    return "".join(digits)


# ---------------------------------------------------------------------------
# Core evaluator
# ---------------------------------------------------------------------------

def _eval_term(t: Term, env: dict[int, Thunk]) -> Value:
    """Evaluate a term in the given environment."""
    global _current_steps

    _current_steps += 1
    if _current_steps > MAX_STEPS:
        raise BetaReductionLimit("Maximum evaluation steps exceeded")

    match t:
        case TInt(value):
            return VInt(value)

        case TBool(value):
            return VBool(value)

        case TString(value):
            return VString(value)

        case TVar(value):
            thunk = _lookup(env, value)
            return _force(thunk)

        case TLam(var, body):
            return VClosure(var, body, env.copy())

        case TUnOp(op, term):
            v = _eval_term(term, env)
            return _eval_unop(op, v)

        case TBinOp(left, op, right):
            return _eval_binop(left, op, right, env)

        case TIf(cond, true_branch, false_branch):
            # Only the selected branch is evaluated (spec requirement)
            cond_val = _eval_term(cond, env)
            if not isinstance(cond_val, VBool):
                raise TypeError_(f"Condition must be boolean, got {type(cond_val).__name__}")
            if cond_val.value:
                return _eval_term(true_branch, env)
            else:
                return _eval_term(false_branch, env)

        case TLet(var, value, body):
            # Let is sugar for immediate lambda application
            new_env = env.copy()
            new_env[var] = Thunk(kind="thunk", term=value, env=env)
            return _eval_term(body, new_env)

        case _:
            raise TypeError_(f"Unknown term type: {type(t).__name__}")


def _eval_unop(op: str, v: Value) -> Value:
    """Evaluate a unary operator."""
    match op:
        case "-":
            if isinstance(v, VInt):
                return VInt(-v.value)
            raise TypeError_(f"'-' requires integer, got {type(v).__name__}")

        case "!":
            if isinstance(v, VBool):
                return VBool(not v.value)
            raise TypeError_(f"'!' requires boolean, got {type(v).__name__}")

        case "#":
            # U# — convert string to integer using base-94
            if isinstance(v, VString):
                return VInt(_string_to_int(v.value))
            raise TypeError_(f"'#' requires string, got {type(v).__name__}")

        case "$":
            # U$ — convert integer to string using base-94
            if isinstance(v, VInt):
                return VString(_int_to_string(v.value))
            raise TypeError_(f"'$' requires integer, got {type(v).__name__}")

        case _:
            raise UnknownUnOp(op)


def _eval_binop(left: Term, op: str, right: Term, env: dict[int, Thunk]) -> Value:
    """Evaluate a binary operator."""
    match op:

        # ---- Arithmetic -----------------------------------------------
        case "+":
            lv, rv = _eval_term(left, env), _eval_term(right, env)
            if isinstance(lv, VInt) and isinstance(rv, VInt):
                return VInt(lv.value + rv.value)
            raise TypeError_(f"'+' requires integers")

        case "-":
            lv, rv = _eval_term(left, env), _eval_term(right, env)
            if isinstance(lv, VInt) and isinstance(rv, VInt):
                return VInt(lv.value - rv.value)
            raise TypeError_(f"'-' requires integers")

        case "*":
            lv, rv = _eval_term(left, env), _eval_term(right, env)
            if isinstance(lv, VInt) and isinstance(rv, VInt):
                return VInt(lv.value * rv.value)
            raise TypeError_(f"'*' requires integers")

        case "/":
            lv, rv = _eval_term(left, env), _eval_term(right, env)
            if isinstance(lv, VInt) and isinstance(rv, VInt):
                if rv.value == 0:
                    raise ArithmeticError_("Division by zero")
                # Spec: truncate toward 0
                return VInt(int(lv.value / rv.value))
            raise TypeError_(f"'/' requires integers")

        case "%":
            # Modulo — truncates toward 0 (same sign convention as division)
            lv, rv = _eval_term(left, env), _eval_term(right, env)
            if isinstance(lv, VInt) and isinstance(rv, VInt):
                if rv.value == 0:
                    raise ArithmeticError_("Modulo by zero")
                # Python % always non-negative; spec example: -7 % 3 = -1
                result = int(lv.value / rv.value)
                return VInt(lv.value - result * rv.value)
            raise TypeError_(f"'%' requires integers")

        # ---- Comparison -----------------------------------------------
        case "<":
            lv, rv = _eval_term(left, env), _eval_term(right, env)
            if isinstance(lv, VInt) and isinstance(rv, VInt):
                return VBool(lv.value < rv.value)
            raise TypeError_(f"'<' requires integers")

        case ">":
            lv, rv = _eval_term(left, env), _eval_term(right, env)
            if isinstance(lv, VInt) and isinstance(rv, VInt):
                return VBool(lv.value > rv.value)
            raise TypeError_(f"'>' requires integers")

        case "=":
            lv, rv = _eval_term(left, env), _eval_term(right, env)
            if type(lv) is not type(rv):
                return VBool(False)
            if isinstance(lv, (VInt, VBool, VString)):
                return VBool(lv.value == rv.value)   # type: ignore[union-attr]
            return VBool(False)

        # ---- Logical (short-circuit) ----------------------------------
        case "&":
            lv = _eval_term(left, env)
            if not (isinstance(lv, VBool) and lv.value):
                return VBool(False)
            rv = _eval_term(right, env)
            if not isinstance(rv, VBool):
                raise TypeError_(f"'&' requires booleans")
            return VBool(rv.value)

        case "|":
            lv = _eval_term(left, env)
            if isinstance(lv, VBool) and lv.value:
                return VBool(True)
            rv = _eval_term(right, env)
            if not isinstance(rv, VBool):
                raise TypeError_(f"'|' requires booleans")
            return VBool(rv.value)

        # ---- String operations ----------------------------------------
        case ".":
            lv, rv = _eval_term(left, env), _eval_term(right, env)
            if isinstance(lv, VString) and isinstance(rv, VString):
                return VString(lv.value + rv.value)
            raise TypeError_(f"'.' requires strings")

        case "T":
            # BT n s — take first n characters of string s
            lv, rv = _eval_term(left, env), _eval_term(right, env)
            if isinstance(lv, VInt) and isinstance(rv, VString):
                return VString(rv.value[:lv.value])
            raise TypeError_(f"'T' (take) requires integer and string")

        case "D":
            # BD n s — drop first n characters of string s
            lv, rv = _eval_term(left, env), _eval_term(right, env)
            if isinstance(lv, VInt) and isinstance(rv, VString):
                return VString(rv.value[lv.value:])
            raise TypeError_(f"'D' (drop) requires integer and string")

        # ---- Function application (call-by-name) ----------------------
        case "$":
            # B$ func arg
            # Evaluate the function side; pass arg as an unevaluated thunk
            func_val = _eval_term(left, env)
            if not isinstance(func_val, VClosure):
                raise TypeError_(f"'$' left side must be a function, got {type(func_val).__name__}")

            # Call-by-name: wrap argument in a thunk (do NOT evaluate yet)
            arg_thunk = Thunk(kind="thunk", term=right, env=env)

            # Extend the closure's captured environment with the argument
            new_env = func_val.env.copy()
            new_env[func_val.var] = arg_thunk

            return _eval_term(func_val.body, new_env)

        case _:
            raise UnknownBinOp(op)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

_current_steps: int = 0


def interpret(check_max: bool, term: Term, strategy: str = "lazy") -> tuple[Term, int]:
    """Interpret a term and return (result_term, step_count)."""
    global _current_steps
    _current_steps = 0

    result = _eval_term(term, {})
    return _to_term(result), _current_steps
