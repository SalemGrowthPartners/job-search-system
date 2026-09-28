---
layout: default
title: Local Job Search System
---

# Build a job search around your real experience

This downloadable workspace helps ChatGPT Work learn your verified career history, search across multiple job sources, evaluate opportunities, prepare tailored materials, and maintain a local application tracker.

[Go to the download page](https://github.com/{{ site.github.repository_nwo }}/releases/latest){: .btn .btn-primary }
[View the project on GitHub](https://github.com/{{ site.github.repository_nwo }}){: .btn }

## Designed for professionals, not programmers

You interact with the system by sending simple messages in a ChatGPT Work session:

- `/onboard`
- `/find`
- `/find broad`
- `/prepare [job/company]`
- `/apply [job/company]`
- `/status`

You do not need to understand Python, Git, APIs, YAML, or command-line tools.

## Start with evidence, then confirm it

During onboarding, the system reviews one or preferably several resumes and optional writing samples. It proposes a career history, accomplishments, skills, tools, industries, and management experience.

Old resumes are treated as evidence rather than unquestionable truth. Conflicting dates, inconsistent metrics, suspiciously precise claims, and unsupported inferences are presented for confirmation. Resume-supported information remains distinct from facts you explicitly confirm.

## Search broadly and compare honestly

The system supports:

- focused and broad job discovery
- title-based and capability-based searches
- employer watch lists and multiple job sources
- authoritative posting verification and deduplication
- separate qualification, career-fit, confidence, and urgency scores
- recency-aware application priorities
- tailored resumes, cover letters, and application answers

## The human remains in control

Preparation stops for your review. Application assistance may fill supported routine information and upload reviewed documents, but it stops before submission. You review legal statements, salary responses, demographic choices, unsupported answers, and every final document.

## Privacy

The project is designed to store resumes, career facts, applications, and tracker history in your local folder. The public repository contains only blank schemas and fictional fixtures.

For the safest setup, download the latest Release ZIP and keep the completed workspace in a private local folder. Do not upload an onboarded workspace, completed tracker, resumes, or application packages to a public repository.

## Getting started

You do not need a GitHub account or any knowledge of GitHub to use this system.

1. Click **Go to the download page** near the top of this page. This opens the latest release on GitHub; it does not begin the download yet.
2. On the page that opens, find the **Assets** section.
3. Click **Job.Search.System.Starter.zip**. This is the only file you need.
4. Ignore **Source code (zip)** and **Source code (tar.gz)**. GitHub adds those automatically, and they are not the prepared starter package.
5. Open your Downloads folder and double-click `Job.Search.System.Starter.zip` to unzip it.
6. Move the unzipped folder somewhere private and easy to find, such as your Documents folder.
7. Open that folder in a fresh ChatGPT Work session.
8. Send `/onboard` and follow the short, staged conversation.

Do not click **Fork**, **Code**, or **Clone**. Those GitHub features are for people who want to modify the software itself.

See [`START-HERE.md`](../START-HERE.md) for the complete guide.

---

Released under the [MIT License](../LICENSE).
