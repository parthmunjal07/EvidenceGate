def test_package_structure():
    import evidencegate.domain
    import evidencegate.ingest
    import evidencegate.quality
    import evidencegate.governance
    import evidencegate.registry
    import evidencegate.routing
    import evidencegate.admission
    import evidencegate.runtime
    import evidencegate.plugins
    import evidencegate.results
    import evidencegate.persistence
    import evidencegate.api
    import evidencegate.metrics
    import evidencegate.ui

    # Asserting that the modules are loaded correctly
    assert evidencegate.domain is not None
    assert evidencegate.plugins is not None
