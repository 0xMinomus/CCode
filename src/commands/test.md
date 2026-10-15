---
description: Run the relevant checks for a requested behavior or change.
argument-hint: [feature, files, or test scope]
---
Run relevant tests or checks and report their actual results. Do not edit files.

Scope: $ARGUMENTS

Read workspace instructions. Identify the smallest tests that cover the requested behavior, then include broader checks when the project requires them. Use isolated data for stateful checks. Do not send provider prompts, access live services, or run destructive commands unless the user explicitly requests that exact action. Report commands run, pass/fail results, and coverage limits. Never claim a check that did not run.