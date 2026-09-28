"""Shared factual DNS name representation for clear-DNS observations."""

from dataclasses import dataclass


DNS_NAME_REPRESENTATION_V1 = "DNS_NAME_REPRESENTATION_V1"


@dataclass(frozen=True, slots=True)
class DNSNameCanonicalization:
    """Immutable result; failures retain rendered evidence and an explicit reason."""

    rendered: str | None
    canonical: str | None = None
    labels: tuple[str, ...] | None = None
    representation_version: str | None = None
    failure_reason: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.failure_reason is None


def canonicalize_dns_name(rendered_qname: str) -> DNSNameCanonicalization:
    """Apply C3-DEC-20260921-DNS-T1-CANON-V1 without repair or IDNA/PSL work."""
    if not isinstance(rendered_qname, str):
        raise TypeError("rendered_qname must be a parser-rendered string")
    if rendered_qname == ".":
        return DNSNameCanonicalization(rendered_qname, failure_reason="ROOT_NAME_NOT_APPLICABLE")
    if not rendered_qname:
        return DNSNameCanonicalization(rendered_qname, failure_reason="EMPTY_NAME")
    if any(character.isspace() for character in rendered_qname):
        return DNSNameCanonicalization(rendered_qname, failure_reason="WHITESPACE_IN_NAME")

    # lower() is Unicode's locale-independent mapping. No IDNA conversion occurs.
    canonical = rendered_qname.lower()
    if canonical.endswith("."):
        canonical = canonical[:-1]
    if not canonical:
        return DNSNameCanonicalization(rendered_qname, failure_reason="EMPTY_NAME")
    labels = tuple(canonical.split("."))
    if any(label == "" for label in labels):
        return DNSNameCanonicalization(rendered_qname, failure_reason="EMPTY_LABEL")
    return DNSNameCanonicalization(
        rendered=rendered_qname,
        canonical=canonical,
        labels=labels,
        representation_version=DNS_NAME_REPRESENTATION_V1,
    )
