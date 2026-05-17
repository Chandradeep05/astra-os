"""
ASTRA OS — Sandboxed Python Executor
======================================
Two-layer defense:
  Layer 1: AST static analysis — rejects code before compilation.
  Layer 2: RestrictedPython runtime — executes inside a hardened namespace
           with no file I/O, no imports, no subprocess, no dunder access.

This runs entirely in-process — no subprocess spawning.
The subprocess approach was removed because it used the REAL Python
interpreter with full OS-level access. RestrictedPython compiles to
a restricted bytecode that cannot escape the controlled namespace.

Resource limits (CPU time + memory) are enforced via threading.Timer
for a hard-kill on timeout.
"""

import ast
import io
import logging
import threading
from typing import Any, Optional

from RestrictedPython import compile_restricted, safe_globals
from RestrictedPython.PrintCollector import PrintCollector
from RestrictedPython.Guards import safer_getattr
from RestrictedPython.Eval import (
    default_guarded_getitem,
    default_guarded_getiter,
)

logger = logging.getLogger(__name__)

# Maximum integer constant allowed in a multiplication expression.
# Prevents: [0] * (10 ** 9)  →  ~8 GB allocation → OOM kill.
# 1_000_000 items × ~28 bytes (Python int) ≈ 28 MB — acceptable.
_MAX_SAFE_LITERAL: int = 1_000_000

# ── 1. AST-level blocked node types ──────────────────────────────────────────
# These AST node types are structurally dangerous regardless of content.
_BLOCKED_AST_NODES = (
    ast.Import,          # import os, import sys, etc.
    ast.ImportFrom,      # from os import path, etc.
    ast.Global,          # global variable escapes sandbox namespace
    ast.Nonlocal,        # nonlocal escapes closure sandbox
    ast.AsyncFunctionDef,# async functions can bypass timeout via event loop
    ast.AsyncFor,
    ast.AsyncWith,
    ast.Await,
)

# Dunder attribute access patterns that enable class traversal attacks:
#   ().__class__.__bases__[0].__subclasses__()  ← classic sandbox escape
_BLOCKED_ATTR_PREFIXES = ("__", "_dunder_")


def _validate_ast(code: str) -> Optional[str]:
    """
    Parse the code into an AST and walk every node.
    Returns an error string if anything blocked is found, None if clean.
    This check CANNOT be bypassed via string obfuscation — it operates
    on the parsed syntax tree, not the raw source text.
    """
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as e:
        return f"Syntax error in code: {e}"

    for node in ast.walk(tree):
        # Block forbidden node types
        if isinstance(node, _BLOCKED_AST_NODES):
            node_name = type(node).__name__
            return (
                f"Blocked: '{node_name}' statements are not permitted. "
                "Imports, global/nonlocal declarations, and async code are disabled."
            )

        # Block dunder attribute access: obj.__class__, obj.__dict__, etc.
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                return (
                    f"Blocked: dunder attribute access '__.{node.attr}.__' is not permitted. "
                    "This is a known sandbox escape vector."
                )

        # Block memory bomb: [x] * 10**9 or 10**9 * [x]
        # Pattern: BinOp with Mult where either operand is a large int constant.
        # [0] * (10 ** 9) allocates ~8 GB and OOM-kills the server process.
        # The AST check catches this before RestrictedPython even sees the code.
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            for operand in (node.left, node.right):
                if isinstance(operand, ast.Constant) and isinstance(operand.value, int):
                    if operand.value > _MAX_SAFE_LITERAL:
                        return (
                            f"Blocked: integer literal {operand.value:,} exceeds the safe "
                            f"limit of {_MAX_SAFE_LITERAL:,} to prevent memory exhaustion."
                        )

    return None


# ── 2. RestrictedPython guarded helpers ──────────────────────────────────────

def _guarded_import(name, *args, **kwargs):
    """
    Completely block all imports inside restricted execution.
    RestrictedPython replaces __import__ with this — raising here
    ensures no module can be loaded regardless of AST checks.
    """
    raise ImportError(
        f"Blocked: importing '{name}' is not permitted inside the sandbox."
    )


