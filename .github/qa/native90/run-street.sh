#!/usr/bin/env bash
set -euo pipefail

# emulator-runner starts each script line in a new shell; keep readiness and
# metadata-derived candidate selection together and fail before UI on error.
test "$#" -eq 2
mkdir -p street-audit
appium --address 127.0.0.1 --port 4723 --log-no-colors --log-timestamp > street-audit/appium.log 2>&1 &
for attempt in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:4723/status > /dev/null; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:4723/status > street-audit/appium-ready.json
candidate_file=$(python3 -c 'import json;print(json.load(open(".github/qa/native90/meta.json"))["fileName"])')
python3 -u .github/qa/street-consent-audit.py --apk "candidate/$candidate_file" --api "$1" --case-id "$2" --out street-audit
