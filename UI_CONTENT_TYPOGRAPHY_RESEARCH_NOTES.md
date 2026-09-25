# UI-03 content and typography research notes

Research completed before the UI-03 implementation pass on 25 September 2026. The goal was to extract practical guidance for a dense, evidence-led operator console, not to copy another product's visual system.

## Sources and findings

- [USWDS typography](https://designsystem.digital.gov/components/typography/) and [USWDS font family tokens](https://designsystem.digital.gov/design-tokens/typesetting/font-family/) recommend familiar, readable interface type, a clear hierarchy, and restrained use of uppercase. Applied as a system sans stack for normal interface copy and monospace only for identifiers and structured values.
- [GOV.UK writing for user interfaces](https://www.gov.uk/service-manual/design/writing-for-user-interfaces) emphasizes short, direct labels and instructions. Applied to page descriptions, navigation, replay actions, and empty states.
- [GOV.UK guidance on designing with data](https://www.gov.uk/service-manual/design/designing-with-data-an-introduction) stresses consistent data formats, explicit context, and attention to quality and metadata. Applied by keeping source results, alerts, quality, and visibility distinct and consistently labeled.
- [Microsoft Fluent 2 typography](https://fluent2.microsoft.design/typography) frames type as a hierarchy of roles and levels. Applied to establish page, section, body, table, secondary, and technical text roles.
- [IBM Carbon data table guidance](https://carbondesignsystem.com/components/data-table/style/) supports a compact, scannable operational table. Applied to sentence-case headers, readable 13px rows, concise evidence, and a 40–48px row rhythm.
- [PlanetScale's product design process](https://planetscale.com/blog/how-product-design-works-at-planetscale) illustrates testing the real interaction rather than judging a static concept alone. Applied through page and inspector captures plus controlled scenario replays.

## Decisions applied

- Make current runtime and recent analyst alerts the first things visible on Overview; put the live path after the real alert output.
- Use a compact horizontal path with four evidence stages and two outcome branches. Keep the active result context in the flow and remove stage numbering, legends, and architecture slogans.
- Give each page one job: current attention, analyst review, observed or derived records, runtime readiness, or controlled replay.
- Use sentence case, familiar actions, and short descriptions. Keep exact technical state values available in detail views.
- Use a readable system sans face for ordinary UI text. Reserve the mono face for times where alignment helps and for lane, mechanism, source, result, model, policy, and hash identifiers.
- Keep measurements factual. “Quality issues” counts degraded records; it does not claim an aggregate sensor health score.
- Keep analyst presentation separate from scientific results, and keep score caveats and claim limits visible in the inspector.

## Research limits

These sources informed editorial and visual choices; they are not a usability study with government analysts. The product still needs final visual acceptance and judge-demo choreography from the named human owner.
