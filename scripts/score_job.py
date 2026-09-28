#!/usr/bin/env python3
"""Score a normalized job analysis JSON.

This script intentionally does not try to understand raw job descriptions.
ChatGPT/Codex should first analyze a posting and produce normalized 0-1 values
for each scoring dimension plus hard-filter fields. This script then applies
stable, auditable math from config/scoring.yaml.
"""
from pathlib import Path
import json
import sys
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / "config" / "scoring.yaml").read_text())


def weighted_score(weights, values):
    total = 0.0
    for key, weight in weights.items():
        value = float(values.get(key, 0))
        value = max(0.0, min(1.0, value))
        total += weight * value
    return round(total)


def hard_reject(job):
    reasons = []
    salary = job.get("salary_min")
    floor = CONFIG["hard_filters"]["minimum_known_base_salary"]
    if salary is not None and floor is not None and salary < floor:
        reasons.append(f"known base salary ${salary:,.0f} is below ${floor:,.0f} floor")
    if job.get("mandatory_relocation"):
        reasons.append("mandatory relocation")
    if job.get("major_organic_social_ownership"):
        reasons.append("major organic social-media ownership")
    trips = job.get("domestic_trips_per_year")
    max_trips = CONFIG["hard_filters"]["maximum_domestic_trips_per_year"]
    if trips is not None and max_trips is not None and trips > max_trips:
        reasons.append(f"travel expectation exceeds {max_trips} domestic trips/year")
    return reasons


def score_job(job):
    rejects = hard_reject(job)
    q = weighted_score(CONFIG["qualification_score"], job.get("qualification", {}))
    c = weighted_score(CONFIG["career_fit_score"], job.get("career_fit", {}))
    confidence = round(max(0, min(1, float(job.get("confidence", 0)))) * 100)
    result = {
        "hard_reject": bool(rejects),
        "reject_reasons": rejects,
        "qualification_score": q,
        "career_fit_score": c,
        "confidence": confidence,
    }
    return result


def main(path):
    print(json.dumps(score_job(json.loads(Path(path).read_text())), indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/score_job.py path/to/job-analysis.json")
        sys.exit(2)
    main(sys.argv[1])
