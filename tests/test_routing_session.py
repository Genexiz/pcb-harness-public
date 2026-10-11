from io import StringIO
from pathlib import Path
import asyncio
import json

import pytest

from eval.routing_smoke.prepare import prepare_campaign
from eval.routing_smoke.session import HOST_DISCLOSURE, run_stdio_session


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/routing/tiny"


def test_prepare_creates_five_isolated_hash_bound_runs(tmp_path):
    campaign = tmp_path / "campaign"
    runs = prepare_campaign(FIXTURE, campaign, repeats=5)

    assert [path.name for path in runs] == ["run-1", "run-2", "run-3", "run-4", "run-5"]
    manifests = [json.loads((path / "manifest.json").read_text()) for path in runs]
    assert len({manifest["run_id"] for manifest in manifests}) == 5
    assert all((path / "input/board.kicad_pcb").is_file() for path in runs)
    assert all((path / "project/board.kicad_pcb").is_file() for path in runs)
    assert all(manifest["max_actions"] == 300 for manifest in manifests)
    assert all(manifest["max_duration_seconds"] == 1200 for manifest in manifests)
    assert all(manifest["fixture_sha256"] for manifest in manifests)
    with pytest.raises(FileExistsError):
        prepare_campaign(FIXTURE, campaign, repeats=5)


def test_prepare_rejects_tampered_fixture(tmp_path):
    fixture = tmp_path / "fixture"
    prepare_campaign(FIXTURE, tmp_path / "seed", repeats=1)
    source = tmp_path / "seed/run-1/input"
    fixture.mkdir()
    for path in source.rglob("*"):
        if path.is_file():
            target = fixture / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())
    board = fixture / "board.kicad_pcb"
    board.write_text(board.read_text() + "\n")

    with pytest.raises(ValueError, match="fixture hashes"):
        prepare_campaign(fixture, tmp_path / "tampered", repeats=1)


def test_memory_relay_records_exact_calls_and_unavailable_model_fields(tmp_path):
    commands = [
        {"tool": "pcb_connect", "arguments": {}},
        {"tool": "pcb_summary", "arguments": {}},
    ]
    source = StringIO("".join(json.dumps(command) + "\n" for command in commands))
    sink = StringIO()
    transcript = tmp_path / "host-transcript.jsonl"

    asyncio.run(run_stdio_session(
        workspace=tmp_path,
        run_directory=tmp_path / "runs/service",
        transcript=transcript,
        backend="memory",
        source=source,
        sink=sink,
    ))

    rows = [json.loads(line) for line in transcript.read_text().splitlines()]
    output = [json.loads(line) for line in sink.getvalue().splitlines()]
    assert [row["tool"] for row in rows] == ["pcb_connect", "pcb_summary"]
    assert [row["arguments"] for row in rows] == [{}, {}]
    assert [row["sequence"] for row in rows] == [1, 2]
    assert output == rows
    assert rows[0]["host"] == HOST_DISCLOSURE
    assert rows[0]["host"]["name"] == "Codex desktop subscription"
    assert rows[0]["host"]["exact_model"] == "unavailable"
    assert rows[0]["host"]["provider_tokens"] == "unavailable"
    assert rows[0]["host"]["provider_cost"] == "unavailable"
    assert rows[0]["host"]["model_api_key_used_by_harness"] is False
    assert rows[1]["result"]["backend"] == "memory"


def test_relay_rejects_non_object_arguments_without_recording_a_fake_call(tmp_path):
    source = StringIO(json.dumps({"tool": "pcb_connect", "arguments": []}) + "\n")
    transcript = tmp_path / "host-transcript.jsonl"

    with pytest.raises(BaseExceptionGroup) as error:
        asyncio.run(run_stdio_session(
            workspace=tmp_path,
            run_directory=tmp_path / "runs/service",
            transcript=transcript,
            backend="memory",
            source=source,
            sink=StringIO(),
        ))
    assert error.value.subgroup(ValueError) is not None
    assert "object arguments" in repr(error.value.subgroup(ValueError))
    assert not transcript.exists()


@pytest.mark.parametrize("existing", ["transcript", "service"])
def test_m2_session_rejects_reused_evidence_before_launching_client(tmp_path, monkeypatch, existing):
    transcript = tmp_path / "host-transcript.jsonl"
    service = tmp_path / "runs/service"
    target = transcript if existing == "transcript" else service / "run.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("retained evidence\n")
    def unexpected_client(*args, **kwargs):
        pytest.fail("client launched before checking M2 run freshness")
    monkeypatch.setattr("eval.routing_smoke.session.Client", unexpected_client)
    with pytest.raises(FileExistsError):
        asyncio.run(run_stdio_session(workspace=tmp_path, run_directory=service,
            transcript=transcript, backend="memory", source=StringIO(), sink=StringIO()))
    assert target.read_text() == "retained evidence\n"
