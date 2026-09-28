# Posting recency and application priority

Recency is independent of the existing qualification and career-fit scores. No score weights, candidate thresholds, or importer fit ordering change.

## Dates and evidence

Within provenance, original_posted_at is either YYYY-MM-DD (when only a date is known) or an ISO timestamp with timezone. It requires original_posted_evidence with date_type:original_published, url, raw_text and observed_at. Preserve source wording and an auditable reason for treating it as original publication. For ambiguous “posted recently,” updated_at, reposted or last-published values, leave original_posted_at null/absent and retain source dates/date_basis separately. No fabricated timestamp precision. No automatic legacy migration.

origin.at is first_discovered_at, immutable and separate from publication. last_verified_at is an activity check. Existing date_posted remains compatible and is retained when a later import omits it, but without explicit evidence it is not a recency input. Known original dates survive reimports omitting them; a different supplied original date fails with an evidence-conflict error. Reconcile source evidence explicitly before correcting stored data. Reposts cannot reset age.

## Configurable policy

config/recency.yaml defines four urgency bands: age 0–3 highest, 4–7 high, 8–14 normal, 15–30 reduced; over 30 older. Age is calendar days in America/Los_Angeles for timestamps. Unknown age gets normal ordering without a freshness bonus or assumed-age penalty. Future original dates are flagged, not treated as new.

An eligible qualified/stretch job with career fit >=90 gets an exceptional-fit designation. Exceptional jobs older than 7 days rise to high urgency while retaining their true age and verification needs. Ties use unchanged career-fit, qualification and confidence values, then stable ID. This is an explainable ordering, not a new score.

Over-30-day postings need an employer activity check no more than 7 days old. Over-60-day postings also need evergreen_checked_at and evergreen_check_evidence within that window. Records with availability other than open, future verification timestamps, or recorded conflicts go to needs_verification. Unknown original dates do not imply old age. Significant gaps still require agent interpretation; numerical eligibility is not a guarantee of suitability.

## Read-only command

`python3 scripts/find_jobs.py priority [--as-of YYYY-MM-DD]`

Returns application_priority, unchanged fit_order IDs, needs_verification, exceptional_older_matches, unknown_date_matches, and excluded IDs. The views preserve visibility for older/unknown matches without forcing them below an unlimited stream of fresh results. Highlighted blocked jobs are not cleared for application. APPLIED, INTERVIEW, REJECTED, WITHDRAWN and OFFER statuses are excluded, as are hard rejects and below-threshold candidates. The tracker is the human-status source. Pending storage transactions must be recovered before viewing priority. --as-of supports repeatable audits/tests and never changes stored dates.

## Discovery

Standard plans search 3-day and 7-day windows with overlap and extend to the last completed run when needed. Date filters and newest sorting are used only where supported. Use 20% undated search effort in standard mode and 40% in broad mode for exceptional older matches and sources without date filters. These are effort targets, not candidate quotas. Log date_filter and date_filter_supported per coverage entry. Preserve blocked retries regardless of cutoff. Existing identity and description hashes distinguish repeated inventory from changed jobs; an updated hash is not a new publication date.
