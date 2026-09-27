"""Deterministic end-to-end contracts for the curated Traffic Lab demos."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_product_surface import client_for


DEMOS = (
    ("mixed_ddos_recon", 2, 8, {"DDoS", "Reconnaissance"}, 1),
    ("ddos_one_way", 2, 4, {"DDoS"}, 0),
    ("c2_recurrence", 3, None, {"C2 / Beaconing"}, None),
    ("dga_lexical", 1, 2, {"DGA + DNS"}, 0),
    ("raw_pcap_ddos_recon", 11, 35, {"DDoS", "Reconnaissance"}, 3),
)


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario,observations,result_count,families,relations", DEMOS)
async def test_curated_judge_demo_completes_with_its_presentation_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: str,
    observations: int, result_count: int | None, families: set[str], relations: int | None,
):
    if scenario == "dga_lexical":
        model = Path("artifacts/dga/local/DGA_M1_R1_SERIALIZED_MODEL.joblib").resolve()
        monkeypatch.setenv("EVIDENCEGATE_DGA_MODEL", str(model))

    async with client_for(tmp_path / f"{scenario}.db") as (client, service):
        started = await client.post("/replay", json={"scenario": scenario, "speed": 0})
        assert started.status_code == 202
        status = await service.wait_for_replay()
        assert status.state == "COMPLETED"
        assert status.observations_emitted == observations

        trace = (await client.get("/runtime/trace", params={"after": 0, "limit": 500})).json()["events"]
        assert trace
        assert [event["sequence"] for event in trace] == list(range(trace[0]["sequence"], trace[-1]["sequence"] + 1))
        observation_ids = {event["observation_id"] for event in trace if event["kind"] == "OBSERVATION_CREATED"}
        assert len(observation_ids) == observations

        results = (await client.get("/results", params={"limit": 500})).json()["results"]
        assert all(result["source_observation_ids"] for result in results)
        assert all(set(result["source_observation_ids"]) <= observation_ids for result in results)
        if result_count is not None:
            assert len(results) == result_count
        result_ids = {result["result_id"] for result in results}

        derived = (await client.get("/investigations")).json()
        views = [view for view in derived["family_views"] if set(view["source_result_ids"]) & result_ids]
        assert families <= {view["family"] for view in views}
        view_ids = {view["family_view_id"] for view in views}
        links = [link for link in derived["links"] if link["left_family_view_id"] in view_ids and link["right_family_view_id"] in view_ids]
        if relations is not None:
            assert len(links) == relations

        if scenario == "ddos_one_way":
            assert any(result["result_type"] == "INSUFFICIENT_EVIDENCE" for result in results)
            assert any("REVERSE_FACTS" in result["visibility_snapshot"]["unavailable"] for result in results)
        if scenario == "c2_recurrence":
            persistence = [event for event in trace if event["kind"] == "RESULT_PERSISTED"]
            recurrence = next(result for result in results if result["mechanism_id"] == "C2-M1" and result["result_type"] == "REVIEW_FINDING")
            persisted = next(event for event in persistence if event["result_id"] == recurrence["result_id"])
            source_sequences = [event["sequence"] for event in trace if event["kind"] == "OBSERVATION_CREATED" and event["observation_id"] in recurrence["source_observation_ids"]]
            assert len(recurrence["source_observation_ids"]) == 3
            assert persisted["sequence"] > max(source_sequences)
        if scenario == "dga_lexical":
            assert {result["mechanism_id"] for result in results} == {"DGA-A1-M1", "DNS-T1"}
