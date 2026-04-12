# JIP Quality Standards and Scoring Engine
## The definitive quality bar for Jhaveri Intelligence Platform

### Purpose

This document defines what "excellent" looks like for every dimension of a JIP platform. It is the scoring engine inside JIP Command Center — the automated system that evaluates every platform, finds every gap, and enables one-click fixes.

This is written for a solo developer who builds through Claude Code. The standards are not aspirational — they are enforced. Every platform must reach green (80+) on every dimension. Claude is held to these standards on every build.

---

## Scoring philosophy

Every score is 0-100. Each dimension has weighted checks. Each check is binary (pass/fail) or graduated (0-100). The dimension score is the weighted sum.

Scores map to colors:
- 90-100: green (excellent)
- 70-89: yellow (acceptable, room for improvement)  
- 50-69: orange (needs attention)
- 0-49: red (critical — fix immediately)

Every check produces:
- A score (number)
- Evidence (what was found)
- Plain English explanation (what it means for a non-engineer)
- A fix description (what Claude should do)
- Severity (critical / high / medium / low)

---

## Dimension 1: Security (weight: 25%)

This protects client data and Jhaveri's reputation. Financial platforms are high-value targets.

### Check 1.1: No hardcoded secrets (20 points)

**How it works:** Regex scan every file in the repo for patterns that look like secrets.

```python
SECRET_PATTERNS = [
    r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\'][a-zA-Z0-9_\-]{16,}',
    r'(?i)(secret|password|passwd|pwd)\s*[=:]\s*["\'][^"\']{8,}',
    r'(?i)(token)\s*[=:]\s*["\'][a-zA-Z0-9_\-\.]{16,}',
    r'(?i)(supabase[_-]?key|service[_-]?role)\s*[=:]\s*["\']eyJ',
    r'(?i)(anthropic|openai|stripe)[_-]?(api)?[_-]?(key|secret)\s*[=:]\s*["\']',
    r'(?i)(aws[_-]?access|aws[_-]?secret)\s*[=:]\s*["\']',
    r'(?i)(database[_-]?url|db[_-]?password|postgres)\s*[=:]\s*["\'][^"\']{8,}',
    r'(?i)(jwt[_-]?secret|session[_-]?secret)\s*[=:]\s*["\'][^"\']{8,}',
    r'sk-[a-zA-Z0-9]{20,}',          # Anthropic/OpenAI key format
    r'eyJ[a-zA-Z0-9_\-]{20,}\.eyJ',  # JWT tokens
]
EXCLUDE_DIRS = ['node_modules', '.git', '__pycache__', '.next', 'dist', 'build']
EXCLUDE_FILES = ['.env.example', '.env.template', 'CLAUDE.md', '*.md']
```

**Scoring:**
- 0 matches: 20/20
- 1-2 matches: 10/20
- 3+ matches: 0/20

**Plain English:** "Are there any passwords, API keys, or secret tokens written directly in the code instead of stored safely in environment variables?"

### Check 1.2: Environment variable hygiene (15 points)

**How it works:**
1. Find all `process.env.X` and `os.environ["X"]` references in code
2. Check that a `.env.example` file exists listing all required vars
3. Check that `.env` is in `.gitignore`
4. Check that no `NEXT_PUBLIC_` var contains a service role key or secret
5. Check that server-only vars (Supabase service role, DB password, Anthropic key) are never referenced in files under `src/app/`, `src/components/`, `pages/`, or any client-side directory

**Scoring:**
- `.env` in `.gitignore`: 3 points
- `.env.example` exists with all vars listed: 3 points
- No secrets in `NEXT_PUBLIC_` vars: 4 points
- Service role key only in server files: 5 points

**Plain English:** "Are sensitive credentials properly hidden and never accidentally sent to users' browsers?"

### Check 1.3: Dependency vulnerabilities (15 points)

**How it works:**
```bash
# JavaScript
npm audit --json 2>/dev/null | python3 -c "
import json,sys; d=json.load(sys.stdin)
crit=d.get('metadata',{}).get('vulnerabilities',{}).get('critical',0)
high=d.get('metadata',{}).get('vulnerabilities',{}).get('high',0)
print(json.dumps({'critical':crit,'high':high}))"

# Python
pip audit --format=json 2>/dev/null
```

