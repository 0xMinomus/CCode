---
description: Reproduce a reported bug, find its root cause, and verify the fix.
argument-hint: <observed failure and reproduction steps>
---
Diagnose and fix the reported failure.

Report: $ARGUMENTS

Read workspace instructions. Reproduce the behavior before editing when practical. Trace the shared path and its callers; identify the root cause rather than suppressing the symptom. Preserve security, data integrity, and existing behavior outside the fix. Add a focused regression check when practical, then exercise the changed path and report exact results. State clearly when reproduction was not possible. Do not commit, push, or deploy unless requested.