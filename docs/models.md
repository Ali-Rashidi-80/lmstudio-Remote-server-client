# Models

**English** · [فارسی](fa/models.md)

Defaults locked for this deployment:

- **Chat:** `gemma-4-12b-agentic-fable5-composer2.5-v2-3.5x-tau2@q6_k`
- **Embedding:** `text-embedding-embeddinggemma-300m` (`EMBED_DIM=768`)

Alternates:

- Chat quality: `@q8_0` / throughput: `@q4_k_m` / light: `google/gemma-4-e4b`
- Embed alternate: `text-embedding-nomic-embed-text-v2`

Changing the embedding model requires a full reindex of RAG chunks (`embed_model_id` is stored per chunk).

Configure via Bridge env / admin settings; Worker must load matching LM Studio identifiers.