**Scoring:**
- 0 critical, 0 high: 15/15
- 0 critical, 1-3 high: 10/15
- 1+ critical: 0/15

**Plain English:** "Do any of the software libraries we use have known security holes that attackers could exploit?"

### Check 1.4: CORS configuration (10 points)

**How it works:** Parse FastAPI main.py for CORSMiddleware configuration.

```python
# PASS: specific origins
allow_origins=["https://horizon.jslwealth.in", "https://ops.jslwealth.in"]

# FAIL: wildcard
allow_origins=["*"]

# FAIL: no CORS config at all (defaults to blocking, but means it wasn't thought about)
```

**Scoring:**
- Specific origins listed: 10/10
- Wildcard in production: 0/10
- No CORS config: 5/10 (secure default but unintentional)

**Plain English:** "Does the server only accept requests from our own websites, or could any website in the world talk to our backend?"

### Check 1.5: Authentication coverage (15 points)

**How it works:** 
1. Parse all FastAPI route decorators (`@app.get`, `@router.post`, etc.)
2. Check if each route has a dependency on auth (e.g., `Depends(get_current_user)`, `Depends(verify_api_key)`)
3. Whitelist public routes: `/health`, `/api/health`, `/docs`, `/openapi.json`

**Scoring:**
- 100% of non-public routes have auth: 15/15
- 90-99%: 10/15
- 70-89%: 5/15
- Below 70%: 0/15

**Plain English:** "Can anyone access our data without logging in, or is every sensitive page properly locked?"

### Check 1.6: Supabase service role key (10 points)

**How it works:** Specific check for JIP platforms.
1. Grep for `supabase` and `service_role` in all files
2. If found in any file under frontend directories (`src/app/`, `src/components/`, `pages/`, `public/`): FAIL
3. If found only in backend Python files: PASS

**Scoring:** Binary — 10 or 0.

**Plain English:** "The master database key that can read and write everything — is it safely locked away on the server, or could someone find it in the website code?"

### Check 1.7: HTTPS enforcement (5 points)

**How it works:** Check Nginx config or Dockerfile for HTTP→HTTPS redirect.

**Plain English:** "Is all traffic encrypted, or could someone eavesdrop on data between clients and our servers?"

### Check 1.8: Rate limiting (5 points)

**How it works:** Check for rate limiting middleware (e.g., `slowapi`, custom middleware) on public-facing endpoints.

**Plain English:** "If someone tries to overwhelm our servers with millions of requests, do we have protection?"

### Check 1.9: Input validation (5 points)

**How it works:** Check that FastAPI endpoints use Pydantic models for request bodies (not raw `dict` or `Request.json()`). Check that query parameters have type annotations.

**Scoring:**
- All endpoints use Pydantic models: 5/5
- Most do: 3/5
- Raw dict/json access: 0/5

**Plain English:** "When someone sends data to our system, do we check that it's the right format before processing it, or do we blindly trust whatever comes in?"

---

## Dimension 2: Code quality (weight: 25%)

This determines whether the code is maintainable, readable, and won't break unexpectedly.

### Check 2.1: Zero lint errors (10 points)

**How it works:**
```bash
# TypeScript/JavaScript
npx eslint src/ --format json --quiet

# Python
ruff check . --output-format json
```

**Scoring:**
- 0 errors: 10/10
- 1-5 errors: 7/10
- 6-20 errors: 3/10
- 20+ errors: 0/10

**Plain English:** "Does the code follow basic formatting and style rules, or is it messy and inconsistent?"

### Check 2.2: Zero type errors (10 points)

**How it works:**
```bash
# TypeScript
npx tsc --noEmit --pretty false 2>&1 | grep "error TS" | wc -l

# Python
mypy . --no-error-summary 2>&1 | grep "error:" | wc -l
```

**Scoring:** Same as lint — 0 errors = 10, 1-5 = 7, 6-20 = 3, 20+ = 0.

**Plain English:** "Is the code type-safe? When we say a function returns a number, does it actually always return a number, or could it sometimes return nothing and crash?"

### Check 2.3: Test coverage (15 points)

