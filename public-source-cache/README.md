# Public operator document cache

The scheduled `public-source-cache.yml` workflow reads public operator publications every six hours (00:23, 06:23, 12:23 and 18:23 UTC). GitHub may delay scheduled jobs. The application rejects copies more than 12 hours old and keeps direct operator lookup available.

The initial successful collection contains Cherkasy, Khmelnytskyi and Rivne documents. Zaporizhzhia collection has not yet succeeded; its direct app reader remains available. This is not a claim of complete regional address coverage.

The collector publishes generic decoded public PDF/XLSX/table data, original source URLs and SHA-256 values. Application address matching remains on the phone. User searches, EIC/account identifiers, credentials and manual corrections are not submitted to this pipeline. Application source remains in its private repository.

`manifest.json` names immutable content-hashed gzip assets in the `source-cache-data` release. Each operator is collected atomically. A failed collection can retain a still-valid previous operator bundle without changing its original fetched time. Unreferenced assets older than 48 hours are removed only after a new manifest has been published.

The Android client validates the allowed operator/source URLs, SHA-256, compressed/decompressed sizes, document structure and age before using a copy. Successful or authoritative direct results take priority; a copy is attempted after a source transport/format failure. Original source, scope and collection time are retained. A copied publication is labelled in the app.

The pipeline provides address-list caching, not a permanently running API or a cache of daily outage schedules. It uses standard public GitHub Actions runners; no paid plan or external database is configured.
