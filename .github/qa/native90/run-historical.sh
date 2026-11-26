#!/usr/bin/env bash
set -euo pipefail

# The emulator action executes each script line in a fresh shell. Keep the
# bounded readiness loop and candidate_file assignment in this one process.
test "$#" -eq 2
mkdir -p historical-audit
appium --address 127.0.0.1 --port 4723 --log-no-colors --log-timestamp > historical-audit/appium.log 2>&1 &
for attempt in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:4723/status > /dev/null; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:4723/status > historical-audit/appium-ready.json
candidate_file=$(python3 -c 'import json;print(json.load(open(".github/qa/native90/meta.json"))["fileName"])')
python3 -u .github/qa/historical-hint-audit.py run --apk "candidate/$candidate_file" --plan historical-plan/plan.json --plan-sha256 "$1" --api "$2" --out historical-audit
