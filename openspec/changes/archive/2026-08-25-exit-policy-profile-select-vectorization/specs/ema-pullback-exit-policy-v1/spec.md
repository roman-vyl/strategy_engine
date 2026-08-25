## ADDED Requirements

### Requirement: Positional, fail-closed profile selection

Per-bar profile selection within exit-policy evaluation SHALL be positional (selecting by bar position/index-position, not by pandas label/index alignment): for bar `i`, the value SHALL come from the series belonging to the profile assigned to bar `i`, matched by position, not by any join/merge/reindex operation. An unrecognized profile name encountered during selection SHALL cause evaluation to fail (raise an error) rather than silently substitute a default or null value.

#### Scenario: Selection is positional, not label-aligned

- **WHEN** exit-policy evaluation selects a per-bar value according to the bar's assigned profile
- **THEN** the selected value SHALL be the value at that same bar position in the chosen profile's series
- **AND** the selection SHALL NOT depend on pandas index/label alignment between the profile assignment and the series being selected from.

#### Scenario: Unrecognized profile name fails closed

- **WHEN** a bar is assigned a profile name that does not correspond to any evaluated profile series
- **THEN** exit-policy evaluation SHALL raise an error
- **AND** SHALL NOT silently produce a null, default, or otherwise substituted value for that bar.
