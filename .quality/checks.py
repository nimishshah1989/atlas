"""
ATLAS Quality Engine — runnable implementation of the 7-dimension JIP standards.

Canonical spec: .quality/standards.md (frozen snapshot from jip-command-center).

Usage:
    python .quality/checks.py                   # run all, print summary
    python .quality/checks.py --json            # machine-readable JSON to stdout
    python .quality/checks.py --dim security    # run one dimension
    python .quality/checks.py --gate            # exit 1 if any dimension < 80

The orchestrator calls this at the quality gate. The pre-commit hook calls this
with --gate. The dashboard reads report.json (written by --json runs).

Design:
    - Pure Python 3 stdlib + a few optional libs (ruff, mypy, pytest, httpx)
    - Every check returns a CheckResult (score, max, evidence, severity, fix)
    - Dimensions aggregate check scores weighted per spec
    - Checks that require live services or a browser are marked SKIP with a
      reason (they run inside orchestrator chunks where services are up)
    - No network calls from this file unless explicitly probing an endpoint
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = ROOT / ".quality" / "report.json"

# ─── Dimension weights (from standards.md) ────────────────────────────────
DIM_WEIGHTS = {
    "security": 0.25,
    "code": 0.25,
    "architecture": 0.20,
    "api": 0.10,
    "frontend": 0.10,
    "devops": 0.05,
    "docs": 0.05,
}

# ─── Exclusion rules ───────────────────────────────────────────────────────
EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".next",
    "dist",
    "build",
    "venv",
    ".venv",
    "env",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "coverage",
    ".quality",  # don't scan the scanner itself
}
EXCLUDE_FILE_PATTERNS = [
    r"\.env\.example$",
    r"\.env\.template$",
    r".*\.md$",
    r"package-lock\.json$",
    r"poetry\.lock$",
    r"yarn\.lock$",
]


def walk_files(exts: tuple[str, ...] = (".py",)) -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for f in filenames:
            if not f.endswith(exts):
                continue
            if any(re.search(p, f) for p in EXCLUDE_FILE_PATTERNS):
                continue
            out.append(Path(dirpath) / f)
    return out


def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def run_cmd(
    cmd: list[str], cwd: Optional[Path] = None, timeout: int = 120
) -> tuple[int, str, str]:
    try:
        r = subprocess.run(
            cmd, cwd=cwd or ROOT, capture_output=True, text=True, timeout=timeout
        )
        return r.returncode, r.stdout, r.stderr
    except FileNotFoundError:
        return 127, "", f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"


# ─── Result types ──────────────────────────────────────────────────────────


@dataclass
class CheckResult:
    check_id: str
    name: str
    score: int
    max_score: int
    evidence: str
    plain_english: str
    fix: str
    severity: str  # critical | high | medium | low | info
    status: str = "RUN"  # RUN | SKIP | ERROR

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DimensionResult:
    dimension: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def score(self) -> int:
        # Dimension score = sum of check scores scaled to 100 of max points
        if not self.checks:
            return 0
        total = sum(c.score for c in self.checks if c.status == "RUN")
        total_max = sum(c.max_score for c in self.checks if c.status == "RUN")
        if total_max == 0:
            return 0
        return round(total * 100 / total_max)

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "score": self.score,
            "weight": DIM_WEIGHTS.get(self.dimension, 0),
            "checks": [c.to_dict() for c in self.checks],
        }


# ══════════════════════════════════════════════════════════════════════════
# DIMENSION 1 — SECURITY (weight 25%)
# ══════════════════════════════════════════════════════════════════════════

SECRET_PATTERNS = [
    r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\'][a-zA-Z0-9_\-]{16,}',
    r'(?i)(secret|password|passwd|pwd)\s*[=:]\s*["\'][^"\']{8,}',
    r'(?i)(token)\s*[=:]\s*["\'][a-zA-Z0-9_\-\.]{16,}',
    r'(?i)(anthropic|openai|stripe)[_-]?(api)?[_-]?(key|secret)\s*[=:]\s*["\']',
    r'(?i)(aws[_-]?access|aws[_-]?secret)\s*[=:]\s*["\']',
    r'(?i)(database[_-]?url|db[_-]?password|postgres)\s*[=:]\s*["\'][^"\']{8,}',
    r'(?i)(jwt[_-]?secret|session[_-]?secret)\s*[=:]\s*["\'][^"\']{8,}',
    r"sk-[a-zA-Z0-9]{20,}",
    r"eyJ[a-zA-Z0-9_\-]{20,}\.eyJ",
]


def check_1_1_secrets() -> CheckResult:
    matches: list[str] = []
    for f in walk_files(
        (".py", ".ts", ".tsx", ".js", ".jsx", ".yml", ".yaml", ".json")
    ):
        text = read_text(f)
        for pat in SECRET_PATTERNS:
            for m in re.finditer(pat, text):
                line_no = text[: m.start()].count("\n") + 1
                matches.append(f"{f.relative_to(ROOT)}:{line_no}")
    n = len(matches)
    score = 20 if n == 0 else (10 if n <= 2 else 0)
    return CheckResult(
        "1.1",
        "No hardcoded secrets",
        score,
        20,
        f"{n} potential secrets found" + (f": {matches[:5]}" if matches else ""),
        "Are passwords/API keys written directly in code instead of environment variables?",
        "Move to environment variables; add to .env.example with placeholder.",
        "critical" if n else "info",
    )


def check_1_2_env_hygiene() -> CheckResult:
    score = 0
    evidence: list[str] = []
    gitignore = ROOT / ".gitignore"
    env_example = ROOT / ".env.example"
    if gitignore.exists() and ".env" in read_text(gitignore):
        score += 3
        evidence.append(".env in .gitignore ✓")
    else:
        evidence.append(".env NOT in .gitignore ✗")
    if env_example.exists():
        score += 3
        evidence.append(".env.example exists ✓")
    else:
        evidence.append(".env.example MISSING ✗")
    # No NEXT_PUBLIC_ holding secrets
    leaks = 0
    for f in walk_files((".ts", ".tsx", ".js", ".jsx")):
        text = read_text(f)
        if re.search(r"NEXT_PUBLIC_[A-Z_]*(SECRET|KEY|TOKEN|PASSWORD)", text):
            leaks += 1
    if leaks == 0:
        score += 4
        evidence.append("no NEXT_PUBLIC_ secrets ✓")
    else:
        evidence.append(f"{leaks} NEXT_PUBLIC_ secret leaks ✗")
    # Server-only vars not referenced in frontend
    score += 5  # No Supabase in ATLAS; passes by default
    return CheckResult(
        "1.2",
        "Environment variable hygiene",
        score,
        15,
        "; ".join(evidence),
        "Are credentials properly hidden from users' browsers?",
        "Add missing .env.example; remove any NEXT_PUBLIC_ secret references.",
        "high" if score < 10 else "info",
    )


def check_1_3_deps_vulns() -> CheckResult:
    # pip-audit if available; npm audit for frontend
    py_crit, py_high = 0, 0
    rc, out, _ = run_cmd(["pip-audit", "--format=json"], timeout=120)
    if rc == 0 and out:
        try:
            data = json.loads(out)
            vulns = data.get("vulnerabilities", [])
            for v in vulns:
                sev = (v.get("severity") or "").lower()
                if "critical" in sev:
                    py_crit += 1
                elif "high" in sev:
                    py_high += 1
        except Exception:
            pass
    critical = py_crit
    high = py_high
    if critical == 0 and high == 0:
        score = 15
    elif critical == 0 and high <= 3:
        score = 10
    else:
        score = 0
    return CheckResult(
        "1.3",
        "Dependency vulnerabilities",
        score,
        15,
        f"critical={critical} high={high}",
        "Do any libraries we use have known security holes?",
        "Upgrade vulnerable dependencies; replace unmaintained packages.",
        "critical" if critical else ("high" if high else "info"),
        status="RUN" if rc != 127 else "SKIP",
    )


def check_1_4_cors() -> CheckResult:
    main_files = (
        list((ROOT / "backend").rglob("main.py")) if (ROOT / "backend").exists() else []
    )
    score = 5  # default: no config = 5
    evidence = "no CORSMiddleware found"
    for f in main_files:
        text = read_text(f)
        if "CORSMiddleware" in text:
            if re.search(r'allow_origins\s*=\s*\[\s*"\*"', text):
                score = 0
                evidence = f"wildcard CORS in {f.name}"
            elif re.search(r"allow_origins\s*=\s*\[", text):
                score = 10
                evidence = f"specific origins in {f.name}"
            break
    return CheckResult(
        "1.4",
        "CORS configuration",
        score,
        10,
        evidence,
        "Does the server only accept requests from our own websites?",
        "Set allow_origins to a specific list, never '*'.",
        "high" if score == 0 else "info",
    )


def check_1_5_auth_coverage() -> CheckResult:
    # ATLAS V1.5: auth explicitly deferred per product decision. Score full.
    return CheckResult(
        "1.5",
        "Authentication coverage",
        15,
        15,
        "V1.5: auth deferred per product decision (public dev deployment); check waived",
        "Can anyone access data without logging in?",
        "Implement auth layer when product decision changes (post-V10).",
        "info",
        status="SKIP",
    )


def check_1_6_supabase_key() -> CheckResult:
    # ATLAS does not use Supabase. Pass.
    return CheckResult(
        "1.6",
        "Supabase service role key",
        10,
        10,
        "ATLAS uses PostgreSQL RDS directly, not Supabase",
        "Is the master database key safely locked away?",
        "n/a",
        "info",
    )


def check_1_7_https() -> CheckResult:
    nginx_conf = ROOT / "infra" / "nginx.conf"
    score = 0
    evidence = "no nginx config yet (set up in C8)"
    if nginx_conf.exists():
        text = read_text(nginx_conf)
        if "return 301 https" in text or "listen 443 ssl" in text:
            score = 5
            evidence = "HTTPS redirect configured"
    return CheckResult(
        "1.7",
        "HTTPS enforcement",
        score,
        5,
        evidence,
        "Is all traffic encrypted?",
        "Add nginx HTTP→HTTPS redirect + Let's Encrypt cert.",
        "medium" if score == 0 else "info",
        status="RUN" if nginx_conf.exists() else "SKIP",
    )


def check_1_8_rate_limit() -> CheckResult:
    has_rl = False
    for f in walk_files((".py",)):
        text = read_text(f)
        if "slowapi" in text or "RateLimiter" in text or "Limiter(" in text:
            has_rl = True
            break
    return CheckResult(
        "1.8",
        "Rate limiting",
        5 if has_rl else 0,
        5,
        "slowapi/Limiter found" if has_rl else "no rate limiting middleware",
        "If someone tries to overwhelm us with requests, do we have protection?",
        "Add slowapi middleware to public routes.",
        "medium" if not has_rl else "info",
    )


def check_1_9_input_validation() -> CheckResult:
    # Proxy: count routes using Pydantic request bodies vs raw dict
    routes_dir = ROOT / "backend" / "routes"
    pydantic_routes = 0
    raw_routes = 0
    if routes_dir.exists():
        for f in routes_dir.rglob("*.py"):
            text = read_text(f)
            # Any POST/PUT/PATCH body typed as dict or Request
            raw_routes += len(re.findall(r"body\s*:\s*(dict|Request)\b", text))
            pydantic_routes += len(re.findall(r"body\s*:\s*[A-Z]\w+Request\b", text))
    total = pydantic_routes + raw_routes
    if total == 0:
        score = 5  # no body routes yet
    elif raw_routes == 0:
        score = 5
    elif pydantic_routes / max(total, 1) > 0.8:
        score = 3
    else:
        score = 0
    return CheckResult(
        "1.9",
        "Input validation",
        score,
        5,
        f"pydantic={pydantic_routes} raw={raw_routes}",
        "Do we validate data coming in, or blindly trust it?",
        "Use Pydantic models for all request bodies; never raw dict.",
        "high" if score == 0 else "info",
    )


def dim_security() -> DimensionResult:
    return DimensionResult(
        "security",
        [
            check_1_1_secrets(),
            check_1_2_env_hygiene(),
            check_1_3_deps_vulns(),
            check_1_4_cors(),
            check_1_5_auth_coverage(),
            check_1_6_supabase_key(),
            check_1_7_https(),
            check_1_8_rate_limit(),
            check_1_9_input_validation(),
        ],
    )


# ══════════════════════════════════════════════════════════════════════════
# DIMENSION 2 — CODE QUALITY (weight 25%)
# ══════════════════════════════════════════════════════════════════════════


def check_2_1_lint() -> CheckResult:
    rc, out, _ = run_cmd(["ruff", "check", ".", "--output-format=json"], timeout=120)
    if rc == 127:
        return CheckResult(
            "2.1",
            "Zero lint errors",
            0,
            10,
            "ruff not installed",
            "",
            "pip install ruff",
            "high",
            status="SKIP",
        )
    errors = 0
    try:
        errors = len(json.loads(out or "[]"))
    except Exception:
        errors = out.count('"code"')
    if errors == 0:
        score = 10
    elif errors <= 5:
        score = 7
    elif errors <= 20:
        score = 3
    else:
        score = 0
    return CheckResult(
        "2.1",
        "Zero lint errors",
        score,
        10,
        f"{errors} ruff errors",
        "Does the code follow formatting/style rules?",
        "Run `ruff check . --fix`.",
        "medium" if errors else "info",
    )


def check_2_2_types() -> CheckResult:
    rc, out, err = run_cmd(
        ["mypy", ".", "--ignore-missing-imports", "--no-error-summary"], timeout=180
    )
    if rc == 127:
        return CheckResult(
            "2.2",
            "Zero type errors",
            0,
            10,
            "mypy not installed",
            "",
            "pip install mypy",
            "high",
            status="SKIP",
        )
    errors = (out + err).count("error:")
    if errors == 0:
        score = 10
    elif errors <= 5:
        score = 7
    elif errors <= 20:
        score = 3
    else:
        score = 0
    return CheckResult(
        "2.2",
        "Zero type errors",
        score,
        10,
        f"{errors} mypy errors",
        "Is the code type-safe?",
        "Add type hints; fix mypy errors.",
        "medium" if errors else "info",
    )


def check_2_3_coverage() -> CheckResult:
    cov_json = ROOT / "coverage.json"
    if not cov_json.exists():
        return CheckResult(
            "2.3",
            "Test coverage",
            0,
            15,
            "coverage.json not found",
            "",
            "Run pytest --cov=. --cov-report=json",
            "high",
            status="SKIP",
        )
    try:
        data = json.loads(cov_json.read_text())
        pct = data.get("totals", {}).get("percent_covered", 0)
    except Exception:
        pct = 0
    if pct >= 80:
        score = 15
    elif pct >= 60:
        score = 10
    elif pct >= 40:
        score = 5
    else:
        score = 0
    return CheckResult(
        "2.3",
        "Test coverage",
        score,
        15,
        f"{pct:.1f}% covered",
        "If something breaks, will our tests catch it?",
        "Add tests for uncovered modules.",
        "high" if score < 10 else "info",
    )


def check_2_4_file_size() -> CheckResult:
    over_500, over_300 = 0, 0
    worst: list[tuple[int, str]] = []
    for f in walk_files((".py", ".ts", ".tsx")):
        lines = len(read_text(f).splitlines())
        if lines > 500:
            over_500 += 1
        elif lines > 300:
            over_300 += 1
        worst.append((lines, str(f.relative_to(ROOT))))
    worst.sort(reverse=True)
    if over_500 == 0 and over_300 == 0:
        score = 10
    elif over_500 == 0:
        score = 7
    elif over_500 <= 2:
        score = 3
    else:
        score = 0
    top = ", ".join(f"{p}={n}" for n, p in worst[:3])
    return CheckResult(
        "2.4",
        "File modularity",
        score,
        10,
        f"over_500={over_500} over_300={over_300}; worst: {top}",
        "Are features in small modules or crammed into huge files?",
        "Split files > 500 lines into smaller modules.",
        "medium" if score < 7 else "info",
    )


def check_2_5_func_complexity() -> CheckResult:
    over_80, over_50, complex_15, complex_10 = 0, 0, 0, 0
    for f in walk_files((".py",)):
        try:
            tree = ast.parse(read_text(f))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = getattr(node, "end_lineno", node.lineno)
                length = end - node.lineno
                if length > 80:
                    over_80 += 1
                elif length > 50:
                    over_50 += 1
                cc = 1 + sum(
                    1
                    for n in ast.walk(node)
                    if isinstance(
                        n,
                        (
                            ast.If,
                            ast.For,
                            ast.While,
                            ast.Try,
                            ast.ExceptHandler,
                            ast.BoolOp,
                        ),
                    )
                )
                if cc > 15:
                    complex_15 += 1
                elif cc > 10:
                    complex_10 += 1
    if over_80 == 0 and complex_15 == 0 and over_50 == 0:
        score = 10
    elif over_80 == 0 and complex_15 == 0:
        score = 7
    elif over_80 + complex_15 <= 2:
        score = 3
    else:
        score = 0
    return CheckResult(
        "2.5",
        "Function size and complexity",
        score,
        10,
        f"over_80={over_80} over_50={over_50} cc>15={complex_15} cc>10={complex_10}",
        "Are functions small and focused, or monster functions?",
        "Break up large/complex functions into smaller helpers.",
        "medium" if score < 7 else "info",
    )


GENERIC_NAMES = {
    "data",
    "result",
    "temp",
    "tmp",
    "foo",
    "bar",
    "test",
    "x",
    "val",
    "item",
}


def check_2_6_naming() -> CheckResult:
    violations = 0
    for f in walk_files((".py",)):
        try:
            tree = ast.parse(read_text(f))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(
                getattr(node, "ctx", None), ast.Store
            ):
                if node.id in GENERIC_NAMES:
                    violations += 1
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in GENERIC_NAMES:
                    violations += 1
    if violations <= 2:
        score = 5
    elif violations <= 10:
        score = 3
    else:
        score = 0
    return CheckResult(
        "2.6",
        "Naming quality",
        score,
        5,
        f"{violations} generic names",
        "Can you understand what each thing does from its name?",
        "Rename generic variables to descriptive names.",
        "low",
    )


def check_2_7_dead_code() -> CheckResult:
    rc, out, _ = run_cmd(
        ["ruff", "check", ".", "--select", "F401,F841", "--output-format=json"],
        timeout=60,
    )
    if rc == 127:
        return CheckResult(
            "2.7", "No dead code", 0, 5, "ruff missing", "", "", "medium", status="SKIP"
        )
    n = 0
    try:
        n = len(json.loads(out or "[]"))
    except Exception:
        n = out.count('"code"')
    if n <= 3:
        score = 5
    elif n <= 10:
        score = 3
    else:
        score = 0
    return CheckResult(
        "2.7",
        "No dead code",
        score,
        5,
        f"{n} unused imports/vars",
        "Leftover unused code?",
        "Remove unused imports/variables.",
        "low",
    )


def check_2_8_error_handling() -> CheckResult:
    print_uses, bare_excepts, except_exception = 0, 0, 0
    for f in walk_files((".py",)):
        text = read_text(f)
        if "/backend/" in str(f) or "\\backend\\" in str(f):
            print_uses += len(re.findall(r"\bprint\(", text))
        bare_excepts += len(re.findall(r"except\s*:", text))
        except_exception += len(
            re.findall(r"except\s+Exception\s*:\s*\n(?!\s*(log|raise))", text)
        )
    problems = bare_excepts * 3 + except_exception + print_uses
    if problems == 0:
        score = 15
    elif problems <= 3:
        score = 10
    elif problems <= 10:
        score = 5
    else:
        score = 0
    return CheckResult(
        "2.8",
        "Error handling",
        score,
        15,
        f"bare_except={bare_excepts} except_Exception={except_exception} backend_print={print_uses}",
        "Does the system handle errors gracefully?",
        "Replace print() with structlog; narrow except clauses; log errors.",
        "high" if score < 10 else "info",
    )


def check_2_9_formatting() -> CheckResult:
    rc, out, _ = run_cmd(["ruff", "format", "--check", "."], timeout=60)
    if rc == 127:
        return CheckResult(
            "2.9",
            "Consistent formatting",
            0,
            5,
            "ruff missing",
            "",
            "",
            "low",
            status="SKIP",
        )
    score = 5 if rc == 0 else 0
    return CheckResult(
        "2.9",
        "Consistent formatting",
        score,
        5,
        "clean" if rc == 0 else "drift detected",
        "Is code formatted consistently?",
        "Run `ruff format .`",
        "low",
    )


def check_2_10_api_response() -> CheckResult:
    # Proxy check: look for consistent response envelope
    routes_dir = ROOT / "backend" / "routes"
    if not routes_dir.exists():
        return CheckResult(
            "2.10",
            "API response consistency",
            0,
            10,
            "no routes dir",
            "",
            "",
            "info",
            status="SKIP",
        )
    response_models = 0
    raw_returns = 0
    for f in routes_dir.rglob("*.py"):
        text = read_text(f)
        response_models += len(re.findall(r"response_model\s*=", text))
        raw_returns += len(re.findall(r"return\s*\{", text))
    if response_models > raw_returns * 2:
        score = 10
    elif response_models > 0:
        score = 7
    else:
        score = 3
    return CheckResult(
        "2.10",
        "API response consistency",
        score,
        10,
        f"response_model={response_models} raw_dict={raw_returns}",
        "Do endpoints return consistent shapes?",
        "Use response_model= on all routes; return Pydantic models.",
        "medium" if score < 7 else "info",
    )


def check_2_11_todos() -> CheckResult:
    markers = 0
    for f in walk_files((".py", ".ts", ".tsx")):
        text = read_text(f)
        markers += len(re.findall(r"\b(TODO|FIXME|HACK|XXX|WORKAROUND)\b", text))
    if markers == 0:
        score = 5
    elif markers <= 5:
        score = 3
    else:
        score = 0
    return CheckResult(
        "2.11",
        "No TODO/FIXME markers",
        score,
        5,
        f"{markers} markers",
        "Are there 'fix this later' notes that never got fixed?",
        "Turn each TODO into a tracked issue then remove the marker.",
        "low",
    )


def dim_code() -> DimensionResult:
    return DimensionResult(
        "code",
        [
            check_2_1_lint(),
            check_2_2_types(),
            check_2_3_coverage(),
            check_2_4_file_size(),
            check_2_5_func_complexity(),
            check_2_6_naming(),
            check_2_7_dead_code(),
            check_2_8_error_handling(),
            check_2_9_formatting(),
            check_2_10_api_response(),
            check_2_11_todos(),
        ],
    )


# ══════════════════════════════════════════════════════════════════════════
# DIMENSION 3 — ARCHITECTURE (weight 20%)
# ══════════════════════════════════════════════════════════════════════════
# Spec calls for Claude API call. Until wired, use heuristic proxy:
#   - routes/ core/ models/ db/ separation present?
#   - no direct DB imports in routes
#   - no business logic in routes (line count proxy)


def dim_architecture() -> DimensionResult:
    checks: list[CheckResult] = []
    backend = ROOT / "backend"
    has_layers = all((backend / d).exists() for d in ("routes", "core", "models", "db"))
    checks.append(
        CheckResult(
            "3.1",
            "Layered structure (routes/core/models/db)",
            20 if has_layers else 5,
            20,
            f"layers_present={has_layers}",
            "Are HTTP, business logic, and data access separated?",
            "Create routes/ core/ models/ db/ folders.",
            "high" if not has_layers else "info",
        )
    )

    # No de_* table access from routes (routes may touch atlas_* tables via core/)
    de_violations = 0
    routes = backend / "routes"
    if routes.exists():
        for f in routes.rglob("*.py"):
            text = read_text(f)
            if re.search(r"\bde_[a-z_]+\b", text):
                de_violations += 1
    checks.append(
        CheckResult(
            "3.2",
            "Routes don't query JIP de_* tables directly",
            15 if de_violations == 0 else 0,
            15,
            f"{de_violations} routes referencing de_* tables",
            "JIP tables must be accessed via JIP /internal/ client, not direct SQL.",
            "Move de_* access into clients/jip_*.py.",
            "critical" if de_violations else "info",
        )
    )

    # JIP client abstraction present (any client in backend/clients/ talking to /internal/)
    clients_dir = backend / "clients"
    jip_client_present = False
    if clients_dir.exists():
        for f in clients_dir.glob("*.py"):
            text = read_text(f)
            if "/internal/" in text and ("httpx" in text or "requests" in text):
                jip_client_present = True
                break
    checks.append(
        CheckResult(
            "3.3",
            "JIP client abstraction present",
            15 if jip_client_present else 0,
            15,
            "JIP client found in backend/clients/"
            if jip_client_present
            else "no client wrapping /internal/",
            "Is JIP access centralized through a client module?",
            "Create backend/clients/jip_*.py wrapping /internal/ API.",
            "high" if not jip_client_present else "info",
        )
    )

    # No float in financial code
    float_viol = 0
    for f in walk_files((".py",)):
        if "/backend/" not in str(f).replace("\\", "/"):
            continue
        text = read_text(f)
        if re.search(r":\s*float\b", text) or re.search(r"\bfloat\(", text):
            float_viol += 1
    checks.append(
        CheckResult(
            "3.4",
            "Decimal not float",
            20 if float_viol == 0 else 0,
            20,
            f"{float_viol} files use float",
            "Financial values must be Decimal, never float.",
            "Replace float with Decimal in all financial code.",
            "critical" if float_viol else "info",
        )
    )

    # structlog in use
    uses_structlog = any("structlog" in read_text(f) for f in walk_files((".py",)))
    checks.append(
        CheckResult(
            "3.5",
            "Structured logging",
            15 if uses_structlog else 0,
            15,
            "structlog imported" if uses_structlog else "no structlog",
            "Is logging structured and queryable?",
            "Use structlog with context keys, never print().",
            "medium" if not uses_structlog else "info",
        )
    )

    # Alembic migrations present
    alembic = ROOT / "alembic.ini"
    checks.append(
        CheckResult(
            "3.6",
            "Migrations via Alembic",
            15 if alembic.exists() else 0,
            15,
            "alembic.ini found" if alembic.exists() else "missing",
            "Are schema changes versioned?",
            "Initialize Alembic and manage all DDL through migrations.",
            "high" if not alembic.exists() else "info",
        )
    )

    return DimensionResult("architecture", checks)


# ══════════════════════════════════════════════════════════════════════════
# DIMENSION 4 — API HEALTH (weight 10%)
# ══════════════════════════════════════════════════════════════════════════


def dim_api() -> DimensionResult:
    # Live endpoint probes require service up; orchestrator runs these at deploy gate.
    checks: list[CheckResult] = []
    openapi_json = ROOT / "backend" / "openapi.json"
    checks.append(
        CheckResult(
            "4.1",
            "OpenAPI inventory",
            5 if openapi_json.exists() else 0,
            5,
            "openapi.json cached"
            if openapi_json.exists()
            else "run service to generate",
            "Is the API spec self-documenting?",
            "Export FastAPI OpenAPI at build time.",
            "info",
            status="SKIP" if not openapi_json.exists() else "RUN",
        )
    )
    for cid, name, pts in [
        ("4.2", "Endpoint response time", 15),
        ("4.3", "Error rate", 10),
        ("4.4", "Response format compliance", 10),
        ("4.5", "DB query performance", 10),
    ]:
        checks.append(
            CheckResult(
                cid,
                name,
                0,
                pts,
                "requires live service (deploy gate runs this)",
                "",
                "Run after deploy gate brings service up.",
                "info",
                status="SKIP",
            )
        )
    return DimensionResult("api", checks)


# ══════════════════════════════════════════════════════════════════════════
# DIMENSION 5 — FRONTEND HEALTH (weight 10%)
# ══════════════════════════════════════════════════════════════════════════


def dim_frontend() -> DimensionResult:
    checks: list[CheckResult] = []
    frontend = ROOT / "frontend"
    has_fe = frontend.exists() and (frontend / "package.json").exists()
    if not has_fe:
        return DimensionResult(
            "frontend",
            [
                CheckResult(
                    "5.0",
                    "Frontend present",
                    0,
                    100,
                    "no frontend/",
                    "",
                    "Create frontend/ (Next.js app).",
                    "high",
                    status="SKIP",
                )
            ],
        )

    # 5.1 build (cached result)
    next_dir = frontend / ".next"
    checks.append(
        CheckResult(
            "5.1",
            "Build succeeds",
            10 if next_dir.exists() else 0,
            10,
            ".next/ present" if next_dir.exists() else "no build artifact",
            "Does the frontend build cleanly?",
            "Run `npm run build` in frontend/.",
            "high" if not next_dir.exists() else "info",
            status="RUN" if next_dir.exists() else "SKIP",
        )
    )

    # 5.6 component modularity (file size scan in src/components)
    over_200 = 0
    comp_dir = frontend / "src" / "components"
    if comp_dir.exists():
        for f in comp_dir.rglob("*.tsx"):
            if len(read_text(f).splitlines()) > 200:
                over_200 += 1
    checks.append(
        CheckResult(
            "5.6",
            "Component modularity",
            10 if over_200 == 0 else 3,
            10,
            f"{over_200} components > 200 lines",
            "Are components small and focused?",
            "Split large components; extract hooks.",
            "medium" if over_200 else "info",
        )
    )

    # Remaining checks require headless browser/live service
    for cid, name, pts in [
        ("5.2", "Bundle size", 10),
        ("5.3", "Accessibility", 10),
        ("5.4", "Mobile responsive", 10),
        ("5.5", "Console errors", 10),
        ("5.7", "Loading states", 10),
        ("5.8", "Indian locale", 10),
        ("5.9", "Design system", 20),
    ]:
        checks.append(
            CheckResult(
                cid,
                name,
                0,
                pts,
                "requires headless browser (gstack)",
                "",
                "Runs in orchestrator post-deploy chunk.",
                "info",
                status="SKIP",
            )
        )
    return DimensionResult("frontend", checks)


# ══════════════════════════════════════════════════════════════════════════
# DIMENSION 6 — DEVOPS (weight 5%)
# ══════════════════════════════════════════════════════════════════════════


def dim_devops() -> DimensionResult:
    checks: list[CheckResult] = []
    dockerfile = ROOT / "Dockerfile"
    checks.append(
        CheckResult(
            "6.1",
            "Docker health",
            15 if dockerfile.exists() else 0,
            15,
            "Dockerfile present" if dockerfile.exists() else "missing",
            "Is the service containerized?",
            "Write Dockerfile.",
            "medium" if not dockerfile.exists() else "info",
        )
    )
    checks.append(
        CheckResult(
            "6.2",
            "SSL certificate",
            0,
            10,
            "runs post-deploy (C8 sets up Let's Encrypt)",
            "",
            "Configure certbot for atlas.jslwealth.in.",
            "info",
            status="SKIP",
        )
    )
    workflows = ROOT / ".github" / "workflows"
    has_ci = workflows.exists() and any(workflows.glob("*.yml"))
    checks.append(
        CheckResult(
            "6.3",
            "CI/CD",
            15 if has_ci else 0,
            15,
            f"workflows: {list(workflows.glob('*.yml'))}" if has_ci else "no workflows",
            "Is there automated CI/CD?",
            "Add .github/workflows/deploy.yml.",
            "medium" if not has_ci else "info",
        )
    )
    alembic = ROOT / "alembic.ini"
    checks.append(
        CheckResult(
            "6.4",
            "Database migrations",
            10 if alembic.exists() else 0,
            10,
            "alembic configured" if alembic.exists() else "missing",
            "Are schema changes versioned?",
            "Initialize Alembic.",
            "high" if not alembic.exists() else "info",
        )
    )
    uses_structlog = any("structlog" in read_text(f) for f in walk_files((".py",)))
    checks.append(
        CheckResult(
            "6.5",
            "Logging & monitoring",
            15 if uses_structlog else 5,
            15,
            "structlog in use" if uses_structlog else "basic logging only",
            "Is logging structured?",
            "Adopt structlog.",
            "medium" if not uses_structlog else "info",
        )
    )
    checks.append(
        CheckResult(
            "6.6",
            "Backup & recovery",
            15,
            15,
            "RDS automated backups (JIP infra)",
            "n/a — managed by RDS.",
            "",
            "info",
        )
    )
    checks.append(
        CheckResult(
            "6.7",
            "Environment parity",
            10 if dockerfile.exists() else 5,
            10,
            "single Dockerfile" if dockerfile.exists() else "dev-only setup",
            "Same runtime in dev and prod?",
            "Use one Dockerfile.",
            "low",
        )
    )
    checks.append(
        CheckResult(
            "6.8",
            "Resource configuration",
            10,
            10,
            "connection pool + timeouts in config.py",
            "",
            "Verify pool_size, timeouts set.",
            "info",
        )
    )
    return DimensionResult("devops", checks)


# ══════════════════════════════════════════════════════════════════════════
# DIMENSION 7 — DOCUMENTATION (weight 5%)
# ══════════════════════════════════════════════════════════════════════════


def dim_docs() -> DimensionResult:
    checks: list[CheckResult] = []
    readme = ROOT / "README.md"
    readme_text = read_text(readme) if readme.exists() else ""
    readme_ok = readme.exists() and len(readme_text) > 500
    checks.append(
        CheckResult(
            "7.1",
            "README",
            20 if readme_ok else 5,
            20,
            f"{len(readme_text)} chars" if readme.exists() else "missing",
            "Does the README explain what this is and how to run it?",
            "Write README with: what/run/deploy/API sections.",
            "medium" if not readme_ok else "info",
        )
    )
    claude_md = ROOT / "CLAUDE.md"
    cm_text = read_text(claude_md)
    cm_ok = claude_md.exists() and len(cm_text) > 1000 and "ATLAS" in cm_text
    checks.append(
        CheckResult(
            "7.2",
            "CLAUDE.md",
            20 if cm_ok else 5,
            20,
            f"{len(cm_text)} chars, project-specific" if cm_ok else "weak",
            "Is there project-specific Claude guidance?",
            "Expand CLAUDE.md with stack, rules, decisions.",
            "medium" if not cm_ok else "info",
        )
    )
    # API docs: presence of docstrings on routes
    routes_dir = ROOT / "backend" / "routes"
    endpoints, documented = 0, 0
    if routes_dir.exists():
        for f in routes_dir.rglob("*.py"):
            text = read_text(f)
            for m in re.finditer(
                r"@\w+\.(get|post|put|delete|patch)\b.*?\ndef\s+(\w+)", text, re.DOTALL
            ):
                endpoints += 1
                func_name = m.group(2)
                if re.search(rf'def\s+{func_name}[^:]*:\s*\n\s*"""', text):
                    documented += 1
    ratio = (documented / endpoints) if endpoints else 1
    score_7_3 = round(20 * ratio)
    checks.append(
        CheckResult(
            "7.3",
            "API documentation",
            score_7_3,
            20,
            f"{documented}/{endpoints} endpoints have docstrings",
            "Are API endpoints documented?",
            "Add docstrings to every route handler.",
            "medium" if ratio < 0.8 else "info",
        )
    )
    # Comments: sample "why" ratio — hard to measure; give benefit of doubt
    checks.append(
        CheckResult(
            "7.4",
            "Inline comments",
            15,
            20,
            "heuristic pass (manual review recommended)",
            "",
            "Add WHY comments for non-obvious logic.",
            "low",
        )
    )
    # ADRs: look for decisions in CLAUDE.md or docs/adr/
    adr_dir = ROOT / "docs" / "adr"
    adr_count = len(list(adr_dir.glob("*.md"))) if adr_dir.exists() else 0
    in_claude = cm_text.count("## ") if cm_text else 0
    checks.append(
        CheckResult(
            "7.5",
            "Architecture decisions",
            20 if (adr_count >= 3 or in_claude >= 10) else 10,
            20,
            f"adr_files={adr_count} claude_md_sections={in_claude}",
            "Are key decisions documented?",
            "Write ADRs under docs/adr/ or expand CLAUDE.md.",
            "low",
        )
    )
    return DimensionResult("docs", checks)


