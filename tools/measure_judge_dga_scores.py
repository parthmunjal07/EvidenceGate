"""Run every curated DGA demo name through the verified DGA-A1/M1-R1 runtime."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
from pathlib import Path

import httpx

from evidencegate.api.app import create_app


ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "artifacts" / "dga" / "local" / "DGA_M1_R1_SERIALIZED_MODEL.joblib"
EXPECTED_SHA256 = "39da209d2cfd869dd284e10b8a07adc04826c95146712cc6854a69b9873890df"
OUTPUT = ROOT / "evidencegate" / "demo_data" / "dga_dns_v2" / "model_measurements.json"


async def measure() -> dict[str, object]:
    model = Path(os.environ.get("EVIDENCEGATE_DGA_MODEL", str(MODEL))).resolve()
    digest = hashlib.sha256(model.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise SystemExit(f"Model SHA-256 mismatch: expected {EXPECTED_SHA256}, got {digest}")
    os.environ["EVIDENCEGATE_DGA_MODEL"] = str(model)
    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="evidencegate-dga-measure-") as temporary:
        app = create_app(Path(temporary) / "measure.db")
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://measure",
            ) as client:
                response = await client.post(
                    "/replay", json={"scenario": "dga_lexical", "speed": 0}
                )
                response.raise_for_status()
                status = await app.state.service.wait_for_replay()
                if status.state != "COMPLETED":
                    raise SystemExit(f"Replay did not complete: {status.state}")
                trace = (
                    await client.get("/runtime/trace", params={"after": 0, "limit": 500})
                ).json()["events"]
                names = {
                    event["observation_id"]: event["canonical_observation"]["facts"].get(
                        "qname_rendered"
                    )
                    for event in trace
                    if event["kind"] == "OBSERVATION_CREATED"
                }
                results = (await client.get("/results", params={"limit": 100})).json()["results"]
                dga = [item for item in results if item["mechanism_id"] == "DGA-A1-M1"]
                if len(dga) != 6:
                    raise SystemExit(f"Expected six DGA results; received {len(dga)}")
                for result in dga:
                    observation_id = result["source_observation_ids"][0]
                    rows.append(
                        {
                            "source_position": next(
                                event["canonical_observation"]["source_position"]
                                for event in trace
                                if event.get("observation_id") == observation_id
                                and event["kind"] == "OBSERVATION_CREATED"
                            ),
                            "qname": names[observation_id],
                            "model_input_domain": result["evidence"]
                            .get("representation", {})
                            .get("model_input"),
                            "dga_labelled_lexical_resemblance_score": result["evidence"][
                                "dga_labelled_lexical_resemblance_score"
                            ],
                            "model_id": "DGA-A1-M1-R1",
                        }
                    )
    rows.sort(key=lambda item: int(item["source_position"]))
    return {
        "measurement_kind": "controlled_demo_model_inference",
        "scientific_evaluation_claim": False,
        "model_filename": MODEL.name,
        "model_bytes": MODEL.stat().st_size,
        "model_sha256": digest,
        "model_id": "DGA-A1-M1-R1",
        "rows": rows,
    }


def main() -> None:
    measurement = asyncio.run(measure())
    OUTPUT.write_text(json.dumps(measurement, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"Recorded {len(measurement['rows'])} actual DGA-A1/M1-R1 scores in {OUTPUT.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
