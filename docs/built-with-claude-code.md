# Built with Claude Code

chronon is built in pair with Claude Code: Claude Code writes most of the code,
and Orel makes every design decision and reviews every change.

The working rules are in `CLAUDE.md` at the repository root. The short
version:

- **Decisions first.** Architectural choices are made explicitly and
  recorded as ADRs with the options that were rejected and where they break.
- **Gates before "done".** `make check` (format, lint, strict types, unit
  tests, manifest validation, and a grep that keeps the upstream domain out of
  the code) must pass, and contract tests must pass against a running site
  for anything touching the API.
- **Explain-back.** After each component, Orel explains it back, and the
  explanation lives under *Components*.
- **Honest docs.** Pages describe only what exists; shortcuts are named.

Failures and their root causes are recorded in the [build log](build-log.md).
