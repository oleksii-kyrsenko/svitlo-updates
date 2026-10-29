# Free Qwen / DeepSeek comparison, 29 October 2026

An isolated research test on the existing 96 national QA scenarios plus a separate Kyiv control. Three original scenarios lack a complete original address and remain in the denominator. This does not modify production models, evidence or the Android app.

Both pinned Q4_K_M models receive identical source-only frozen packets, the same prompt and JSON schema, temperature 0, seed 42, 768 total output tokens, a 192 token reasoning budget, 6144 context and four CPU threads. Four Qwen and sixteen DeepSeek standard public Ubuntu 24.04 Actions shards; equal per-case settings, up to twenty concurrent jobs. The DeepSeek model is **DeepSeek-R1-Distill-Qwen-7B**, not the paid DeepSeek API or the full R1 model. Models have no web tools during inference.

Inputs contain public test addresses and excerpts from publicly accessible source documents, saved browser pages and official APIs. Source text is untrusted. HTML scripts/forms and sensitive JSON keys have been stripped. Full original records are retained where practical; general lexical retrieval selects document excerpts and can miss relevant rows. Official Sumy responses use the public website client decoder. Model outputs are hypotheses requiring independent address, period and citation checks. Archived expected queues and previous research conclusions are excluded from model inputs and kept outside this directory.

Compare number correctness, quote validity, unsupported claims, abstentions, latency and token use separately. A model-only replay cannot establish end-to-end app coverage or a production replacement decision. Shards may run on different physical CPU types; retain hardware manifests and do not treat wall time as a precise hardware-controlled speed comparison.

Run locally: `python qa/model-comparison-96/run_benchmark.py qwen 0 4` (downloads pinned model/runtime files to a temporary directory). Public artifacts retain manifests and all actual case responses. No paid API, third-party account or API key is used.
