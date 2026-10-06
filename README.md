# e-Cidade GitHub organization configuration

This repository contains the shared GitHub organization configuration for the
e-Cidade community.

It is the technical control plane for:

- the public organization profile;
- repository governance and GitHub rulesets;
- synchronized mirrors of e-Cidade distributions maintained by ecosystem
  participants;
- shared automation and contribution policies.

The public community hub is [`e-cidade/e-cidade`](https://github.com/e-cidade/e-cidade).

## Mirrors

Mirrors are declared in `mirrors/mirrors.json`.

A mirror preserves upstream Git history while allowing a small,
organization-owned administrative layer on its public default branch. That
layer may identify the upstream project, explain where code contributions
should be sent, and provide repository-local community metadata.

Functional changes belong in the corresponding upstream repository unless the
community explicitly decides otherwise.

## Governance

Repository rules are declared in `governance.config.json` and reconciled with
`LibreCodeCoop/github-governance`.

Governance changes should be reviewable, testable and applied consistently
across the organization.
