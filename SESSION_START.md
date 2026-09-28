# Fresh-session initialization and command routing

Read project files instead of relying on earlier chat history. First inspect profile and configuration status, tracker, saved records, pending transactions, and applications. Run `python3 scripts/validate.py` when possible.

If onboarding is incomplete, accept `/onboard`; explain that discovery and application workflows depend on completing it. Do not force a user who has already completed onboarding to repeat questions answered in authoritative files.

| Command | Workflow |
|---|---|
| `/onboard` | `templates/onboard/WORKFLOW.md` |
| `/find` | `templates/find/WORKFLOW.md`; run the standard sourcing plan and execute discovery |
| `/find broad` | Same workflow; execute the complete broad plan |
| `/prepare [job]` | `templates/prepare/WORKFLOW.md` and package template |
| `/apply [job]` | `templates/apply/WORKFLOW.md`; never submit |
| `/status` | Read-only state summary; never browse or mutate |

Resolve a job by exact ID, company plus role, or a unique company match. Ask only when identity is ambiguous.

For `/status`, show counts and actionable jobs, applications with recorded dates, package readiness, unresolved decisions, saved discovery coverage, and separate fit and application-priority views. Never imply a saved posting was just reverified.
