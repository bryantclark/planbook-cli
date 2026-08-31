---
name: versioned-machine-contract
date: 2026-08-30
description: Publish the CLI surface as a versioned manifest with structured errors, so agents discover it instead of parsing help text
tags: [agents, contract, errors]
---

# Version the machine contract

The primary caller of this CLI is an agent, not a person. An agent had to learn
the surface from ~20 `--help` runs and diagnose failures by reading English on
stderr — both of which this project's own instructions forbid.

Three things are now published rather than described:

- **`planbook schema`** generates the manifest from the argparse tree: every
  command, flag, type, default, whether it repeats, whether it writes, whether
  it is destructive. Generated, so it cannot drift from the surface.
- **`--error-json`** (and `PLANBOOK_ERROR_JSON=1`) turns any failure into one
  JSON object with a stable `kind`, the exit `code`, a `retryable` flag and a
  `remedy`. The taxonomy lives on the exception classes in `errors.py`.
- **`CONTRACT_VERSION`** in `contract.py` stamps the manifest, every error and
  every dry-run preview, so a caller can refuse to guess against a contract it
  does not know.

Prose on stderr stays the default, because a person at a terminal is still the
one who has to sign in.

Bump the version when an output shape changes. Adding a command or a flag is a
minor bump; renaming or removing a documented key is a major one.
