# Security policy

This repository is a demonstration source kit, not a supported platform distribution.
Use a current compatible platform and verify service access, identity trust and
runtime versions in your own environment.

Please report suspected vulnerabilities privately through this repository's
GitHub **Security → Report a vulnerability** form. Do not post credentials,
private deployment logs, tokens or personal data in public issues. Include the
source commit, affected component and a sanitized reproduction.

Only the current main branch receives example updates. The source license does
not provide a response-time commitment. Platform/runtime findings should also be
reported through your platform vendor's security channel.

Credential files, local profiles and deployment journals are ignored. Never
commit them. Preserve TLS checks and exact SSO admission. Hub uses the presenter's
existing permissions; a read-only prompt is not an authorization boundary.
