# PCB Harness — Development Roadmap

วันที่: 2026-10-03 · สถานะ: แผน milestone สำหรับเริ่มพัฒนา ไม่ใช่ implementation ที่รันแล้ว

Spec: not published in this repository; this roadmap summarizes the requirements it references.

## จุดหมาย

ให้ harness สร้างและตรวจบอร์ด STM32F103C8T6 multi-interface ตาม spec v2 พร้อม artifacts ที่เปิดแก้ใน KiCad และส่งให้คนตรวจผลิตได้ จากนั้นใช้ board revision จริงยืนยันการทำงานพร้อมกัน เป้าหมายวิจัยประเมินด้วย controlled comparisons แยกจาก milestone ของบอร์ดจริง

ลำดับหลัก: พิสูจน์ API → Kernel → agent บอร์ดเล็ก → circuit/docs/rules → full STM32 board → release/bring-up → controlled eval

โฟกัสรอบแรกเป็น M0 เท่านั้น ไม่ scaffold pipeline ทั้งหมดก่อนรู้ว่า IPC operations ที่ต้องใช้ทำงานจริงอย่างไร Detailed implementation plans แยกตาม milestone เพื่อไม่ผูกโค้ดกับ API ที่ยังไม่ได้พิสูจน์

## M0 — KiCad capability spike

**Deliverable:** disposable KiCad fixture + capability report ที่แยก supported/unsupported/unverified พร้อม commands, outputs, snapshots และวิธี recovery

**ขอบเขตไฟล์เมื่อเริ่ม execution:**

- `docs/capabilities/kicad-10-macos.md`: รายงานข้อค้นพบและ API mapping
- `experiments/kicad-ipc/`: disposable probes ไม่ถือเป็น product implementation
- `fixtures/capability/`: small project ที่ใช้ยืนยัน geometry/rules/CLI
- `runs/capability/<run-id>/`: raw logs, baseline/end snapshots, verification JSON และ SVG

**Steps:**

- [x] ตรวจคำสั่งและรุ่นจาก executable จริง:

  ```sh
  /Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli version
  /Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb drc --help
  /Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli sch erc --help
  /Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb export svg --help
  python3 --version
  ```

  บันทึก output จริงและ executable path ปัจจุบัน version/DRC/ERC help ตรวจแล้วระหว่างวางแผน; ยังต้อง capture เข้า run artifacts ตอน execution

- [x] เลือก released `kicad-python` จาก metadata ที่เข้ากับ KiCad 10.0.0 และ Python ที่ใช้จริง บันทึก version/dependencies; อ่าน version-matched examples/API docs ก่อนเขียน probe ห้ามยึด development documentation เป็น available API
- [x] เตรียม scratch project ที่มี schematic, PCB, project settings และ custom rules; resistor 3 ตัว, 2 nets และ geometry ที่อ่านตำแหน่งได้แน่นอน มี short/clearance/width/open-circuit variants ที่สร้างจาก baseline สำเนาแยก
- [x] เปิด scratch board ใน PCB Editor และเชื่อม IPC แบบระบุ instance/document identity ตรวจ API server configuration; หาก GUI/API ไม่มี ให้บันทึก setup requirement โดยไม่แก้หรือ restore บอร์ดของผู้ใช้
- [x] ทดลองเพิ่ม/อ่าน/move/rotate/flip footprint; ตรวจ transformed pad geometry กับ saved file และ KiCad UI; บันทึก capability ของ asset loading/bootstrap
- [x] ทดลอง exact track polyline, via และ update/delete object; คำสั่งต้องลงตามพิกัดที่ probe ระบุ ไม่มี autorouter/shove/route search
- [x] ทดลอง commit/revert multi-action transaction และ save/reload ตรวจ baseline hashes กับ readback ข้อที่ API ทำไม่ได้ให้ประเมิน project-copy restoration พร้อม state reconciliation แทนการอ้างว่าเป็น native undo
- [x] ทดลอง custom rules negative fixtures และ zone refill ใช้ command บน disposable project copy:

  ```sh
  /Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli pcb drc \
    --format json --severity-all --schematic-parity \
    --refill-zones --save-board --exit-code-violations \
    --output runs/capability/drc.json fixtures/capability/board.kicad_pcb
  /Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli sch erc \
    --format json --severity-all --exit-code-violations \
    --output runs/capability/erc.json fixtures/capability/board.kicad_sch
  ```

  Expected: known-bad fixtures ถูกตรวจจับตามประเภท; good fixture ไม่มี mandatory violations; process errors ไม่ถูกแปลเป็น design pass สร้าง parent output directories ก่อนเรียก command ตรวจ JSON schema และ exit codes จากรุ่นจริง ไม่เดาค่ารหัสผิดพลาด

