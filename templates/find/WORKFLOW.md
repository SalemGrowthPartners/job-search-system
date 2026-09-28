# Multi-source `/find`

Require completed onboarding. Run `python3 scripts/find_jobs.py plan` for standard discovery or add `--mode broad`. Execute the returned plan; printing it is not completion.

Use employer/watch sources, ATS exploration, specialist boards, capability searches, and bounded aggregator discovery. Standard mode rotates queries and sources while covering every configured track. Broad mode runs all configured title and capability searches and all enabled companies.

Target recent three- and seven-day windows, with an explicit undated-posting sweep. Preserve an evidenced original publication date separately from first discovery, update, or repost dates. Never invent freshness.

Stage leads before promotion when verification is incomplete. For each promising role, capture original source, timestamp, method, query ID, run ID, employer, title and URL. Verify the full authoritative posting and application route. Preserve geographic restrictions, compensation basis, travel, management scope, responsibilities and hard conflicts.

Deduplicate only with reliable identity evidence: employer requisition, namespaced ATS posting, canonical employer URL, or observed redirect. Title similarity alone is insufficient.

Analyze qualification, career fit and confidence separately. Apply hard filters from configuration. Missing information lowers confidence rather than automatically lowering fit. Record strengths, classified gaps, unknowns and conflicts. Use `promote` or `import` with dry-run before saving.

Finish by logging source coverage, failures, blocks, duplicates and effort. Run `priority` for application order and `report` for measured coverage. Present fit ranking separately from urgency. Do not resurface APPLIED, REJECTED or WITHDRAWN jobs as new candidates.