**How it works:**
```bash
# Python
pytest --cov=. --cov-report=json -q
# Read coverage percentage from coverage.json

# JavaScript  
npx jest --coverage --coverageReporters=json-summary -q
# Read from coverage/coverage-summary.json
```

**Scoring:**
- 80%+ coverage: 15/15
- 60-79%: 10/15
- 40-59%: 5/15
- Below 40%: 0/15

**Plain English:** "If something breaks, will our automated tests catch it? A coverage of 80% means 80% of the code is tested — the remaining 20% could break silently."

### Check 2.4: File modularity — no large files (10 points)

**How it works:**
```bash
find . -name "*.py" -o -name "*.ts" -o -name "*.tsx" | \
  xargs wc -l | sort -rn | head -20
```

Thresholds:
- No file over 300 lines: ideal
- No file over 500 lines: acceptable
- Files over 500 lines: needs splitting

**Scoring:**
- All files under 300 lines: 10/10
- All files under 500 lines: 7/10
- 1-2 files over 500: 3/10
- 3+ files over 500: 0/10

**Plain English:** "Are features broken into small, manageable pieces, or are there massive files where everything is jammed together? Smaller files are easier to understand, test, and fix."

### Check 2.5: Function size and complexity (10 points)

**How it works:** Parse AST to find functions.

Thresholds:
- No function over 50 lines: ideal
- No function over 80 lines: acceptable
- Functions over 80 lines: needs refactoring
- Cyclomatic complexity over 10: needs simplifying (count of if/elif/for/while/try/except per function)

**Scoring:**
- All functions under 50 lines, complexity under 10: 10/10
- All under 80 lines, complexity under 15: 7/10
- Any function over 80 lines or complexity over 15: 3/10
- Multiple violations: 0/10

**Plain English:** "Is each function doing one clear thing, or are there monster functions trying to do everything at once? Long, complicated functions are where bugs hide."

### Check 2.6: Proper variable and function naming (5 points)

**How it works:** AST-based analysis:
1. No single-letter variables (except `i`, `j`, `k` in loops, `e` in exceptions, `_` for unused)
2. Functions use verb_noun pattern (`calculate_returns`, `fetch_nav_data`, not `data`, `process`, `handle`)
3. Constants are UPPER_SNAKE_CASE
4. Classes are PascalCase
5. No generic names: `data`, `result`, `temp`, `tmp`, `foo`, `bar`, `test`, `x`, `val`, `item` as standalone variable names (these are fine as parts of descriptive names like `nav_data`, `score_result`)

**Scoring:**
- 0-2 violations: 5/5
- 3-10 violations: 3/5
- 10+ violations: 0/5

**Plain English:** "Can someone read the code and understand what each piece does from its name alone? Good names are like good labels — they tell you what's inside without opening the box."

### Check 2.7: No dead code (5 points)

**How it works:**
1. Find unused imports (`ruff check --select F401`)
2. Find unused variables (`ruff check --select F841`)
3. Find commented-out code blocks (regex: 3+ consecutive lines starting with `#` or `//` that look like code)
4. Find unreachable code after `return` statements

**Scoring:**
- 0-3 instances: 5/5
- 4-10: 3/5
- 10+: 0/5

**Plain English:** "Is there leftover code that's not being used anymore? Dead code is confusing — someone looking at it doesn't know if it's important or forgotten garbage."

### Check 2.8: Error handling (15 points)

**How it works:**
1. Every FastAPI endpoint must have a try/except or use a global error handler
2. Except blocks must never be bare (`except:` or `except Exception:` without logging)
3. All except blocks must log the error
4. API responses on error must return structured JSON: `{"error": "message", "detail": "...", "status_code": 500}`
5. No `print()` statements for error logging — use proper `logging` module
6. Frontend: all API calls wrapped in try/catch with user-friendly error display

**Scoring:**
- All routes have proper error handling, structured responses, logging: 15/15
- Most routes covered: 10/15
- Bare excepts or print-based error handling: 5/15
- No error handling: 0/15

**Plain English:** "When something goes wrong, does the system handle it gracefully and tell us what happened? Or does it crash with a cryptic error that nobody understands?"

### Check 2.9: Consistent formatting (5 points)

**How it works:**
```bash
# JavaScript/TypeScript
npx prettier --check "src/**/*.{ts,tsx,js,jsx}" 2>&1 | tail -1

# Python
black --check . 2>&1 | tail -1
```

