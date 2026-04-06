# Security Policy

## Accepted Vulnerabilities

This document tracks known vulnerabilities that have been reviewed and accepted with justification.

### CVE-2024-23342: python-ecdsa Minerva Timing Attack

**Package:** `ecdsa` v0.19.1 (transitive dependency via `python-jose`)
**Severity:** HIGH (CVSS 7.4) - Attack Complexity: HIGH
**Status:** No patch available (as of March 2026)
**Date Accepted:** 2026-03-11

#### Vulnerability Description
The `ecdsa` library is vulnerable to a Minerva timing attack on P-256 ECDSA signature operations. An attacker with high-precision timing measurements and thousands of signature samples could potentially extract private keys.

#### Mitigation
1. **Primary:** We use `python-jose[cryptography]` which prefers the `cryptography` library's timing-resistant implementation over the pure-Python `ecdsa` fallback
2. **Usage Context:** JWT tokens with short expiration times limit signature sample collection
3. **Attack Complexity:** Requires network-level timing precision and extensive measurement campaigns

#### Risk Assessment
- **Likelihood:** Low (requires sophisticated timing attack infrastructure)
- **Impact:** High (private key compromise)
- **Overall Risk:** Medium (acceptable given mitigations)

#### Monitoring Plan
- Review quarterly for patched versions
- Re-assess if usage patterns change (e.g., long-lived tokens)
- Consider migration to pure `cryptography`-based JWT library if patch unavailable by Q3 2026

#### References
- CVE: https://nvd.nist.gov/vuln/detail/CVE-2024-23342
- GitHub Advisory: GHSA-wj6h-64fc-37mp
- OSV Entry: https://osv.dev/vulnerability/CVE-2024-23342

---

## Resolved Vulnerabilities

This section documents vulnerabilities that have been resolved through package upgrades.

### 2026-04-06: Security Patch Batch

**Resolved 4 vulnerabilities** via dependency upgrades:

1. **CVE-2026-34073** - `cryptography` 46.0.5 → 46.0.6
   - Incomplete DNS name constraint enforcement on peer names
   - Severity: Not yet scored
   - GHSA: GHSA-m959-cc7f-wv43

2. **CVE-2026-33936** - `ecdsa` 0.19.1 → 0.19.2
   - Denial of Service via improper DER length validation in crafted private keys
   - Severity: Not yet scored
   - GHSA: GHSA-9f5j-8jwj-x28g

3. **CVE-2026-34070** - `langchain-core` 1.2.17 → 1.2.26
   - Path Traversal vulnerabilities in legacy `load_prompt` functions
   - Severity: Not yet scored
   - GHSA: GHSA-qh6h-p6c9-ff54

4. **GHSA-5239-wwwm-4pmq** - `pygments` 2.19.2 → 2.20.0
   - ReDoS vulnerability in AdlLexer (Archetype Definition Language lexer)
   - Previously accepted 2026-03-24, now resolved
   - CVE: CVE-2026-4539

**Verification:** All vulnerabilities confirmed resolved via `pip-audit` on 2026-04-06.

---

## Reporting a Vulnerability

If you discover a security vulnerability, please report it to: [security@example.com]

Do NOT create a public GitHub issue for security vulnerabilities.