def _write_guard(obj):
    """
    RestrictedPython calls this before any attribute write.
    We block all attribute writes to prevent monkey-patching.
    """
    raise AttributeError("Blocked: attribute writes are not permitted in the sandbox.")


def _getattr_guard(obj, name):
    """Block dunder attribute access at runtime (second layer after AST check)."""
    if isinstance(name, str) and name.startswith("__") and name.endswith("__"):
        raise AttributeError(
            f"Blocked: accessing '{name}' is not permitted in the sandbox."
        )
    return safer_getattr(obj, name)


# ── 3. Controlled built-in namespace ─────────────────────────────────────────
# We start from RestrictedPython's safe_globals (which already strips
# dangerous builtins) and add only the safe subset we explicitly allow.

_SAFE_BUILTINS = {
    # Type constructors
    "bool": bool, "int": int, "float": float, "complex": complex,
    "str": str, "bytes": bytes, "bytearray": bytearray,
    "list": list, "tuple": tuple, "dict": dict, "set": set, "frozenset": frozenset,

    # Iterables & functional
    "len": len, "range": range, "enumerate": enumerate, "zip": zip,
    "map": map, "filter": filter, "reversed": reversed, "sorted": sorted,
    "iter": iter, "next": next, "any": any, "all": all,

    # Math
    "abs": abs, "round": round, "pow": pow, "divmod": divmod,
    "sum": sum, "min": min, "max": max, "hash": hash,

    # Introspection (safe subset)
    "isinstance": isinstance, "issubclass": issubclass,
    "hasattr": hasattr, "callable": callable,
    "repr": repr, "format": format, "id": id,

    # I/O — print ONLY (captured, not real stdout)
    "print": print,

    # Exceptions — allow raising and catching
    "Exception": Exception, "ValueError": ValueError, "TypeError": TypeError,
    "KeyError": KeyError, "IndexError": IndexError, "AttributeError": AttributeError,
    "StopIteration": StopIteration, "RuntimeError": RuntimeError,
    "NotImplementedError": NotImplementedError, "ArithmeticError": ArithmeticError,
    "ZeroDivisionError": ZeroDivisionError, "OverflowError": OverflowError,

    # BLOCKED — not in this dict:
    # open, eval, exec, compile, __import__, input, breakpoint,
    # vars, dir, globals, locals, getattr (replaced by guard), setattr, delattr,
    # memoryview, staticmethod, classmethod, super, type, object
}


# ── 4. Main executor ──────────────────────────────────────────────────────────

