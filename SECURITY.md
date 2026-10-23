# Security Policy

## 1. Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.x     | :white_check_mark: |
| < 2.0   | :x:                |

---

## 2. Reporting a Vulnerability

We take the security and integrity of payment recovery workflows seriously.

If you discover a potential vulnerability, please **DO NOT** create a public GitHub issue. Instead, report it privately to our engineering team:

1. **Email:** Send details to `security@recovery-engine.local` (or through GitHub Private Vulnerability Reporting).
2. **Details to include:**
   - Affected component(s) (`backend/api`, `backend/go-executor`, `audit_repository`, etc.)
   - Reproduction steps or proof-of-concept
   - Impact assessment on idempotency, rate limiting, or financial consistency
3. **Response Timeline:**
   - An acknowledgment will be sent within 24 hours.
   - A triage update and mitigation timeline will be provided within 72 hours.

---

## 3. Threat Model & Security Design

This repository incorporates security-by-design patterns:
* **Idempotency Protections:** Multi-layered defense preventing duplicate financial actions.
* **Tamper-Evident Ledger:** RFC 6962 SHA-256 Merkle trees providing cryptographically verifiable inclusion proofs.
* **Secret Management:** Strict `.gitignore` rules preventing `.env` and credential leakage.
* **Least Privilege:** Services connect with partitioned database roles and scoped tokens.
