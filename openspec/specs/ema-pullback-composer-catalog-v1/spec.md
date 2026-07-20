# EMA Pullback Composer Catalog v1

## Purpose

Define Strategy Engine as the authoritative source of EMA Pullback strategy component authoring metadata for research consumers.

## Requirements

### Requirement: Authoritative composer catalog

Strategy Engine SHALL be the authoritative owner of strategy component authoring metadata. The endpoint SHALL preserve the existing BBB Workbench `ComponentCatalog` response shape. Research consumers SHALL retrieve this catalog through the API instead of maintaining a local semantic copy.

#### Scenario: Retrieve EMA Pullback authoring metadata

- **WHEN** a consumer requests the EMA Pullback composer catalog
- **THEN** Strategy Engine SHALL return the BBB Workbench-compatible `ComponentCatalog` response shape
- **AND** the returned metadata SHALL be the authoritative source for research consumers.
