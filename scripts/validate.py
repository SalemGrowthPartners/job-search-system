#!/usr/bin/env python3
from pathlib import Path
import csv
import json
import sys

try:
    import yaml
except ImportError:
    print("Missing dependency: PyYAML. Run: pip install -r requirements.txt")
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
YAML_FILES = [
    ROOT / "profile" / "master-profile.yaml",
    ROOT / "profile" / "accomplishments.yaml",
    ROOT / "profile" / "preferences.yaml",
    ROOT / "config" / "search-tracks.yaml",
    ROOT / "config" / "scoring.yaml",
]

errors = []
try:
    import onboard
    onboard.validate_ledger()
    print("OK  onboarding/claim-review.yaml")
except Exception as e:
    errors.append(f"onboarding claim review: {e}")
try:
    import sourcing
    sourcing.configuration(ROOT)
    print("OK  sourcing configuration")
except Exception as e:
    errors.append(f"sourcing configuration: {e}")
for path in YAML_FILES:
    try:
        with path.open() as f:
            yaml.safe_load(f)
        print(f"OK  {path.relative_to(ROOT)}")
    except Exception as e:
        errors.append(f"{path}: {e}")

tracker = ROOT / "tracker.csv"
try:
    with tracker.open(newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
    required = {"id", "company", "role", "qualification_score", "career_fit_score", "confidence", "status"}
    missing = required - set(header)
    if missing:
        errors.append(f"tracker.csv missing columns: {sorted(missing)}")
    else:
        print("OK  tracker.csv")
except Exception as e:
    errors.append(f"tracker.csv: {e}")

# Validate persisted normalized records when the discovery layer has been used.
records_path = ROOT / "jobs" / "discovered" / "records.json"
if records_path.exists():
    try:
        from discovery import STATUSES, normalize, group
        from score_job import score_job
        tracks = yaml.safe_load((ROOT / "config/search-tracks.yaml").read_text())["search_tracks"]
        records = json.loads(records_path.read_text())
        if not isinstance(records, list):
            raise ValueError("records must be an array")
        ids = set()
        for record in records:
            normalize(record, tracks)
            record_id = record.get("id")
            if not isinstance(record_id, str) or not record_id or record_id in ids:
                raise ValueError("missing or duplicate record ID")
            ids.add(record_id)
            if record.get("status") not in STATUSES:
                raise ValueError(f"invalid status for {record_id}")
            scores = score_job(record)
            if record.get("scores") != scores or record.get("candidate_group") != group(scores):
                raise ValueError(f"outdated or invalid scores for {record_id}; reimport current analysis")
        print("OK  jobs/discovered/records.json")
    except Exception as e:
        errors.append(f"jobs/discovered/records.json: {e}")

if (ROOT / "jobs/.discovery-transaction.json").exists():
    errors.append("interrupted discovery transaction: run a real import to recover")

if errors:
    print("\nVALIDATION FAILED")
    for err in errors:
        print("-", err)
    sys.exit(1)

print("\nProject structure is valid.")
