# forge-runner log queries (jq recipes)

Per-chunk log files live at `.forge/logs/<chunk_id>.log` in JSONL format.
Each line is a JSON object with at minimum: `t`, `chunk_id`, `kind`, `payload`.

Companion failure records live at `.forge/logs/<chunk_id>.failure.json` (JSON, not JSONL).

> **Schema note**: `contracts/log-event.schema.json` specifies `evt` and `session_id`
> as the field names; the current runner implementation writes `kind` and `chunk_id`.
> All recipes below use the actual written field names.

---

## 1. List all file edits made during a session

Shows the path of every file the runner asked the agent to edit.

```bash
jq -r 'select(.kind=="tool_use" and .payload.tool=="Edit") | .payload.input.file_path' \
    .forge/logs/V1-1.log
```

---

## 2. Tool calls in chronological order

Shows each tool invocation with its timestamp and name for a quick audit trail.

```bash
jq -r 'select(.kind=="tool_use") | [.t, .payload.tool] | @tsv' \
    .forge/logs/V1-1.log
```

---

## 3. Extract failure reason from a failure record

Companion `.failure.json` files are written when verification fails.

```bash
jq '{chunk_id, failed_check, failed_check_detail, suggested_recovery}' \
    .forge/logs/V1-1.failure.json
```

---

## 4. Compute session duration (first and last event timestamps)

```bash
jq -r '.t' .forge/logs/V1-1.log \
    | sort \
    | awk 'NR==1{first=$0} END{print "start:", first, "\nend:  ", $0}'
```

Or with Python if `awk` date arithmetic is inconvenient:

```bash
python3 -c "
import json, sys
from datetime import datetime
ts = [json.loads(l)['t'] for l in open('.forge/logs/V1-1.log') if l.strip()]
fmt = '%Y-%m-%dT%H:%M:%S.%f%z'
start, end = datetime.fromisoformat(ts[0]), datetime.fromisoformat(ts[-1])
print(f'Duration: {(end-start).total_seconds():.1f}s')
"
```

---

## 5. Event count by kind

Summarises how many events of each type were emitted — useful for quick health checks.

```bash
jq -r '.kind' .forge/logs/V1-1.log | sort | uniq -c | sort -rn
```

---

## 6. Show all text blocks emitted by the agent

Useful for reviewing what the agent narrated during a session.

```bash
jq -r 'select(.kind=="text") | .payload.content' .forge/logs/V1-1.log
```

---

## Searching across all chunk logs

```bash
# Find every chunk that had a timeout error
grep -l '"timeout"' .forge/logs/*.failure.json 2>/dev/null

# Find file edits across all chunks
cat .forge/logs/*.log | jq -r 'select(.kind=="tool_use" and .payload.tool=="Edit") | [.chunk_id, .payload.input.file_path] | @tsv'
```