**Scoring:** Binary — 5 or 0.

**Plain English:** "Is the code formatted consistently, or does every file look different? Consistent formatting makes code easier to read and review."

### Check 2.10: API response consistency (10 points)

**How it works:** Analyze all FastAPI endpoint return types:
1. All success responses should follow: `{"data": ..., "status": "success"}`
2. All error responses should follow: `{"error": "message", "detail": "...", "status_code": N}`
3. All list endpoints should support pagination: `{"data": [...], "total": N, "page": N, "page_size": N}`
4. All monetary values returned as strings or Decimal (never float)
5. All dates in ISO 8601 format
6. HTTP status codes used correctly (200 for success, 201 for created, 400 for bad request, 401 for unauthorized, 404 for not found, 500 for server error)

**Scoring:**
- Fully consistent: 10/10
- Mostly consistent (1-2 deviations): 7/10
- Inconsistent: 3/10

**Plain English:** "When our platforms talk to each other, do they speak the same language? Consistent API responses mean fewer bugs and easier integration."

### Check 2.11: No TODO/FIXME/HACK markers (5 points)

**How it works:**
```bash
grep -rn "TODO\|FIXME\|HACK\|XXX\|WORKAROUND" --include="*.py" --include="*.ts" --include="*.tsx" .
```

**Scoring:**
- 0 markers: 5/5
- 1-5 markers: 3/5 (but each should be tracked as an issue)
- 5+ markers: 0/5

**Plain English:** "Are there notes in the code saying 'fix this later' that never got fixed? These are technical IOUs that accumulate interest."

---

## Dimension 3: Architecture quality (weight: 20%)

This uses Claude API for assessment because architecture is judgment, not just pattern matching.

### How it works

For each platform, send to Claude API:

```python
ARCHITECTURE_PROMPT = """
You are a senior software architect reviewing a production financial platform.

Here is the codebase structure:
{directory_tree}

Here is the main backend router:
{main_router_file}

Here is the main frontend page:
{main_page_file}

Here is the Dockerfile:
{dockerfile}

Here is the project's CLAUDE.md (coding standards):
{claude_md}

Score this codebase on each dimension below. For each dimension, provide:
- score: integer 0-100
- evidence: specific files, lines, or patterns you observed
- plain_english: one sentence a non-engineer would understand
- fix: what should be changed (be specific — file names and what to do)

Return ONLY valid JSON. No markdown, no explanation outside the JSON.

{{
  "dimensions": [
    {{
      "name": "separation_of_concerns",
      "score": N,
      "evidence": "...",
      "plain_english": "...",
      "fix": "..."
    }},
    ...
  ],
  "overall": N
}}

Dimensions to score:

1. SEPARATION OF CONCERNS (weight 15%)
Are API routes, business logic, and data access in separate files/layers?
- GOOD: routes/ folder for HTTP handling, services/ for business logic, models/ for data
- BAD: route handler that directly queries the database and formats the response

2. SINGLE RESPONSIBILITY (weight 15%)
Does each file/module do ONE thing?
- GOOD: auth.py handles only authentication, portfolio.py handles only portfolio logic
- BAD: utils.py with 50 unrelated functions

3. DRY — NO DUPLICATION (weight 15%)
Are patterns reused, not copy-pasted?
- GOOD: shared utility for Indian number formatting used across all platforms
- BAD: same date formatting logic written in 4 different files

4. CONSISTENT PATTERNS (weight 15%)
Same patterns used across all endpoints?
- GOOD: every endpoint follows the same error handling, auth, response format pattern
- BAD: some endpoints return {"data": ...}, others return raw arrays, others return {"result": ...}

5. DEPENDENCY INJECTION (weight 10%)
Are dependencies (database, external APIs, config) injected, not hardcoded?
- GOOD: FastAPI Depends() for database sessions, config loaded from environment
- BAD: database connection created inside each route handler

6. ERROR RESILIENCE (weight 10%)
Can the system handle failures gracefully?
- GOOD: retry logic on external API calls, circuit breakers, timeout configs, fallback responses
- BAD: one failed API call crashes the entire request

7. DATABASE PATTERNS (weight 10%)
Is database access clean and safe?
- GOOD: parameterized queries, connection pooling, migrations for schema changes
- BAD: raw SQL string concatenation, no migrations, connections opened and never closed

8. SCALABILITY READINESS (weight 5%)
Could this handle 10x traffic without a rewrite?
- GOOD: async endpoints, connection pooling, caching layer, stateless design
- BAD: synchronous blocking calls, in-memory state, no caching

9. DEPENDENCY HYGIENE (weight 5%)
Are dependencies minimal and well-managed?
- GOOD: requirements.txt/package.json with pinned versions, no unused packages
- BAD: 200 dependencies for a simple app, unpinned versions, abandoned packages
"""
```

