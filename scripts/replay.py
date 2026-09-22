#!/usr/bin/env python3
"""Replay passive typed-NDJSON or raw-PCAP through the EvidenceGate runtime."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from evidencegate.ingest.replay import NdjsonReplaySource, ReplayRunner, validate_bundle
from evidencegate.ingest.pcap import PcapReplaySource, validate_pcap
from evidencegate.ingest.replay_schema import ReplayValidationError
from evidencegate.persistence.sqlite import SqliteWriter
from evidencegate.plugins.providers.registry import build_mvp_runtime_registration
from evidencegate.runtime.supervisor import RuntimeSupervisor


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--bundle", type=Path, help="typed-NDJSON replay bundle")
    source.add_argument("--pcap", type=Path, help="offline classic-PCAP capture")
    parser.add_argument("--manifest", type=Path, help="trusted sidecar for --pcap")
    parser.add_argument("--database", type=Path, default=Path("evidencegate.db"))
    parser.add_argument("--speed", type=float, default=0,
                        help="0 = as fast as possible; 1 = event-time speed")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.pcap is not None and args.manifest is None:
        parser.error("--manifest is required with --pcap")
    if args.bundle is not None and args.manifest is not None:
        parser.error("--manifest is only valid with --pcap")
    if args.validate_only:
        try:
            count = (
                await validate_pcap(args.pcap, args.manifest)
                if args.pcap is not None
                else await validate_bundle(args.bundle)
            )
        except ReplayValidationError as exc:
            parser.error(str(exc))
        print(f"valid source: {count} records/packets")
        return

    sqlite = SqliteWriter(args.database, Path("evidencegate/persistence/schema.sql"))
    sqlite.connect()
    persisted = 0

    async def write_result(result, target):
        nonlocal persisted
        await sqlite.write_result(result)
        persisted += 1

    registration = build_mvp_runtime_registration(datetime.now(timezone.utc))
    supervisor = RuntimeSupervisor(
        registration.plugins, registration.governances, write_result,
        reorder_policies=registration.reorder_policies,
    )
    try:
        try:
            input_source = (
                PcapReplaySource(args.pcap, args.manifest)
                if args.pcap is not None
                else NdjsonReplaySource(args.bundle)
            )
            summary = await ReplayRunner(
                input_source, supervisor, speed=args.speed,
            ).run()
        except ReplayValidationError as exc:
            parser.error(str(exc))
    finally:
        sqlite.close()
    print(
        f"records read={summary.records_read} "
        f"observations emitted={summary.observations_emitted} "
        f"control events={summary.control_events} "
        f"results persisted={persisted} "
        f"elapsed wall time={summary.elapsed_wall_seconds:.6f}s"
    )


if __name__ == "__main__":
    asyncio.run(main())
