# Security and Production Readiness

## Included controls

- Argon2 password hashing
- Short-lived JWT access tokens
- Rotating refresh tokens with reuse detection
- Failed-login lockout
- Platform and site-scoped authorization
- API-key hashing and scope checks
- Request IDs and defensive response headers
- Strict Pydantic request validation
- Parameterized SQLAlchemy queries
- Media size limits and filename sanitization
- Audit records for sensitive operations
- Signed webhook payload support

## Required production work

- Replace all example secrets and passwords.
- Store secrets in a cloud secrets manager.
- Use TLS at the load balancer and database.
- Add managed WAF and rate limiting.
- Enforce antivirus and content-type inspection for uploads.
- Move media to private object storage and use signed URLs where required.
- Prevent webhook requests to loopback, metadata and private-network addresses.
- Add background delivery retries with exponential backoff and dead-letter handling.
- Configure encrypted backups and test restoration.
- Add SIEM forwarding, alerting and privileged-action review.
- Review privacy, retention and data-residency requirements.
- Perform dependency, container, SAST, DAST and penetration testing.

This project is an engineering starter and must be reviewed for organization-specific legal, security, privacy and compliance requirements before production use.