- [x] ทดสอบ SVG export แล้ว map coordinates/layer selection/crop กับ query geometry; ไม้บรรทัดและ net highlighting ที่ API ไม่มีให้ระบุว่าเป็น overlay ของ harness
- [ ] ทดสอบ human edit/stale read, disconnect ระหว่าง mutation, board reopen และ modified settings ต้องรู้ว่าเกิด commit หรือไม่ก่อน retry; checkpoint ไม่ทับ edits โดยเงียบ
- [x] สรุป capability matrix: operation, exact API/CLI, preconditions, units/IDs, supported status, evidence path และ failure handling

**ผล execution 2026-10-03:** M0 core gate ผ่านบน KiCad 10.0.0 macOS; ดูรายงาน `docs/capabilities/kicad-10-macos.md` และ 47 regression tests. Human GUI edit, saved reload และ controlled lost commit reply ยืนยันแล้ว; OS-crash/all-delivery-phase และ unsaved settings/atomic concurrency ยังไม่ยืนยัน จึงคง extended checklist ข้อนั้นไว้

**Gate:** สคริปต์ที่ไม่ใช่ AI สร้าง/แก้ footprint และ copper geometry บน KiCad จริง ตรวจด้วย saved project และ restore ได้; mapping ของ rules/zone/verification/render มีหลักฐานหรือข้อจำกัดที่ชัดเจน หาก operation ที่จำเป็นไม่มีเส้นทางที่ทำได้จริง ให้ปรับ backend contract ก่อน M1

## M1 — Kernel ที่เชื่อถือได้

**Architecture boundary / planned file responsibilities:**

```text
src/pcb_harness/
  domain/          geometry, object IDs, rules, revisions, typed results
  kernel/          action validation, single writer, transactions, query facade
  backends/       ipc editor, cli verifier/exporter, memory test backend
  runs/           manifests, event log, checkpoint bundles, reconciliation
  rendering/      coordinates/layers/overlays from validated saved data
tests/
  contract/       identical operation semantics across backends
  integration/    real KiCad fixtures and persisted project verification
```

**Deliverable:** scripted place/route/query/render/verify workflow ผ่าน Kernel interface เดียวที่ใช้ KiCad จริง; small Memory backend ใช้ tests

**Must cover:** stale revision rejected; duplicate action not applied twice; timeout reconciled; rotate/flip pad transforms; same-net versus different-net copper; via layer spans; clearance at board edges/holes; unrouted progress separated from geometric DRC; strict atomic rip-up/reroute; restore preserves rules/assets/settings; locks honored

**Gate:** known-bad fixtures ไม่มี false pass; negative rules ตรวจด้วย real KiCad; final verification ใช้ saved/reloaded project ไม่ใช้ Memory oracle; full/project and scoped checks เรียกชื่อและเก็บ evidence ต่างกัน

## M2 — Subscription-driven MCP และ single-agent routing proof

**Files:** `src/pcb_harness/mcp_server.py`, `fixtures/routing/`, `eval/routing_smoke/`, `playbooks/routing/`, host connection examples และ MCP protocol/contract tests

**Deliverable:** local MCP server ให้ Codex ที่ใช้ ChatGPT Subscription เรียก Kernel ทำ placement/routing บน circuit/netlist ที่คนตรวจแล้ว ไม่บังคับ LLM API key และไม่เพิ่ม upstream circuit agent โมเดลคิด/เลือก tools ใน host; Harness รับ intent และตรวจ/ลงมือผ่าน Kernel

**Experiment:** 5 repeats, ≤300 committed/rejected action attempts ต่อ run, ≤20 นาที wall time ต่อ run, action/time limits ระบุใน frozen run config ก่อนเริ่ม และบันทึก host/model ที่เข้าถึงได้ token/cost/settings ที่ host ไม่เปิดเผยเป็น unavailable; ไม่อ้างว่าเป็น controlled provider eval ทุก action attempt นับรวมแม้ rollback; tool/provider failures แยกประเภทแต่ไม่ลบทิ้งจากรายงาน

**Gate:** ≥3/5 runs ผ่าน mandatory DRC, zero unconnected และ circuit parity ภายใน envelope; ตรวจ log ว่า LLM ระบุ placement/path/vias เอง หากไม่ผ่าน วิเคราะห์สาเหตุ geometry/context/tool ergonomics ก่อนเพิ่ม multi-agent ไม่ใช้ autorouter แก้ผลทดลอง

