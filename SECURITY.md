# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for anything security-sensitive
(API keys, authentication, tenant isolation, data exposure).

Email **support@hebbrix.com** instead. We aim to acknowledge reports within
2 business days.

## Scope

This repository is a thin client: it holds no user data and no server-side
secrets. The only sensitive material it touches is:

- your `HEBBRIX_API_KEY` (env var or `~/.hebbrix/config.json`, written `0600`)
- memory content in transit to `api.hebbrix.com` over HTTPS

Vulnerabilities in the Hebbrix service or API itself are also welcome at the
same address.

## Supported versions

Only the latest released version is supported with security fixes.
