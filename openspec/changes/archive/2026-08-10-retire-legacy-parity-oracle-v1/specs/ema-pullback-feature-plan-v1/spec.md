## MODIFIED Requirements

### Requirement: No legacy production imports

Production code SHALL NOT import from `legacy_source` or BBB packages.

#### Scenario: Enforce the production dependency boundary

- **WHEN** architecture checks inspect production imports
- **THEN** no production module SHALL import `legacy_source` or BBB packages.