**ผล execution 2026-10-09:** Gate PASS 4/5 ใน `runs/routing/m2-2026-10-09-r3`. Runs 1–4 ใช้ 6 admitted writes/run และ 232.850–240.979 วินาที ผ่าน mandatory DRC, zero unconnected และ circuit parity; run 5 หยุด fail-closed หลัง checkpoint reply timeout เป็น `RECOVERY_REQUIRED` และไม่ retry. Host/model settings/tokens/cost ที่ host ไม่เปิดเผยบันทึกเป็น unavailable; Harness ไม่ใช้ provider API key. ต้องทำ read-only stabilization หลังเปิด fresh KiCad document เพราะ native `save_as` ครั้งแรกเปลี่ยน serialized live state ข้อนี้เป็น environment/tool-ergonomics limitation ไม่ใช่ fabrication proof.

## M3 — Requirements, parts, circuit และ rules

**Files:** `schemas/`, `parts/`, `docs_store/`, `src/pcb_harness/circuit/`, `src/pcb_harness/fabrication/`, `checklists/`, `playbooks/circuit/`

**Deliverable:** validated JSON requirements/circuit/constraints และ readable schematic/PCB bootstrap พร้อม provenance, complete profile และ upstream circuit review

**Gate:** pinout/footprint wrong, missing required interface, voltage mismatch, ignored errata, duplicate ref, intentional no-connect mismatch และ native F103 USB+CAN concurrency conflict ถูกจับจาก independent checklist; ไม่ยอมให้ circuit-spec self-consistency แปลว่า functional correctness

Complete fabrication profile ต้องครอบคลุม selected service และแปลงกฎที่ enforce ได้ไป KiCad พร้อม negative tests Unknown/manual critical facts ปิด release gate และรายงาน evidence ที่ขาด

**ผล implementation 2026-10-09:** synthetic M3 acceptance ใน `runs/circuit/m3-2026-10-09` ผ่าน strict bundle/provenance/independent review, native schematic/PCB bootstrap (ERC/geometry/parity/netlist), eight circuit negatives และ eight native fabrication negatives พร้อม clean baseline. `release_eligible=false`; complete profile structure ไม่ใช่ confirmed manufacturer compliance และ real STM32 parts/package/resource/firmware feasibility ยังเป็น M4. รายงานข้อจำกัดและ final review อยู่ที่ `docs/capabilities/m3-progress.md`.

**ผลปิด M3 2026-10-10:** final review พบ Important 7 จุดและแก้ครบพร้อม RED→GREEN regressions; full suite 373 tests ผ่าน และ post-review acceptance ใน `runs/circuit/m3-2026-10-10-final` ผ่านทั้งสี่ gates พร้อม artifact integrity, 8/8 circuit negatives และ 8/8 fabrication negatives. คง `release_eligible=false`; Minor 2 ข้อที่ deferred และ rulings บันทึกใน `docs/capabilities/m3-review.md`. M3 software/native calibration complete; milestone ถัดไปคือ M4 feasibility.

## M4 — STM32 board เต็มชุด

**Files:** `benchmarks/stm32-communications/`, `checklists/stm32-communications/`, `src/pcb_harness/orchestration/`, `playbooks/placement/`, `playbooks/review/`

**First feasibility deliverables:** exact part/package choices, document facts, pin allocation, SPI/interrupt scheduling, power/thermal budget, 64 KB/20 KB firmware capacity estimate พร้อม compile/map evidence ของ minimal test firmware และ connector/mechanical envelope

ทั้งสอง CAN networks ใช้ external controller; Ethernet WIZ550io เป็น module บน host board MCU ยังวางโดยตรงตาม requirement GPIO allocation ต้อง reserve SWD, boot และ clock ไม่ใช้ reference pinout โดยไม่ตรวจ package

**Gate ก่อน layout:** interface counts/concurrency/test envelope ทำได้ตามเอกสารและ resource budget; circuit review/required facts พร้อม; schematic/ERC/bootstrap/parity ผ่าน หากไม่ fit ห้ามเปลี่ยน MCU/ตัด port โดยเงียบ ต้องออก feasibility report และ design revision ที่อธิบายข้อจำกัด

**Gate หลัง layout:** stage repair/checkpoints ทำงาน; routing complete; saved-file DRC/ERC/parity ผ่าน; documentation compliance ไม่มี mandatory rule fail/unknown; quality report และ unresolved manual items ครบ

