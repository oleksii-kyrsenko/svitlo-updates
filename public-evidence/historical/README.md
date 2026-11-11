# Historical public house snapshots

This reader imports reviewed immutable public address snapshots as optional historical suggestions. Every version-five record carries `historical:true`, `requiresConfirmation:true` and `method:"direct"`. It is neither an official confirmation nor evidence that the queue is still current. Older clients ignore the new version. The client must show the original publication date and warning and require user confirmation.

The initial reviewed source is the ProСвітло Poltava city snapshot. Configuration pins the repository, full Git commit, path, raw SHA256 and original publication commit/date. Only the uniquely matching city name, community, type and KATOTTG is selected; rural sampled inheritance and the separate GAV map are excluded. Exact source spellings remain intact. There are no configured house numbers or queue assignments.

Each record contains a lossless selected JSON street subtree in `quote`, explicit literal houses, a single GPV queue, immutable `sourceSnapshot` provenance and exact city context projection/pointers. It never invents a prose quotation. Grouping limits are 100 houses and 2,500 UTF-8 quote bytes. Before grouping, normalized same-house empty, unknown, multiple, malformed and conflicting claims veto positives. Street identity collisions abstain completely. A street with an unsupported compound/qualified house selector abstains completely because its scope cannot safely be assumed disjoint. Selectors are never split or expanded. Exact suffixes and slash houses are supported; Latin and Cyrillic remain distinct.

The original publication can be at most 180 days old. `publishedAt` equals `sourceSnapshot.publishedAt` and never changes on a reread. A successful verified read updates only observation/cache times; display eligibility ends no later than seven days after that read and 180 days after the publication. The client additionally requires an observation no older than 36 hours. Cache expiry is not a source validity period. Failed reads never renew a previous record.

The shared six-hour workflow merges with the existing public-evidence manifest under the same writer concurrency group. Successful reads replace the same source family (operator, region, city KATOTTG, repository and path), including an earlier Git pin. Other cities/readers remain intact. A mixed run retains a failed family's old timestamps. A wholly unsuccessful run leaves the manifest unchanged and writes a failure report. Whole-manifest limits are 10,000 grouped records and 2,000,000 serialized bytes; exceeding either fails without truncation. All public writers use compact serialization so the actual bytes match this limit.

The revision monitor compares the pinned publication's Git blob identity with upstream metadata. Changed bytes become a review lead; they do not automatically replace the reviewed pin or borrow a new publication date. `sources.json` contains the original claim publication date, not the latest repository/version timestamp. New source formats or dates need grounding and review.

Local checks and a draft import:

```sh
python public-evidence/qa/test_historical.py
python public-evidence/historical/importer.py --output /tmp/historical-draft.json --report /tmp/historical-report.json --proof-dir /tmp/historical-proof --monitor
```

Omitting `--output` writes the shared manifest. For rollback, set this reader's `enabled` to false and run it: only historical-directory records are removed; the shared manifest's global switch and other readers' records remain unchanged. Merely removing a configuration entry does not immediately revoke an existing snapshot; explicitly disable the reader for immediate rollback, or let its original observation/cache deadlines withdraw it. Restore reviewed configuration to re-enable.
