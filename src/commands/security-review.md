---
description: Audit the requested code path for evidence-backed security issues.
argument-hint: [feature, files, or trust boundary]
---
Review the requested scope for security issues without editing files.

Scope: $ARGUMENTS

Read workspace instructions. Trace reachable trust boundaries, authorization, input validation, filesystem/network access, secret handling, and failure paths. Report only evidence-backed findings with severity, attacker capability, impact, reachable path, and a concrete remediation. Separate confirmed vulnerabilities from unverified risks. Do not expose secret values or probe live systems.