**ผลเริ่ม M4 2026-10-10:** real-target candidate allocation ครบ9 interfaces และ static pin/DMA/EXTI checks ผ่าน; SPI wire-time estimate ผ่านภายใต้ workload ที่ระบุ. Cross-compiled resource probe ใช้ flash576 bytes/RAM13200 bytes รวม stack4096; ยังไม่มี complete interface drivers. Power/thermal, retained ST sources/errata, complete BOM/circuit/native และ mechanical/fabrication gates ยัง unknown. `layout_allowed=false`, `release_eligible=false`; ดู `docs/capabilities/m4-progress.md`. M4 ยังไม่ complete และยังไม่เริ่ม layout.

**ผลต่อ M4 engineering 2026-10-10:** เพิ่ม hash-bound dossier กับ circuit draft ครบ9 interfaces; CAN memory/timestamp/FIFO/bit-rate arithmetic ผ่าน (Classical384B/FD1280B ต่อ2KB controller). แยก CAN VIO บน3V3 ทำให้ reserve เป็น0.572A และ direct5V0.16A. เก็บ8/11 publisher snapshots พร้อม17 planned errata policies; ST originalsยังขาด และ WIZ550io54/55mm conflict/connector envelopes ยังไม่ปิด. Native circuit, complete firmware และ manufacturing/thermal gates ยัง unknown; ไม่อนุญาต layout/release จากผล arithmetic.

**ผลปิด continuation review 2026-10-10:** แก้ Important3ข้อด้วย9 RED→GREEN regressions: factsต้องตรงVDD/VIO, inventoryต้องครอบคลุมU8/อุปกรณ์ที่เพิ่ม และ hash/formatตรวจbytesชุดเดียวกัน. Full suite469 testsผ่าน ไม่มีskip; reportสุดท้าย `runs/m4/engineering-final-2026-10-10` ผ่านintegrity แต่ยังexit2/ปิดlayoutด้วย7 prerequisites. ดู `docs/capabilities/m4-engineering-review.md`; full M4 ยังไม่ complete.

**ผล core asset preparation 2026-10-10:** สร้าง standalone exact-MPN assets6ชนิด และ core BOM8IC+WIZ550io1instanceที่ยังขาดasset; ตรวจderivativesกับsourceที่captureไว้ทั้งMPN/package/document/geometry/BOM. แก้ Important2ข้อพร้อม16 RED→GREEN regressions; full suite528 testsผ่าน ไม่มีskip และKiCad10.0.6เปิด/exportsymbolsทั้ง6ชนิดได้. Final run `runs/m4/core-assets-final-2026-10-10` ผ่านhash/semantic verification แต่ยังexit2/accepted real-target assets0. Support BOM, module mechanics, source-bound pinout/package facts และ complete circuit/firmwareยังไม่ครบ; ดู `docs/capabilities/m4-core-preparation.md`.

**ผล circuit candidate 2026-10-10:** schematic เปิดด้วยKiCad10.0.6ได้ ครบ9interfaces/104components/73nets/19NC; WIZ550io candidateแปลงจากEagleCADผู้ผลิต. Native netlistตรงทั้งหมด แต่ERCยัง4errorsและsupport18typesยังไม่qualifiedเป็นexact purchasingMPNs. แก้reviewImportant2ข้อด้วยnative/sidecarRED-to-GREEN tests; full suite612ผ่านไม่มีskip. Final packet `runs/m4/circuit-review-final-2026-10-10`; ไม่มีPCB/layout/bootstrap acceptanceและfullM4ยังไม่complete. ดู `docs/capabilities/m4-circuit-review.md`.

**ผล integrated checkpoint 2026-10-11:** circuit 141 components/99 nets มี ERC 0 violations (ระบุ default-ignored checks และ supply-drive markers 3 จุด) และ firmware ครบ 9 drivers ใช้ Flash 34,708 B/RAM 17,160 B. Independent review พบ Important 10 ข้อ (gate อ่าน flag ที่เขียนเอง, ทิ้ง blockers ของ sub-packet, required facts ไม่มี record, แก้ baseline ทับของเดิม) แก้แล้วพร้อม regressions. Packet ที่ seal แล้ว `runs/m4/completion-2026-10-11-r3` ยังมี pre-layout blockers 9 ข้อ (required facts มี record ครบ 116 แต่ยัง unconfirmed; ERC re-run และ cross-packet binding ผ่าน); layout ยังปิด. ดู `docs/capabilities/m4-completion.md`.