### Scoring
The overall architecture score is the weighted sum of Claude's 9 dimension scores.

---

## Dimension 4: API endpoint health (weight: 10%)

This checks that every API endpoint actually works.

### Check 4.1: Endpoint inventory (5 points)

**How it works:** Parse FastAPI's OpenAPI spec (`/openapi.json`) to get all routes. Store the inventory. Compare against previous scan to detect new/removed endpoints.

**Scoring:**
- OpenAPI spec accessible and parseable: 5/5
- Spec returns error: 0/5

### Check 4.2: Endpoint response time (15 points)

**How it works:** Hit every endpoint with a test request and measure response time.

```python
import httpx, time

async def check_endpoint(url, method="GET", timeout=10):
    start = time.monotonic()
    try:
        async with httpx.AsyncClient() as client:
            r = await client.request(method, url, timeout=timeout)
            elapsed_ms = (time.monotonic() - start) * 1000
            return {"url": url, "status": r.status_code, "ms": round(elapsed_ms), "ok": r.status_code < 400}
    except Exception as e:
        return {"url": url, "status": 0, "ms": timeout * 1000, "ok": False, "error": str(e)}
```

Thresholds:
- Under 200ms: excellent
- 200-500ms: acceptable
- 500-2000ms: slow
- Over 2000ms or timeout: critical

**Scoring:**
- All endpoints under 500ms: 15/15
- 90%+ under 500ms: 10/15
- 70-89%: 5/15
- Below 70%: 0/15

**Plain English:** "How fast does each part of the system respond? Under half a second is good. Over 2 seconds means something is wrong."

### Check 4.3: Error rate (10 points)

**How it works:** From the last 24 hours of health_checks data, calculate error rate per endpoint.

**Scoring:**
- Under 0.1% error rate: 10/10
- 0.1-1%: 7/10
- 1-5%: 3/10
- Over 5%: 0/10

### Check 4.4: Response format compliance (10 points)

**How it works:** Hit each endpoint and validate the response against expected schema:
- Success responses have `data` key
- Error responses have `error` key
- List responses have pagination fields
- All monetary values are strings or have exactly 2 decimal places
- All dates are ISO 8601
- Indian number formatting where applicable (INR values use lakh/crore separators in display fields)

### Check 4.5: Database query performance (10 points)

**How it works:** Run `EXPLAIN ANALYZE` on the most common queries (identified from the codebase). Flag:
- Sequential scans on tables over 10,000 rows (needs an index)
- Queries taking over 100ms
- N+1 query patterns (detected by counting queries per request)

**Plain English:** "When the system looks up data, is it doing it efficiently, or is it reading through millions of records to find one answer?"

---

## Dimension 5: Frontend health (weight: 10%)

### Check 5.1: Build succeeds (10 points)

```bash
cd frontend && npm run build 2>&1
```

Binary: builds cleanly or doesn't.

### Check 5.2: Bundle size (10 points)

**How it works:** After build, check `.next/` output size.

- Total JS under 500KB: 10/10
- 500KB-1MB: 7/10
- 1-2MB: 3/10
- Over 2MB: 0/10

**Plain English:** "How much data does a user's browser need to download to use the platform? Smaller is faster."

### Check 5.3: Accessibility basics (10 points)

**How it works:** Run axe-core or pa11y on the main pages.
- All images have alt text
- All form inputs have labels
- Color contrast meets WCAG AA
- Interactive elements are keyboard-accessible
- Page has proper heading hierarchy (h1 → h2 → h3, no skips)

### Check 5.4: Mobile responsiveness (10 points)

