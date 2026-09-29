## MODIFIED Requirements

### Requirement: Authoritative composer catalog

Strategy Engine SHALL be the authoritative owner of strategy component
authoring metadata. The endpoint SHALL preserve the existing BBB
Workbench `ComponentCatalog` response shape except that its strategy
selector field SHALL be named `strategy_id`, not `family`. Research
consumers SHALL retrieve this catalog through the API instead of
maintaining a local semantic copy.

#### Scenario: Retrieve EMA Pullback authoring metadata

- **WHEN** a consumer requests the EMA Pullback composer catalog
- **THEN** Strategy Engine SHALL return the BBB Workbench-compatible
  `ComponentCatalog` response shape with `strategy_id` as its selector
  field
- **AND** the returned metadata SHALL be the authoritative source for
  research consumers.

#### Scenario: family is not present

- **WHEN** a composer-catalog response is inspected
- **THEN** it SHALL NOT contain a `family` field
- **AND** SHALL NOT contain both `family` and `strategy_id` as aliases
  of each other.
