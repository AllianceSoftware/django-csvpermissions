# CHANGELOG

<!--
IMPORTANT: the build script extracts the most recent versino from this file
so make sure you follow the template
-->

<!-- Use the poetry changelog a template for each release:
## 1.2.3 2020-01-01

### Breaking Changes

* An Item

### Added

* An Item

### Changed

* An Item

### Fixed

* An Item

-->

## 0.3.0 2026-01-20

- Add `user_type` to `UnresolvedEvaluator`

## 0.2.0 2021-09-13

### Added

- Add documentation
- Add support for django 3.2
- Add explicit support for python 3.6-3.9
- Add `CSV_PERMISSIONS_STRICT` setting
- Add support for multiple CSV files; add `CSV_PERMISSIONS_PATHS` setting
- Add `CSV_PERMISSIONS_RESOLVE_EVALUATORS`
- Add `CSV_PERMISSIONS_GET_USER_TYPE`
- Add `;` as another allowable comment line prefix

### Changed

- `CSV_PERMISSIONS_RESOLVE_RULE_NAME` setting deprecated in favour of `CSV_PERMISSIONS_RESOLVE_PERM_NAME`

## 0.1.0 2020-11-25

### Added

- Alpha version
