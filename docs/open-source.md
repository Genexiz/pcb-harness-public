# Open-source preparation

The user confirmed on 2026-10-09 that PCB Harness is intended to be open source. On 2026-10-11 the user selected **Apache-2.0** for the project's own code (`LICENSE`). This public repository is generated from the maintainer's development tree; non-redistributable files are omitted (see `THIRD_PARTY.md`).

Third-party files keep their own licenses and are not relicensed. Under `benchmarks/stm32-communications/firmware-full/vendor/`, ST HAL/USB and CMSIS (BSD-3-Clause/Apache-2.0) and WIZnet ioLibrary keep their bundled license files. The Microchip CAN FD SPI driver says it may be used "exclusively with Microchip products" and grants no explicit redistribution right. Copied KiCad library footprints/symbols are CC-BY-SA 4.0 with the KiCad library exception.

Public-tree policy: the Microchip driver is fetched by locked hash (`fetch_microchip.py`), third-party notices are in `THIRD_PARTY.md`, and source-retrieval tooling and local paths are not distributed.

## Design requirements

- Keep the Kernel and MCP tool contracts inspectable and reusable. The primary host-driven workflow uses the user's own supported subscription and does not require a developer-owned model API key.
- Keep deterministic synthetic fixtures and meaningful offline Kernel tests in the repository. Real CLI/IPC checks require KiCad and the documented GUI setup, but no model subscription.
- Document supported versions/platforms, installation, configuration, recovery limits and actual verification evidence. Current implementation targets macOS; do not advertise untested platforms as supported.
- Provide configurable local paths and connection examples; never distribute one user's host credentials or personal account configuration.
- Record provenance of included footprints, symbols, schematics and test data. Link to third-party datasheets/reference material unless redistribution is explicitly permitted; do not silently relicense imported assets.

## Before public release

1. Select a project license and add its actual LICENSE text and package metadata. No project license is assigned yet; do not label an unlicensed public dump as an open-source release.
2. Audit direct/transitive dependency licenses and any bundled assets; retain required copyright/license notices. Installing a dependency for development is different from bundling it in a distributable package.
3. Add CONTRIBUTING guidance and issue/reproduction instructions sized to the actual supported code. Specify how reviewers verify change scope, native capability gates and fixture safety.
4. Check tracked files and selected release artifacts for credentials, private projects, model transcripts and account-specific settings. Raw local runs remain ignored by default; publish only intentionally selected, reproducible evidence.
5. Test a clean checkout/install and published entry points with documented dependencies, explicit KiCad version and fresh scratch fixtures. MCP initialization/tool calls must be tested from a real host before claiming integration works.
6. Prepare the repository/package description and release limitations for review. Creating a public repository or publishing a package is a separate action; neither has happened yet.

Dependency metadata inspected locally: kicad-python 0.8.0 reports MIT. The runtime uses the installed KiCad application over IPC/CLI; no KiCad application binary is bundled at present. This note is not a completed dependency/asset license audit and does not choose a license for this project.