**How it works:** Render at 375px width (mobile) and 768px (tablet). Check:
- No horizontal scroll
- Text is readable without zooming (min 14px)
- Touch targets are at least 44x44px
- Tables either scroll horizontally or stack on mobile

**Plain English:** "Wealth managers use tablets. Does the platform look and work properly on smaller screens?"

### Check 5.5: Console errors (10 points)

**How it works:** Load each page in headless browser, capture console errors.

- 0 errors: 10/10
- 1-3 warnings only: 7/10
- Any errors: 0/10

### Check 5.6: Component modularity (10 points)

**How it works:** Scan `src/components/`:
- Each component in its own file
- No component file over 200 lines
- Props are typed (TypeScript interfaces)
- No inline styles over 5 properties (should use Tailwind classes)

### Check 5.7: Loading states and error boundaries (10 points)

**How it works:**
- Every page that fetches data has a loading skeleton/spinner
- Every page has an error boundary or error state
- Empty states are handled (not blank screens)

**Plain English:** "When data is loading or something fails, does the user see a helpful message, or does the screen go blank?"

### Check 5.8: Indian locale compliance (10 points)

JIP-specific:
- All INR values formatted as ₹1,23,456.78 (lakh/crore grouping)
- Dates in DD MMM YYYY format (23 Mar 2026)
- Percentage values show 2 decimal places with % suffix
- All number displays use `Intl.NumberFormat('en-IN')`
- Market hours shown in IST

### Check 5.9: Design system compliance (20 points)

