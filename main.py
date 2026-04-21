from __future__ import annotations

import sys

from ifp_ast import TBool, TInt, TString, Term
from interpreter import InterpreterError, interpret
from parser import ParseError, p_term
from printer import pp_term


def _render_value(term: Term) -> str:
    if isinstance(term, TInt):
        return str(term.value)
    if isinstance(term, TBool):
        return "true" if term.value else "false"
    if isinstance(term, TString):
        return term.value
    return pp_term(term)


def cmd_eval(program: str, check_max: bool) -> int:
    try:
        term = p_term(program)
        result, steps = interpret(check_max=check_max, term=term)
    except ParseError as exc:
        print(f"Parse error: {exc}", file=sys.stderr)
        return 2
    except InterpreterError as exc:
        print(f"Interpreter error: {exc}", file=sys.stderr)
        return 3

    print(f"Result (human):        {_render_value(result)}")
    print(f"Result (encoded term): {pp_term(result)}")
    print(f"Steps: {steps}")
    return 0


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="IFP Mini Interpreter")
    parser.add_argument("program", nargs="?", help="Encoded program to evaluate")
    parser.add_argument("-c", "--check-max", action="store_true", help="Enable max step checking")
    parser.add_argument("-t", "--test", action="store_true", help="Run built-in tests")
    args = parser.parse_args()

    if args.test:
        return run_tests()

    if args.program:
        return cmd_eval(args.program, check_max=args.check_max)

    print("Enter encoded phrase to evaluate (Ctrl+C to exit):")
    try:
        program = input().strip()
    except EOFError:
        print("No input program provided.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nExiting.")
        return 0

    if not program:
        print("No input program provided.", file=sys.stderr)
        return 1

    return cmd_eval(program, check_max=args.check_max)


def run_tests() -> int:
    """Run test suite based on spec examples."""
    tests = [
        # ── Literals ────────────────────────────────────────────────────────
        ("Boolean true",             "T",                "true"),
        ("Boolean false",            "F",                "false"),
        ("Integer I/6",              "I/6",              "1337"),
        ("Integer I!",               "I!",               "0"),
        ("Integer I\"",              'I"',               "1"),
        # SB%,,/}Q/2,$_ -> Hello World!
        ("String Hello World!",      "SB%,,/}Q/2,$_",   "Hello World!"),

        # ── Unary ops ───────────────────────────────────────────────────────
        ("Negate int",               "U- I$",            "-3"),
        ("Boolean not T",            "U! T",             "false"),
        ("Boolean not F",            "U! F",             "true"),
        # U# S4%34 -> 15818151  (string "test" interpreted as base-94 integer)
        ("String to int U#",         "U# S4%34",         "15818151"),
        # U$ I4%34 -> "test"
        ("Int to string U$",         "U$ I4%34",         "test"),

        # ── Binary arithmetic ────────────────────────────────────────────────
        # I# = 2, I$ = 3  (from spec examples)
        ("Add B+ I# I$",             "B+ I# I$",         "5"),
        ("Sub B- I$ I#",             "B- I$ I#",         "1"),
        ("Mul B* I$ I#",             "B* I$ I#",         "6"),
        # B/ U- I( I#  ->  -7 / 2 = -3  (truncate toward 0)
        ("Div truncate toward 0",    "B/ U- I( I#",      "-3"),
        # B% U- I( I#  ->  -7 % 2 = -1
        ("Mod truncate toward 0",    "B% U- I( I#",      "-1"),

        # ── Comparison ──────────────────────────────────────────────────────
        ("Less false B< I$ I#",      "B< I$ I#",         "false"),
        ("Greater true B> I$ I#",    "B> I$ I#",         "true"),
        ("Equal false B= I$ I#",     "B= I$ I#",         "false"),
        ("Equal true B= I$ I$",      "B= I$ I$",         "true"),

        # ── Logical ─────────────────────────────────────────────────────────
        ("OR  B| T F",               "B| T F",           "true"),
        ("AND B& T F",               "B& T F",           "false"),

        # ── String ops ──────────────────────────────────────────────────────
        # B. S4% S34 -> "test"  (S4% = "te", S34 = "st")
        ("Concat B. S4% S34",        "B. S4% S34",       "test"),
        # BT I$ S4%34 -> "tes"  (take 3 chars from "test")
        ("Take BT I$ S4%34",         "BT I$ S4%34",      "tes"),
        # BD I$ S4%34 -> "t"  (drop 3 chars from "test")
        ("Drop BD I$ S4%34",         "BD I$ S4%34",      "t"),

        # ── Conditional ─────────────────────────────────────────────────────
        # ? B> I# I$ S9%3 S./  ->  "no"  (2 > 3 is false)
        ("If false branch",          "? B> I# I$ S9%3 S./",  "no"),
        # ? B< I# I$ S9%3 S./  ->  "yes"
        ("If true branch",           "? B< I# I$ S9%3 S./",  "yes"),

        # ── Function application ─────────────────────────────────────────────
        # B$ B$ L# L$ v# B. SB%,,/ S}Q/2,$_ IK
        #   = ((\v2 -> \v3 -> v2) ("Hello" . " World!")) 42  ->  "Hello World!"
        # NOTE: S}Q/2,$_ uses '_' which decodes to '!'
        ("Func app Hello World",
            "B$ B$ L# L$ v# B. SB%,,/ S}Q/2,$_ IK",
            "Hello World!"),

        # ── Spec reduction example ───────────────────────────────────────────
        # B$ L# B$ L" B+ v" v" B* I$ I# v8
        #   step 1: v# = v8  (unused)  -> B$ L" B+ v" v" B* I$ I#
        #   step 2: v" = B* I$ I#      -> B+ (B* I$ I#) (B* I$ I#)
        #   step 3: B* I$ I# = 3*2 = 6 (evaluated twice, call-by-name)
        #   result: 6 + 6 = 12  (I- in base94)
        ("Call-by-name reduction",
            'B$ L# B$ L" B+ v" v" B* I$ I# v8',
            "12"),

        # ── Spec big example (should evaluate to 16 in 109 steps) ───────────
        (
            "Big recursion example (=16)",
            'B$ B$ L" B$ L# B$ v" B$ v# v# L# B$ v" B$ v# v# L" L# ? B= v# I! I" B$ L$ B+ B$ v" v$ B$ v" v$ B- v# I" I%',
            "16",
        ),
    ]

    passed = 0
    failed = 0

    print("=" * 70)
    print("IFP MINI INTERPRETER — TEST SUITE")
    print("=" * 70)

    for name, program, expected in tests:
        try:
            term   = p_term(program)
            result, steps = interpret(check_max=False, term=term)
            actual = _render_value(result)

            if actual == expected:
                print(f"[PASS] {name}  (steps={steps})")
                passed += 1
            else:
                print(f"[FAIL] {name}")
                print(f"       input:    {program}")
                print(f"       expected: {expected!r}")
                print(f"       actual:   {actual!r}")
                failed += 1
        except Exception as exc:
            print(f"[ERR ] {name}")
            print(f"       input: {program}")
            print(f"       error: {exc}")
            failed += 1

    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed out of {passed+failed} tests")
    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())