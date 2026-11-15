# Security policy

labrador is a local tool that indexes private files. Please report vulnerabilities privately rather than in a
public issue.

## Reporting

Use GitHub's private vulnerability reporting on this repository (Security tab, "Report a vulnerability"). Include
what you did, what you expected and what happened, and the labrador version or commit. Please don't include real
personal documents; a fictional file is enough.

This is a small project maintained in spare time. Expect an acknowledgement within a week or so, not an SLA.

## Scope

In scope: the web UI (`labrador serve`), the loopback restrictions on the LLM client, file-mode handling of the
index, and anything that makes labrador write to, or read outside, what it is documented to touch.

Out of scope: anything that needs access to your user account (the index is readable by you), the `--allow-lan`
and remote-LLM overrides doing what they say, and vulnerabilities in dependencies or in Ollama itself, which
should go to those projects.

## Supported versions

Only the latest commit on `main`.

See [Security and privacy](docs/security-privacy.md) for the security model and known limits.
