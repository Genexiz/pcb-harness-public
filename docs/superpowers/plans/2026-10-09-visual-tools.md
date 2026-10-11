# PCB Visual MCP Tools Plan

> Execute inline with superpowers:executing-plans; user approved board/region renders and editor capture. One fresh final review; no repeated planning approval.

**Goal:** add pcb_render_board, pcb_render_region and pcb_capture_editor, returning actual PNG ImageContent plus revision/source/layer metadata, without model API keys.
**Architecture:** service serializes visual calls with all other tools. A renderer rasterizes safe SVG and adds coordinate/layer/revision legend. Native uses CLI export from an IPC snapshot; explicit Memory generates a labelled diagram. Capture targets one bound PCB Editor PID/window and never substitutes render or desktop capture.
**Spec:** ../../PCB Harness — Design Spec (v2).md sections6/7/10 and approved in-chat visual design.
**Stack:** Python3.11, official MCP2.3.0, KiCad10.0.6 CLI, resvg-py0.5.0, Pillow12.3.0; optional macOS Quartz12.2.2 for window metadata/permission preflight, system screencapture for bound window.

## Constraints / review focus

- No inference/API-key access, no autorouter, no native mutation-gate changes.
- Return image bytes only with honest source/revision; Memory is test-only, saved fixture is not live editor.
- Validate layer/finite crop/pixel bounds before export; fail if native outline/unit mapping cannot be established. IPC/query geometry remains authoritative.
- Source revision must match before/after snapshot/export/render; conflicting edits refuse image delivery.
- Rasterization rejects external references, active SVG and unbounded image/SVG sizes; do not fetch URLs or arbitrary local files.
- Artifacts stay under the fixed run directory; failed export/capture never reuses a prior image.
- Capture requires macOS permission and an explicit API-instance PID; matching owner/title must be unique. No full-screen fallback or automatic OS permission request.
- Existing lack of GUI/socket does not block native CLI saved-fixture rendering or Memory/protocol tests; current-editor capture/live IPC remain unverified until executed.

## Task 1 — SVG/PNG rendering

**Files:** src/pcb_harness/rendering.py, tests/test_rendering.py, pyproject.toml, requirements-mcp.lock.
**Interfaces:** render_svg(svg_text, bounds_mm, offset_mm, revision, layers, output, region_mm=None, width_px=1024, source='...', test_only=False) -> metadata + private _image_bytes. export_saved_board(board_path, bounds_mm, revision, layers, output, region_mm=None, width_px=1024, cli=...) -> same.

- [ ] RED tests: actual PNG/metadata and independently checked pad pixel, exact crop mapping, invalid crop/layers/size, forbidden external SVG, native outline calibration mismatch.
- [ ] Implement finite rectangles, allowed layers, uniform mm→pixel mapping, source/revision legend, bounded rasterization and hash/artifact metadata. Edge.Cuts is always included for calibration.
- [ ] Real CLI test exports immutable synthetic fixture into a disposable output and checks F.Cu/B.Cu pad/track pixels against known coordinates. No GUI needed; saved-fixture source label required.

```python
image=export_saved_board(FIXTURE,[10,10,70,30],revision,['F.Cu','B.Cu'],output)
assert image['revision']==revision and image['source']=='saved KiCad board'
assert image['_image_bytes'].startswith(b'\x89PNG')
```

## Task 2 — Editor capture and serialized service

**Files:** src/pcb_harness/capture.py, mcp_service.py, ipc.py, tests/test_capture.py, test_mcp_service.py.
**Interfaces:** capture_editor(project, socket, revision, output) -> metadata + private _image_bytes; select_editor_window(windows,pid,project_stem) rejects ambiguous/wrong windows. MCPService.render(layers, region_mm=None,width_px=1024), capture_editor() bind fixed backend/session.

- [ ] RED: select only bound PID/PCB Editor title, reject wrong/ambiguous/default socket identity, permission false refuses before invoking capture, Memory capture refuses rather than drawing a fake screenshot.
- [ ] Implement optional OS adapter without opening apps or requesting permissions; capture only window ID with validated PNG/dimension checks.
- [ ] Service render requires connection and stable revision. Native snapshot uses existing guarded copy and bounds; Memory scene is explicitly labelled. Capture rechecks revision/window identity and returns no board coordinate mapping.
- [ ] Test service state unchanged by images; Native revision changes cause CONCURRENT_EDIT instead of returning stale image.

## Task 3 — MCP image content, docs and verification

**Files:** mcp_server.py, tests/test_mcp_server.py, experiments/mcp/smoke_visuals.py, docs/mcp.md, docs/capabilities/visual-progress.md, README.md.
**Interfaces:** pcb_render_board(layers=['F.Cu','B.Cu'],width_px=1024), pcb_render_region(region_mm,layers=['F.Cu','B.Cu'],width_px=1024), pcb_capture_editor(). Success returns TextContent + actual PNG ImageContent + structured metadata; errors contain no image.

- [ ] Actual SDK/STDIO RED tests for 14 discovered tools, PNG bytes/MIME/hash consistency, crop metadata, invalid requests and explicit unsupported capture.
- [ ] Implement additive-write annotations; images are outputs, not provider calls. Do not put base64 into JSON/text metadata.
- [ ] Produce saved-fixture native full/crop PNG artifacts; view them for visual QA. Record unavailable current-editor capture honestly.
- [ ] Full suite and one fresh reviewer; Important fixes in one RED→GREEN pass; commit locally with no public publish. Host image display/analysis requires host support and its subscription; no new credentials.

## Acceptance

Actual native CLI fixture images and demo images have layer/coordinate/revision legends, bounded crops and verified PNG/pixel metadata; actual SDK clients receive ImageContent without keys. Capture identity/permission/error contract is tested and actual OS availability reported. Live native render/capture cannot be claimed from Memory or saved-fixture images.