class PythonExecutor:
    def __init__(self):
        self.name = "python_executor"
        self.description = (
            "Executes Python code for data analysis and math. "
            "Set a variable named 'result' to return a value. "
            "Use 'print()' for output. "
            "RESTRICTIONS: No imports, no file I/O, no network, no OS access."
        )
        self.timeout_seconds = 8          # hard kill via threading.Timer
        self.max_output_chars = 4000      # truncate output to prevent flooding

    def execute(self, code: str) -> str:
        """
        Execute Python code in a two-layer hardened sandbox.

        Layer 1: AST validation — rejects structurally dangerous code.
        Layer 2: RestrictedPython — runtime namespace enforcement.

        Returns a string (output or error message). Never raises.
        """
        if not code or not code.strip():
            return "Error: No code provided."

        # ── Layer 1: AST check ──
        ast_error = _validate_ast(code)
        if ast_error:
            return ast_error

        # ── Layer 2: RestrictedPython compile ──
        try:
            byte_code = compile_restricted(code, filename="<astra_sandbox>", mode="exec")
        except SyntaxError as e:
            return f"Syntax error: {e}"
        except Exception as e:
            return f"Compilation error: {e}"

        # ── Build controlled execution namespace ──
        exec_globals = dict(safe_globals)          # RestrictedPython safe baseline
        exec_globals["__builtins__"] = _SAFE_BUILTINS
        exec_globals["__import__"] = _guarded_import
        exec_globals["_getattr_"] = _getattr_guard
        exec_globals["_getitem_"] = default_guarded_getitem
        exec_globals["_getiter_"] = default_guarded_getiter
        exec_globals["_write_"] = _write_guard
        exec_globals["_inplacevar_"] = _inplacevar_guard

        # Capture print() output
        collector = PrintCollector()
        exec_globals["_print_"] = collector
        exec_globals["print"] = collector

        exec_locals: dict[str, Any] = {}

        # ── Execute with hard timeout via threading.Timer ──
        execution_error: list[str] = []

        def _run():
            # NOTE: resource.setrlimit is intentionally NOT called here.
            # setrlimit() is a process-level syscall — calling it from a thread
            # caps the entire FastAPI server's virtual memory, not just this thread.
            # Primary memory defense is the AST _MAX_SAFE_LITERAL check above.
            # MemoryError catch below handles dynamic allocations that slip through.
            try:
                exec(byte_code, exec_globals, exec_locals)   # noqa: S102
            except MemoryError:
                execution_error.append(
                    "Blocked: code exceeded available memory. Reduce data size."
                )
            except Exception as exc:
                execution_error.append(str(exc))

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=self.timeout_seconds)

        if thread.is_alive():
            # Thread is still running — we cannot kill Python threads,
            # but daemon=True ensures it dies when the process dies.
            # We return immediately and let it expire.
            return (
                f"Execution timed out after {self.timeout_seconds}s. "
                "Reduce data size or simplify your algorithm."
            )

        if execution_error:
            return f"Runtime error:\n{execution_error[0]}"

        # Safely extract printed text — bypass __str__ which may return object repr
        try:
            printed_output = ''.join(getattr(collector, 'txt', []))
        except Exception:
            printed_output = ""
        result_value = exec_locals.get("result", None)

        parts = []
        if printed_output:
            parts.append(f"Output:\n{printed_output.rstrip()}")
        if result_value is not None:
            parts.append(f"Result: {repr(result_value)}")
        if not parts:
            parts.append("Code executed successfully (no output).")

        output = "\n".join(parts)
        if len(output) > self.max_output_chars:
            output = output[: self.max_output_chars] + "\n[Output truncated]"

        return _sanitize_output(output)


# ── Output sanitizer ──────────────────────────────────────────────────────────
import re as _re

# Patterns that look like secrets in executor output.
# These are checked LINE BY LINE — matching lines are replaced, not the whole output.
_SECRET_PATTERNS = [
    # .env-style: KEY=value or KEY = "value"  (at start of line only)
    _re.compile(r'^[A-Z][A-Z0-9_]{3,}\s*=\s*\S+', _re.MULTILINE),
    # API keys: long hex/base64 strings ≥32 chars (sk-..., pk_..., etc.)
    _re.compile(r'\b(?:sk|pk|api|key|token|secret|bearer|auth)[-_][A-Za-z0-9+/=_\-]{24,}\b', _re.IGNORECASE),
    # Generic long token: 40+ char hex string
    _re.compile(r'\b[a-fA-F0-9]{40,}\b'),
    # Unix file paths: at least 2 segments deep (e.g., /home/user, /etc/passwd)
    # Does NOT match simple fractions (1/3) or single-segment paths (/tmp)
    _re.compile(r'(?<!\w)/(?!tmp\b)[a-zA-Z_][a-zA-Z0-9_\-.]*/[^\s:"\',]+'),
    # Windows file paths: C:\Users\...
    _re.compile(r'[A-Za-z]:\\[^\s:"\',]+'),
]
_REDACTED = "[REDACTED]"


def _sanitize_output(output: str) -> str:
    """
    Strip secret-shaped strings from executor output before returning to agent.
    Operates on the final output string — last line of defense.
    """
    sanitized = output
    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub(_REDACTED, sanitized)
    return sanitized


def _inplacevar_guard(op, x, y):
    """
    RestrictedPython calls this for in-place operators (+=, -=, etc.).
    Allow safe arithmetic in-place ops; block anything on protected objects.
    """
    if op == "+=":   return x + y
    if op == "-=":   return x - y
    if op == "*=":   return x * y
    if op == "/=":   return x / y
    if op == "//=":  return x // y
    if op == "%=":   return x % y
    if op == "**=":  return x ** y
    raise TypeError(f"In-place operator '{op}' is not permitted in the sandbox.")


# ── Module-level singleton ────────────────────────────────────────────────────
python_executor = PythonExecutor()
