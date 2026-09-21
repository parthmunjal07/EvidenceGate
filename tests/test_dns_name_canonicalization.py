from dataclasses import replace
from datetime import datetime, timezone

import pytest

from evidencegate.domain.enums import DirectionBasis, SourceKind, TimestampSemantics, WireDirection
from evidencegate.domain.payloads import DNSObservation
from evidencegate.ingest.builders import DNSCanonicalBuilder
from evidencegate.ingest.dns_name import DNS_NAME_REPRESENTATION_V1, canonicalize_dns_name
from evidencegate.ingest.source import RawSourceRecord, SourceManifest


NOW = datetime(2026, 9, 21, tzinfo=timezone.utc)


def test_case_terminal_dot_labels_xn_and_unknown_suffix_are_factual_and_deterministic():
    rendered = "A1.Xn--Exmple-Cua.UNKNOWN."
    first = canonicalize_dns_name(rendered)
    assert first == canonicalize_dns_name(rendered)
    assert first.succeeded
    assert first.rendered == rendered
    assert first.canonical == "a1.xn--exmple-cua.unknown"
    assert first.labels == ("a1", "xn--exmple-cua", "unknown")
    assert first.representation_version == DNS_NAME_REPRESENTATION_V1
    assert canonicalize_dns_name("Example.COM").canonical == "example.com"


def test_no_idna_conversion_or_psl_requirement():
    value = canonicalize_dns_name("Bücher.XN--P1AI")
    assert value.canonical == "bücher.xn--p1ai"
    assert value.labels == ("bücher", "xn--p1ai")


@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("", "EMPTY_NAME"),
        (".", "ROOT_NAME_NOT_APPLICABLE"),
        ("foo..example.com", "EMPTY_LABEL"),
        ("example.com..", "EMPTY_LABEL"),
        (" example.com", "WHITESPACE_IN_NAME"),
        ("example.com\t", "WHITESPACE_IN_NAME"),
    ],
)
def test_malformed_and_root_names_are_not_repaired(value, reason):
    result = canonicalize_dns_name(value)
    assert not result.succeeded
    assert result.rendered == value
    assert result.canonical is None
    assert result.labels is None
    assert result.representation_version is None
    assert result.failure_reason == reason


def test_non_string_is_rejected_without_coercion():
    with pytest.raises(TypeError, match="parser-rendered string"):
        canonicalize_dns_name(123)  # type: ignore[arg-type]


def test_builder_preserves_rendered_failure_but_only_marks_successful_derivations_present():
    manifest = SourceManifest(
        source_id="dns", source_kind=SourceKind.PCAP, capture_start=None, capture_end=None,
        timestamp_semantics=TimestampSemantics.SOURCE_EVENT_TIME,
        input_observation_contract="dns_v1", direction_basis=DirectionBasis.CAPTURE_INTERFACE,
        wire_direction=WireDirection.FORWARD,
    )
    base = DNSObservation("flow", True, 1, "Example.COM.", None, None, None, None, "UDP", False)
    builder = DNSCanonicalBuilder()
    valid = builder.canonicalize(
        RawSourceRecord(base, NOW, 1), manifest, "quality", NOW, {"qname"},
        clear_dns_fields=True,
    )
    assert valid.typed_payload.qname_rendered == "Example.COM."
    assert valid.typed_payload.qname_canonical == "example.com"
    assert {"qname_canonical", "labels", "representation_version"} <= valid.present_fields

    malformed = builder.canonicalize(
        RawSourceRecord(replace(base, qname="foo..example.com"), NOW, 2),
        manifest, "quality", NOW, {"qname"}, clear_dns_fields=True,
    )
    assert malformed.typed_payload.qname_rendered == "foo..example.com"
    assert malformed.typed_payload.canonicalization_failure_reason == "EMPTY_LABEL"
    assert "canonicalization_failure_reason" in malformed.present_fields
    assert not {"qname_canonical", "labels", "representation_version"} & malformed.present_fields

    with pytest.raises(ValueError, match="observed qname"):
        builder.canonicalize(
            RawSourceRecord(replace(base, qname=None), NOW, 3), manifest, "quality", NOW,
            set(), clear_dns_fields=True,
        )
    with pytest.raises(TypeError, match="parser-rendered string"):
        builder.canonicalize(
            RawSourceRecord(replace(base, qname=object()), NOW, 4), manifest, "quality", NOW,
            {"qname"}, clear_dns_fields=True,
        )