## M5 — Release และการทดสอบจริง

**Files:** `src/pcb_harness/release/`, `test_plans/stm32-communications/`, `hardware_tests/stm32-communications/`, `eval/`, `workers/`

**Deliverable:** project bundle, Gerber/drill, BOM, placement file ตาม assembly choice, drawings, manufacturing/profile manifest และ bring-up plan; export แล้วตรวจ geometry/layer/drill/origin/BOM-placement consistency

**Physical gate:** คนตรวจ release; ผู้ใช้ดำเนินการผลิตตาม revision; ทดสอบ power/boot/SWD แล้วแยก interface และ simultaneous 30-minute envelope ตาม spec พร้อม raw counters/sequence logs ไม่อ้าง hardware tested จากการ export หรือ software simulation

**Research gate:** controlled model/tool baselines frozen, exploratory repeats, absolute gains/intervals และ costs; ratio คำนวณเฉพาะเงื่อนไขที่ denominator มีความหมาย; Linux virtual-display worker ต้องผ่าน scripted fixture และ isolation/resume ก่อนนำไป eval

## MCP และงานหลัง v1

MCP wrapper เป็นเส้นทางหลักของ M2 หลัง M1 native acceptance ผ่าน ให้ revision/locks/rules/errors เหมือน native Kernelและเก็บ run logs Codex local STDIO เป็น host แรก ใช้โมเดลจาก Subscription ผ่าน sign-in ของ host โดย Harness ไม่ถือ provider keys หรือ subscription credentials Host-driven session ไม่ปน controlled eval; API-key providers เป็นทางเลือกอนาคตเมื่อผู้ใช้ร้องขอ

Connection gate: จริงทั้ง initialize/tools-list/tools-call, input validation, structured errors, single-writer behavior, reconnect/journal handling และเรียก tool จาก host ที่ sign in ด้วย ChatGPT ได้โดยไม่มี model API key การ register server ต้องยืนยันหลัง client restart; แค่ไฟล์ config ไม่ใช่หลักฐานว่าเชื่อมสำเร็จ KiCad plugin และ raw Ethernet PHY routing เป็นงานรุ่นถัดไป

## Open Source release

ผู้ใช้ยืนยัน 2026-10-09 ให้ทำโปรเจกต์นี้เป็น Open Source เตรียม license ของ project และ third-party notices, public setup/limitations, contribution guidance, reproducible synthetic fixtures และการคัดเลือก artifacts ที่เผยแพร่ได้ ตาม `docs/open-source.md` Runtime/code/docs ต้องไม่บังคับใช้บัญชีหรือ API key ของผู้พัฒนาเพื่อทดสอบ Kernel การ publish repository/package เป็นขั้นต่างหาก; ยังไม่มี public repository หรือ release ที่ยืนยันแล้ว

## ลำดับการตัดสินใจและขอบเขตการทำงาน

- ค่าทาง hardware และ test envelope ใน spec เป็น defaults ที่เปลี่ยนได้ผ่าน versioned design revision
- สถานะปัจจุบัน: M0 core verified บน 10.0.0; CLI regression และ initial M1 native Kernel acceptance บน 10.0.6 ผ่าน; M2 single-agent routing feasibility ผ่าน 4/5; M3 synthetic circuit/native bootstrap acceptance ผ่านตาม report; M4 real-target engineering evidence ผ่าน software review แต่ complete-board prerequisites/layout ยังเปิดค้าง
- Repository อยู่ <repository> บน work/m0-kicad-capability; เก็บงานและ evidence แบบ local commits ไม่มี push/merge
- ก่อนเริ่มแต่ละ milestone ให้เขียน execution plan เฉพาะ milestone จาก interface/API ที่พิสูจน์แล้ว พร้อม exact files, tests, commands และ exit criteria
- เริ่ม M0 แล้วเดินตาม gates; ไม่มีการข้ามไป full-board routing เพราะสร้างไฟล์ตัวอย่างได้หนึ่งครั้ง


M2 execution update 2026-10-09: local MCP exposes 14 tools with calibrated PNG views and a durable frozen run envelope (300 admitted writes / 1200 seconds default). Actual subscribed-host feasibility passed 4/5 on the reviewed tiny circuit; raw evidence is local/ignored and summarized in `docs/capabilities/m2-progress.md`. MCP native edits still require the exact connected stable 10.0.6 backend. This result advances the roadmap to M3 but does not authorize full-board layout or manufacturing claims.
