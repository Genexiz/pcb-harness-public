# Document evidence

Store explicit local document snapshots with source URL, title/revision,
retrieval date, SHA-256, locator and redistribution status. Never treat a URL
as cached evidence. Confirmations bind exact document hashes and require an
identified human reviewer. Synthetic fixtures are not production evidence.

Numeric operating limits require explicit sourced lower/upper bounds in a
fact's optional `range: [lower, upper]`, with the matching `units` (`V` for
pin operating ranges). A scalar nominal or a claim string is not a range.
Missing bounds remain unknown; declared ranges exceeding sourced bounds fail
the provenance audit. Record bounds from the exact source revision and apply
the same human-confirmation requirements before production release.
