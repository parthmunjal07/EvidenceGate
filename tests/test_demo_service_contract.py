"""Curated demo service labels must retain their declared identity basis."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALID_SERVICE_BASES = {"SOURCE_DECLARED_ROLE", "POLICY_DECLARED_ROLE"}


def test_curated_network_demo_roles_have_explicit_service_basis():
    assets = ROOT / "evidencegate" / "demo_data"
    service_pairs = []
    for records_path in sorted(assets.glob("*/records.ndjson")):
        for line_number, line in enumerate(
            records_path.read_text(encoding="utf-8").splitlines(), 1
        ):
            record = json.loads(line)
            payload = record.get("payload", {})
            for role in record.get("role_assignments", []):
                if role.get("role") != "service_id":
                    continue
                label = role.get("identifier", "").removeprefix("service/")
                basis = role.get("basis")
                assert label and label.lower() not in {"unknown", "none"}, (
                    f"{records_path}:{line_number} has an empty service label"
                )
                assert basis in VALID_SERVICE_BASES, (
                    f"{records_path}:{line_number} service {label} has no known basis"
                )
                service_pairs.append(
                    (
                        records_path.parent.name,
                        label,
                        payload.get("protocol"),
                        payload.get("dst_port"),
                        basis,
                    )
                )

    pcap_manifest_path = assets / "raw_pcap_ddos_recon_v2" / "manifest.json"
    manifest = json.loads(pcap_manifest_path.read_text(encoding="utf-8"))
    for service in manifest["services"]:
        label = service["service_id"].removeprefix("service/")
        assert service.get("basis") == "POLICY_DECLARED_ROLE", (
            f"PCAP service {label} must state its configured identity basis"
        )
        assert service["port"] in range(1, 65536)
        assert service["protocol"] in {1, 6, 17}
        service_pairs.append(
            (
                "raw_pcap_ddos_recon_v2",
                label,
                service["protocol"],
                service["port"],
                service["basis"],
            )
        )

    assert service_pairs
    assert any(
        scenario == "mixed_ddos_recon_v2" and port == 8443 and label == "tcp-8443"
        for scenario, label, _, port, _ in service_pairs
    )
