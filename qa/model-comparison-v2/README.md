# Compact extraction prompt comparison

Same frozen original 96 QA scenarios plus Kyiv, same public source-only packets as diagnostic run 40837093030. Expected answers remain outside model inputs. Production is unchanged.

The initial verbose prompt failed a simple synthetic positive control for Qwen. This follow-up uses a compact extraction instruction and context 8192 for BOTH models on ALL packets. No address-to-queue facts or expected real-address labels are added. All responses still require independent source, scope, exact address and citation validation: short prompts can guess on an absent source or a neighboring house, as the synthetic controls explicitly demonstrate. Raw model matches are not automatically confirmed coverage.

Qwen2.5-1.5B-Instruct Q4_K_M versus DeepSeek-R1-Distill-Qwen-7B Q4_K_M; pinned model and llama.cpp locks remain in ../model-comparison-96/locks.json. Temperature 0, seed 42, output 768, reasoning budget 192, four CPU threads. Four Qwen shards and sixteen DeepSeek shards, standard free public Ubuntu 24.04 runners. CPU models vary; preserve per-job manifests.
