# Normalized discovery records

Input is a nonempty JSON array. `scripts/example-discovery.json` is a complete
synthetic example. `scripts/discovery.py:normalize` is the executable contract;
validation completes for the whole batch before any batch writes.

| Field | Contract |
| --- | --- |
| schema_version | Integer 1 (legacy), or 2 with verified provenance per SOURCING.md |
| company, role, source, description | Nonempty strings; description retains posting text |
| url | Absolute HTTP(S) posting URL without embedded credentials |
| date_found | Required ISO date, YYYY-MM-DD |
| date_posted | ISO date or null/omitted |
| location, requisition_id | Nonempty string or null/omitted; use employer-issued requisition ID |
| salary_min, salary_max | Nonnegative finite numbers or null/omitted; min cannot exceed max |
| salary_basis | Must be annual_base_usd if either salary bound is known |
| domestic_trips_per_year | Nonnegative finite number or null/omitted |
| mandatory_relocation, major_organic_social_ownership | Boolean or null/omitted; unknown is not false |
| qualification, career_fit | Objects with exactly all dimensions from scoring.yaml; finite numeric values in [0,1] |
| confidence | Finite numeric value in [0,1], independent of fit |
| search_tracks | Nonempty array of keys from search-tracks.yaml |
| strengths, gaps, unknowns, conflicts | Arrays of nonempty explanatory strings; empty arrays allowed |

Include evidence in the explanatory arrays; use gap class labels from scoring.yaml
in gap explanations. Additional fields (for example evidence excerpts or the original
salary wording) are retained. Input id, scores, status, sources, last_seen, and
candidate_group are ignored because storage owns those fields. Record unknown pay
as null and preserve raw pay wording; do not pass hourly, total compensation, or
foreign currency numbers to annual USD base filters. Existing salary-min filter
semantics are preserved, including its treatment of ranges and unknown minimums.

## Identity and updates

Canonical URLs remove fragments, trailing slashes, and known tracking parameters
(utm_*, gclid, fbclid), while retaining job-identifying query parameters. Exact
canonical URL or normalized company plus employer requisition ID matches an
existing record. Scheme, path case, and other query parameters remain significant.
Cross-board matches without a verified requisition ID remain separate for review.
Titles are never used to auto-merge distinct vacancies. A record connecting two
existing IDs fails the batch rather than silently merging human decisions.

IDs are deterministic hashes of the first canonical URL and remain stable on
updates. Reimports replace the latest analysis with the supplied analysis, retain
all source URL aliases and discovered tracks, retain earliest date_found, and
advance last_seen to the latest observation date. Submit current analyses; there
is no automatic freshness inference from posting text and no historical analysis
archive. Requisition IDs must identify a vacancy, not a generic company ID.

## Scores, ranking, and human state

The importer calls score_job.py directly. Qualified candidates meet both configured
minimums. Stretch candidates meet the configured stretch qualification interval and
career-fit minimum. Both groups rank together by career fit, then qualification,
then confidence; below-threshold jobs follow, and hard rejects come last. Stretch
classification remains visible even when qualification also meets the normal minimum.

New qualified/stretch records start REVIEW, other survivors DISCOVERED, and hard
rejects REJECTED. Reimports preserve existing tracker status, notes, resume_version,
and extra columns; updated hard-reject scores/reasons remain visible even when a
human status such as APPLIED is preserved. Tracker rows without stored discovery
records remain untouched. Conflicts expressed only in prose do not independently
trigger the numeric hard filters; the reviewing agent must surface them.

## Storage and recovery

`jobs/discovered/records.json` stores the complete normalized collection, including
rejected and below-threshold records for audit. `tracker.csv` remains the editable
human status source and CSV projection. Existing jobs/rejected and jobs/shortlisted
directories are reserved for later workflows and are not moved or populated here.

CLI imports take an exclusive advisory project-directory lock on macOS/Linux.
Writes use temporary files and atomic replacement. A journal at
`jobs/.discovery-transaction.json` allows the next real import to finish an
interrupted two-file update before processing its own batch. Avoid editing the
tracker during an import or while this journal exists: recovery completes the
previous saved snapshot. Dry-run neither writes nor recovers a pending transaction.
Keep routine backups; this increment is not a database or concurrent editing system.

## Multi-source extension

New discovery uses version 2 and the provenance/lead contracts in `SOURCING.md`.
Version 1 compatibility and scoring semantics remain intact. Stored provenance
preserves first origin, accumulates encounters, and separates authoritative posting
and application URLs. Unknown legacy origins remain null. `application_date` and
`description_hash` are storage-owned (the former preserved, the latter computed).
An additional namespaced employer/ATS board/posting identity is supported. The
transaction journal may also contain promoted staging leads. New source logs and
watch-list checks support measured rotation without creating automatic browsing.
