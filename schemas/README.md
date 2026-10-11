# Circuit bundle schemas

The authoritative offline Draft 2020-12 schemas ship inside
`src/pcb_harness/circuit/schemas/`. Use `load_bundle` to validate all eight
documents, local artifact paths, and stable identifier uniqueness. Schema
validation is structural; independent circuit review and native verification
are separate gates. No remote schema resolution is permitted.
