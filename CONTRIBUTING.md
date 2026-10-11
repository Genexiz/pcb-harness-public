# Contributing

PCB Harness is preparing for open-source release. The project code is licensed Apache-2.0 (third-party files keep their own licenses); no public contribution workflow is assigned yet. This guide describes local development expectations.

Use Python 3.11 and the pinned dependency inputs. Follow `docs/mcp.md` for a complete test/MCP environment, or `docs/kernel.md` for Kernel-only work. Current native verification targets macOS and KiCad 10.0.6; other platforms are not yet certified.

Run `.venv/bin/python -m pytest -q`. Preserve meaningful RED→GREEN regression evidence for behavior changes. Test MCP behavior with the actual SDK client/STDIO process; do not replace Kernel state changes with mocked success.

Native edits belong only in a fresh scratch project under `runs/`, selected by exact instance/document path. Preserve immutable `fixtures/capability/`. Never test recovery against a user's real board, silently overwrite external edits, retry uncertain writes, or clear a journal to make tests pass.

Keep the model in the host: no required provider keys, subscription credentials or inference calls in the normal MCP workflow. Every geometry path must come from caller intent; no autorouter or hidden optimization. Honor revisions, action IDs, locks, rule/verification gates and recovery flags.

Include a reproduction, supported version/backend, exact commands and result scope with changes. Distinguish Memory/protocol tests, native KiCad checks, subscribed-host integration and hardware tests. A new method in a Python binding is not proof that the installed KiCad supports it.

For M3 circuit work, validate packaged offline schemas, audit exact source/asset
hashes, and use an independently supplied checklist. Never manufacture human
confirmations or make absolute maximum ratings into operating limits. Run the
synthetic circuit/native rule acceptance in a fresh output directory using
`playbooks/circuit/m3-grounding.md`; retain unknown/manual fabrication entries
and distinguish bootstrap acceptance from actual-board release eligibility.

Do not commit API keys, auth files, private projects, raw model transcripts or personal host configuration. Keep third-party source/asset provenance and license notices; generated synthetic fixtures should be reproducible. Publishing source/packages is a separate reviewed step.
