# Security and known limitations

The uploaded runtime source is preserved. These findings are disclosed, not silently patched or deployed.

1. **Authentication is external.** Flask has no authentication middleware. Cloud Run must require authentication. Local development should bind only to loopback.
2. **Period verification is incomplete.** Westgate discovery matches season/week labels; Circa matches week but not independently season. `build_bundle` does not validate PDF headers for season/week. Correctly labeled links can still point to incorrect documents.
3. **Redirect checks happen after fetching.** urllib follows redirects before final-host checks. These are not comprehensive SSRF controls. Routes do not accept user-supplied URLs, but redirect-hop/network restrictions remain a hardening item.
4. **Storage is not transactional.** Raw files are written sequentially before the bundle. A later failure can leave partial writes. The generic error label `REFUSED_NO_WRITE` is not proof of zero writes after a storage exception.
5. **Bundle hashes include time.** A new generation timestamp creates a different hash even with unchanged sources. Existing-object precondition failures are recorded without re-reading the stored object.
6. **Fourteen games are hard-coded.** Other valid slate sizes can be refused. Supported week numbers do not imply all slate sizes are supported.
7. **Circa PDF choice is order-sensitive.** The first resolvable approved-host PDF is used; full-season versus quarterly standings semantics are not independently checked.
8. **Rolling pages limit replay.** No verified historical discovery fallback is included. Today's page cannot establish what was available during an earlier failure.
9. **Malformed-input coverage is limited.** Integer handling uses `isdigit()` before `int()` and timezone/date edge cases need more tests. Not every malformed input necessarily receives the intended 422 response.
10. **PDF parsing is specialized.** Layout and typography changes can break extraction. Fetch-size limits are not a full untrusted-document isolation strategy.
11. **No end-to-end acceptance claim.** Local tests do not establish scheduler delivery, live cloud IAM/storage behavior, all source layouts, or downstream import.

## Publication review

The supplied archive contained application source, tests, Dockerfile, requirements, and README. Source inspection and pattern checks found no keys, tokens, emails, live cloud project/bucket identifiers, or deployment URLs. This does not guarantee absence of all vulnerabilities or sensitive information.

Historical tests contain contest aliases and expected picks; synthetic examples use invented aliases. Raw PDFs, credentials, account-specific configuration, and operational logs are excluded. Do not add them to source control.

Direct dependencies are pinned. No vulnerability assessment, complete transitive lock, image digest pin, container build test, or production security audit is claimed.

## License and data rights

No code license was selected on the owner's behalf. Public visibility is not automatically permission to reuse code. Third-party document rights remain separate. This project is not affiliated with or endorsed by the source organizations.

Before broader customer use, prioritize content-level period validation, configurable slate rules, storage error/status accuracy, deduplication, redirect restrictions, structured run logging, monitoring, and authorization for all outbound actions.
