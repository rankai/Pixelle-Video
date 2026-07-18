# UX-0 contract fixtures

These fixtures are synthetic and contain no production media or private brand
data. They are consumed by the UX-0 schema, migration dry-run, upload-policy
and stable-cursor tests.

The 1000-item performance dataset is deterministic: tests expand
`asset_library_1000.seed.json` with `count=1000`, so the fixture stays reviewable
without checking in a generated wall of JSON.
