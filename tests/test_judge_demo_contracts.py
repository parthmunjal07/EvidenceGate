"""Deterministic end-to-end contracts for the curated Traffic Lab demos."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_product_surface import client_for


DEMOS = (
    ("mixed_ddos_recon", 12, 65, 60, 17, {"DDoS", "Reconnaissance"}, 8, 2, 500),
    ("ddos_one_way", 8, 40, 37, 11, {"DDoS"}, 5, 2, 500),
    ("c2_recurrence", 7, 14, 14, 10, {"C2 / Beaconing", "Data Transfer"}, 7, 0, 500),
    ("dga_lexical", 6, 12, 12, 6, {"DGA + DNS"}, 0, 0, 500),
    ("encrypted_tls_session", 1, 1, 1, 1, {"Encrypted Sessions"}, 0, 0, 50),
    ("raw_pcap_ddos_recon", 18, 58, 71, 15, {"DDoS", "Reconnaissance"}, 8, 5, 500),
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario,result_count,family_count,link_count",
    [
        ("mixed_ddos_recon", 65, 17, 8),
        ("dga_lexical", 12, 6, 0),
        ("encrypted_tls_session", 1, 1, 0),
    ],
)
async def test_curated_demo_deterministic_rerun_recomposes_exact_source_results(
    tmp_path: Path, scenario: str, result_count: int, family_count: int, link_count: int
):
    async with client_for(tmp_path / f"{scenario}-rerun.db") as (client, service):
        run_result_ids = []
        for attempt in range(2):
            started = await client.post("/replay", json={"scenario": scenario, "speed": 0})
            assert started.status_code == 202
            status = await service.wait_for_replay()
            assert status.state == "COMPLETED"
            if attempt == 1:
                assert status.results_persisted == 0
            trace = (await client.get("/runtime/trace", params={"after": 0, "limit": 500})).json()[
                "events"
            ]
            observations = {
                event["observation_id"]
                for event in trace
                if event["kind"] == "OBSERVATION_CREATED" and event["canonical_observation"]
            }
            results = (await client.get("/results", params={"limit": 500})).json()["results"]
            source_results = [
                result
                for result in results
                if result["source_observation_ids"]
                and set(result["source_observation_ids"]) <= observations
            ]
            assert len(source_results) == result_count
            ids = sorted(result["result_id"] for result in source_results)
            run_result_ids.append(ids)
            derived = (
                await client.get(
                    "/investigations", params=[("source_result_id", item) for item in ids]
                )
            ).json()
            assert len(derived["family_views"]) == family_count
            view_ids = {view["family_view_id"] for view in derived["family_views"]}
            assert len(derived["links"]) == link_count
            assert all(
                link["left_family_view_id"] in view_ids and link["right_family_view_id"] in view_ids
                for link in derived["links"]
            )
        assert run_result_ids[0] == run_result_ids[1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario,observations,result_count,routes,view_count,families,relations,zero_routes,max_trace",
    DEMOS,
)
async def test_curated_judge_demo_completes_with_its_presentation_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    observations: int,
    result_count: int,
    routes: int,
    view_count: int,
    families: set[str],
    relations: int,
    zero_routes: int,
    max_trace: int,
):
    if scenario == "dga_lexical":
        model = Path("artifacts/dga/local/DGA_M1_R1_SERIALIZED_MODEL.joblib").resolve()
        monkeypatch.setenv("EVIDENCEGATE_DGA_MODEL", str(model))

    async with client_for(tmp_path / f"{scenario}.db") as (client, service):
        started = await client.post("/replay", json={"scenario": scenario, "speed": 0})
        assert started.status_code == 202
        status = await service.wait_for_replay()
        assert status.state == "COMPLETED"
        assert status.records_read == status.observations_emitted == observations

        trace = (await client.get("/runtime/trace", params={"after": 0, "limit": 500})).json()[
            "events"
        ]
        assert len(trace) <= max_trace
        assert trace
        assert [event["sequence"] for event in trace] == list(
            range(trace[0]["sequence"], trace[-1]["sequence"] + 1)
        )
        observation_ids = {
            event["observation_id"] for event in trace if event["kind"] == "OBSERVATION_CREATED"
        }
        assert len(observation_ids) == observations
        canonical = [
            event["canonical_observation"]
            for event in trace
            if event["kind"] == "OBSERVATION_CREATED"
        ]
        assert len(canonical) == observations and all(item and item["facts"] for item in canonical)
        assert sum(event["kind"] == "ROUTED" for event in trace) == routes
        assert (
            observations
            - len({event["observation_id"] for event in trace if event["kind"] == "ROUTED"})
            == zero_routes
        )

        results = (await client.get("/results", params={"limit": 500})).json()["results"]
        assert all(result["source_observation_ids"] for result in results)
        assert all(set(result["source_observation_ids"]) <= observation_ids for result in results)
        assert len(results) == result_count
        result_ids = {result["result_id"] for result in results}

        derived = (
            await client.get(
                "/investigations", params=[("source_result_id", item) for item in result_ids]
            )
        ).json()
        views = derived["family_views"]
        assert len(views) == view_count
        assert families <= {view["family"] for view in views}
        view_ids = {view["family_view_id"] for view in views}
        links = derived["links"]
        assert all(
            link["left_family_view_id"] in view_ids and link["right_family_view_id"] in view_ids
            for link in links
        )
        if relations is not None:
            assert len(links) == relations

        if scenario == "ddos_one_way":
            assert any(result["result_type"] == "INSUFFICIENT_EVIDENCE" for result in results)
            assert any(
                "REVERSE_FACTS" in result["visibility_snapshot"]["unavailable"]
                for result in results
            )
        if scenario == "c2_recurrence":
            persistence = [event for event in trace if event["kind"] == "RESULT_PERSISTED"]
            recurrence = next(
                result
                for result in results
                if result["mechanism_id"] == "C2-M1" and result["result_type"] == "REVIEW_FINDING"
            )
            persisted = next(
                event for event in persistence if event["result_id"] == recurrence["result_id"]
            )
            source_sequences = [
                event["sequence"]
                for event in trace
                if event["kind"] == "OBSERVATION_CREATED"
                and event["observation_id"] in recurrence["source_observation_ids"]
            ]
            assert len(recurrence["source_observation_ids"]) >= 3
            assert persisted["sequence"] > max(source_sequences)
        if scenario == "dga_lexical":
            assert {result["mechanism_id"] for result in results} == {"DGA-A1-M1", "DNS-T1"}
        if scenario == "encrypted_tls_session":
            assert {result["mechanism_id"] for result in results} == {"ENC-A"}
            result = results[0]
            assert result["evidence"]["parsed_handshake_metadata"] == {
                "message_type": "ClientHello",
                "sni": "example.test",
            }
            assert "DECRYPTED_CONTENT" in result["claim_ceiling"]