**How it works:** Check against the JIP UI design system skill (766 lines):
- Primary teal (#0d9488) used for headers and active states
- White card backgrounds (#ffffff) with slate-50 page background
- Proper text colors (slate-800 headings, slate-700 body)
- Green for profit, red for loss
- No dark mode violations (this is a light theme platform)
- Consistent spacing (Tailwind scale)
- Font consistency

**Plain English:** "Does every screen look like it belongs to the same professional financial platform, or do different pages look like they were designed by different people?"

---

## Dimension 6: Infrastructure and DevOps (weight: 5%)

### Check 6.1: Docker health (15 points)
- Container running and healthy
- Resource usage within limits (CPU < 80%, memory < 80%)
- Container restart count (should be 0 in last 24h)

### Check 6.2: SSL certificate (10 points)
- Valid SSL cert on subdomain
- Cert expiry more than 30 days away
- HSTS header present

### Check 6.3: GitHub Actions CI/CD (15 points)
- Last workflow run passed
- Deploy workflow exists and is active
- Build time under 5 minutes

### Check 6.4: Database migrations (10 points)
- Migration files exist and are sequential
- No pending migrations
- Migration script is idempotent (can run twice safely)

### Check 6.5: Logging and monitoring (15 points)
- Structured logging (JSON format, not print statements)
- Log rotation configured
- Health check endpoint exists and returns proper status

### Check 6.6: Backup and recovery (15 points)
- RDS automated backups enabled
- Point-in-time recovery configured
- Backup retention period at least 7 days

### Check 6.7: Environment parity (10 points)
- Same Dockerfile for development and production
- No environment-specific code branches (no `if env == 'production'` scattered around)
- Configuration through environment variables only

### Check 6.8: Resource configuration (10 points)
- Database connection pooling configured
- Timeout values set on all external API calls
- Memory limits set in Docker
- Graceful shutdown handling (SIGTERM)

---

## Dimension 7: Documentation (weight: 5%)

### Check 7.1: README (20 points)
- Exists and is not a template
- Contains: what the platform does (1-2 sentences), how to run locally, how to deploy, API overview
- Updated within the last 30 days (git blame check)

### Check 7.2: CLAUDE.md (20 points)
- Exists in project root
- Contains: stack info, mandatory rules, architecture decisions, code examples
- Not just a copy of the global CLAUDE.md (has platform-specific context)

### Check 7.3: API documentation (20 points)
- FastAPI auto-generates OpenAPI docs at /docs
- All endpoints have docstrings
- Request/response models have field descriptions
- Example values provided in Pydantic models

### Check 7.4: Inline comments (20 points)
- Complex business logic has explaining comments
- "Why" comments, not "what" comments (explaining the reason, not restating the code)
- No commented-out code blocks (that's dead code, not documentation)

### Check 7.5: Architecture decision records (20 points)
- Key decisions documented somewhere (CLAUDE.md, ADR files, or GSD STATE.md)
- Trade-offs explained ("we chose X over Y because...")
- At least 3 decisions documented per platform

**Plain English:** "If someone new looked at this project tomorrow, could they understand what it does, how it works, and why key decisions were made — without asking anyone?"

---

## "Fix with Claude" — prompt templates

### For security issues:

```python
SECURITY_FIX_PROMPT = """
You are fixing a security issue in a production financial platform (Jhaveri Intelligence Platform).

ISSUE:
- Severity: {severity}
- Category: {category}  
- Description: {description}
- File: {file_path}
- Line: {line_number}

CURRENT FILE CONTENT:
```
{file_content}
```

PROJECT RULES (from CLAUDE.md):
{claude_md_content}

FIX THIS SPECIFIC ISSUE ONLY. Do not change anything else. Do not refactor. Do not "improve" other parts of the file.

Return the complete corrected file content. Nothing else — no explanation, no markdown, just the file.
"""
```

### For code quality issues:

```python
QUALITY_FIX_PROMPT = """
You are fixing a code quality issue in a production financial platform.

ISSUE:
- Type: {issue_type}  (e.g., "function too long", "missing error handling", "dead code")
- Description: {description}
- File: {file_path}

CURRENT FILE CONTENT:
```
{file_content}
```

PROJECT RULES (from CLAUDE.md):
{claude_md_content}

Rules for the fix:
1. Fix ONLY the described issue
2. Keep all existing functionality identical
3. If splitting a large function, keep the original function as a thin wrapper calling the new smaller functions
4. If adding error handling, use structured JSON error responses
5. All financial values must use Decimal, never float
6. Indian number formatting: lakh/crore separators for INR values

Return the complete corrected file. No explanation, no markdown.
"""
```

### For architecture issues:

```python
ARCHITECTURE_FIX_PROMPT = """
You are refactoring a production financial platform to improve its architecture.

ISSUE:
- Dimension: {dimension} (e.g., "separation of concerns", "DRY violation")
- Description: {description}
- Evidence: {evidence}
- Affected files: {file_list}

CURRENT FILES:
{files_content}

PROJECT RULES (from CLAUDE.md):
{claude_md_content}

Rules for the refactor:
1. Do NOT change any API contracts (same endpoints, same request/response formats)
2. Do NOT change any business logic (same calculations, same results)
3. Create new files if needed for proper separation
4. Update imports in all affected files
5. Follow the MF Pulse pattern (single Dockerfile, FastAPI + Next.js)

Return a JSON object mapping file paths to their new content:
{{"file_path_1": "content_1", "file_path_2": "content_2", ...}}
"""
```

---

## Scoring schedule

| Check type | Frequency | Duration | Method |
|------------|-----------|----------|--------|
| Platform health ping | Every 5 minutes | ~2 seconds | curl + response time |
| API endpoint health | Every 15 minutes | ~30 seconds | Hit all endpoints |
| Security scan | Daily 2 AM IST | ~2 minutes | Regex + npm/pip audit |
| Code quality scan | Daily 2 AM IST | ~3 minutes | Lint + type check + coverage |
| Frontend health | Daily 2 AM IST | ~5 minutes | Build + Lighthouse + axe |
| Architecture review | Weekly Sunday 2 AM | ~60 seconds | Claude API call |
| Documentation check | Weekly Sunday 2 AM | ~30 seconds | File existence + git blame |
| Infrastructure check | Every 30 minutes | ~10 seconds | Docker + SSL + DB |

Estimated monthly Anthropic API cost for architecture reviews: ~$2-4 (4 platforms × 4 weeks × ~2000 tokens per review).

---

## Score aggregation

The overall platform health score is a weighted sum:

```
Overall = (Security × 0.25) + (Code Quality × 0.25) + (Architecture × 0.20) + 
          (API Health × 0.10) + (Frontend Health × 0.10) + 
          (Infrastructure × 0.05) + (Documentation × 0.05)
```

Each platform gets its own overall score. The Command Center home page shows all four.

The goal: **every platform at 80+ overall within 8 weeks of launching the Command Center.**