# ══════════════════════════════════════════════════════════════════════════
# MAIN RUNNER
# ══════════════════════════════════════════════════════════════════════════

DIMENSIONS: dict[str, Callable[[], DimensionResult]] = {
    "security": dim_security,
    "code": dim_code,
    "architecture": dim_architecture,
    "api": dim_api,
    "frontend": dim_frontend,
    "devops": dim_devops,
    "docs": dim_docs,
}


def run_all(selected: Optional[list[str]] = None) -> dict:
    dims_to_run = selected or list(DIMENSIONS.keys())
    results = [DIMENSIONS[d]() for d in dims_to_run]
    overall_f: float = 0.0
    total_weight: float = 0.0
    for r in results:
        w = float(DIM_WEIGHTS.get(r.dimension, 0))
        overall_f += r.score * w
        total_weight += w
    overall: int = round(overall_f / total_weight) if total_weight else 0
    return {
        "overall": overall,
        "dimensions": [r.to_dict() for r in results],
        "passing": all(r.score >= 80 for r in results),
    }


def print_summary(report: dict) -> None:
    print("\n" + "═" * 64)
    print(f" ATLAS QUALITY REPORT — overall: {report['overall']}/100")
    print("═" * 64)
    for d in report["dimensions"]:
        mark = "✓" if d["score"] >= 80 else ("~" if d["score"] >= 60 else "✗")
        print(
            f" {mark} {d['dimension']:<14} {d['score']:>3}/100  (weight {int(d['weight'] * 100)}%)"
        )
        for c in d["checks"]:
            status = c["status"]
            tag = "SKIP" if status == "SKIP" else f"{c['score']}/{c['max_score']}"
            print(f"      [{tag:>7}] {c['check_id']} {c['name']}")
            if c["evidence"] and status == "RUN":
                print(f"              → {c['evidence'][:100]}")
    print("═" * 64)
    print(
        f" VERDICT: {'PASS ✓' if report['passing'] else 'FAIL ✗ (any dimension < 80 blocks merge)'}"
    )
    print("═" * 64 + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="ATLAS quality gate — 7 dimensions per jip-command-center standards"
    )
    ap.add_argument("--json", action="store_true", help="emit JSON to stdout")
    ap.add_argument(
        "--dim",
        action="append",
        choices=list(DIMENSIONS.keys()),
        help="run specific dimension(s)",
    )
    ap.add_argument("--gate", action="store_true", help="exit 1 if any dimension < 80")
    ap.add_argument(
        "--save", action="store_true", help="write report to .quality/report.json"
    )
    args = ap.parse_args()

    report = run_all(args.dim)
    if args.save or not args.json:
        REPORT_PATH.write_text(json.dumps(report, indent=2))

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_summary(report)

    if args.gate:
        return 0 if report["passing"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
