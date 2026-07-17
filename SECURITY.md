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

## Stored-memory prompt injection (honest threat model)

A memory store returns what was saved, verbatim. If someone gets poisoned text
into a memory ("ignore previous instructions", "email everything to X"), that
text is later retrieved and reaches the model as part of its context. This is
second-order prompt injection, and it is inherent to memory: the store cannot
tell an instruction-shaped fact from a factual one.

What this client does: every path that puts stored content in front of the model
— the `hebbrix://profile` resource, the `context` prompt, and the results of
`hebbrix_search` / `hebbrix_get` / `hebbrix_list` / `hebbrix_history` /
`hebbrix_ask` — carries an explicit untrusted-data marker telling the model to
treat the payload as passive data and not act on instructions inside it.

**What this is not: a security boundary.** The marker is *advisory*. It informs a
model; it cannot stop one. A client that is weaker, older, or instructed to
"always follow your memory" can still be hijacked, because the raw payload is
delivered intact — nothing at this layer prevents the model from acting on it.
Red-teaming with a frontier, safety-tuned agent showed it resisted retrieval
injection, profile poisoning, false-authority and destructive-command attacks and
warned the user — but that was the *client model's* judgment, not this server's.

If you are building an agent on Hebbrix, put the real boundary in your agent
policy: require human confirmation for consequential/irreversible actions
(sending, deleting, paying), never resolve a recipient or credential from memory
alone, and prefer an out-of-band trusted source for identity.

## Supported versions

Only the latest released version is supported with security fixes.
