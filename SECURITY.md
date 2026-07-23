# Security Policy

## Reporting a vulnerability

Do not open a public issue for secrets, authentication bypasses, arbitrary file access, injection, or remote-code-execution findings.

Use GitHub's private vulnerability reporting for this repository when available. Include reproduction steps, affected versions, impact, and a suggested mitigation.

## Secrets and local data

- Store runtime values in `.env`; only `.env.example` belongs in Git.
- Replace the development `AI_CONFIG_SECRET` before sharing a deployment.
- Treat provider API keys, uploaded sources, generated presentations, and PostgreSQL volumes as private data.
- Do not publish Docker volumes or presentation output directories.

## Supported versions

Security fixes are applied to the latest revision of the `main` branch.
