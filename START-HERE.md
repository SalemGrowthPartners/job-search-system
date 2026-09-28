# Start here: your local job-search workspace

This folder turns a ChatGPT Work session into a persistent job-search assistant. It helps you build a verified career profile, discover and compare openings, prepare tailored application materials, and keep an application tracker. It does not submit applications for you.

## What you need

- A ChatGPT plan that includes **Work** and can open a local project folder, read and write files, browse job sites, and create documents.
- One or more existing resumes or CVs. Several versions are better because they often contain different details.
- Optional writing samples, portfolios, biographies, or accomplishment notes.

You do not need to understand programming, YAML, Python, Git, APIs, or command-line tools. The assistant uses the supporting files behind the scenes.

## Save and open the folder

1. Download and unzip the package.
2. Move the resulting `job-search-system-starter` folder somewhere private and easy to find, such as Documents.
3. In ChatGPT Work, start a fresh local Work session and select that folder as the project or workspace.
4. Send `/onboard` as your first message.

Keep the entire folder together. The tracker, career profile, job records, and application packages are linked by their locations inside it.

## What happens during `/onboard`

The assistant will ask you to provide one or preferably several resumes/CVs. Writing samples are optional. It will review those files and propose:

- career history and education
- accomplishments and metrics
- skills and tools
- industry experience
- management and leadership experience
- relevant work that may not appear in every resume

Old resumes are evidence, not unquestionable truth. A statement found in a resume remains **resume-supported** until you confirm it. Inferences stay proposed. Conflicting dates, titles, numbers, unusually precise claims, and suspicious inconsistencies are shown to you for verification.

The conversation then moves through short preference stages instead of one long questionnaire:

1. Target roles and work you want to do.
2. Adjacent or stretch opportunities.
3. Compensation needs and preferences.
4. Remote, hybrid, onsite, location, and relocation limits.
5. Travel and management preferences.
6. Industry interests, hard exclusions, and other fit factors.
7. Search titles, capability searches, scoring rules, and an initial company watch list.

The assistant validates the finished configuration and tells you when the system is ready.

## Everyday commands

- `/find` — runs a focused, multi-source search using rotating coverage.
- `/find broad` — runs all configured title and capability searches for wider coverage.
- `/prepare [job/company]` — creates a truthful, tailored application package for your review.
- `/apply [job/company]` — helps fill and upload supported information, then stops before submission.
- `/status` — shows saved progress, applications, prepared packages, and suggested next actions without changing anything.

These are messages you send to the Work session. They are not commands you type into Terminal.

## Privacy and responsibility

The profile, source documents, tracker, job records, and prepared applications stay in this local project folder unless you choose to upload, share, or synchronize the folder through another service. Web browsing still sends normal requests to the job sites being viewed.

Review every resume, cover letter, answer, salary response, legal statement, demographic choice, and uploaded file. You remain responsible for the final application. `/apply` must stop before the employer's Submit button, and only your explicit report that you submitted may mark a job as applied.

## If you obtained this from GitHub

Download the packaged ZIP from the repository's **Releases** section instead of onboarding inside a public fork. Keep the completed folder private. It will contain resumes, career facts, job records, tracker history, and application materials.

The included `.gitignore` excludes common source documents, generated application packages, work files, document binaries, caches, and credentials. Blank starter profile and state files are intentionally part of the repository, so a person using Git must still review every change before pushing. Never push an onboarded workspace to a public repository.
