# Agent Evaluation

Folder ini berisi evaluasi offline untuk sistem multi-agent VR:

- `scenarios.json`: kumpulan skenario input Unity dan pilihan rekomendasi.
- `run_agent_evaluation.py`: runner evaluasi deterministic/rule-based.

Jalankan dari root project:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py
```

Evaluasi per agent:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent context
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent dialogue
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent e2e
```

Output JSON untuk analisis lanjutan:

```bash
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --json
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent context --json
env USE_MOCK_MODEL=true PYTHONPATH=src .venv/bin/python evals/run_agent_evaluation.py --agent dialogue --json
```

## Metrik Utama

Context Agent:

- `schema_valid`: output valid sesuai `ContextOutput`.
- `timestamp_matches_request` dan `scene_matches_request`: output grounded ke request Unity.
- `no_visited_sites_recommended`: objek `visited=true` tidak boleh muncul.
- `ranking_exact_match`: urutan rekomendasi sama dengan ranking Euclidean distance backend.
- `nav_target_matches_rank_1`: target NavMesh sama dengan rekomendasi rank-1.
- `Precision@3`, `Recall@3`, `MRR`, `NDCG@3`: kualitas ranking top-3.

Dialogue Agent:

- `schema_valid`: output valid sesuai `DialogueOutput`.
- `options_match_context_order`: opsi UI sama dengan rekomendasi context.
- `subtitle_max_15_words`: subtitle sesuai constraint HUD.
- `no_internal_tokens_or_coordinates`: teks user-facing tidak membocorkan koordinat, tool, backend, atau NavMesh.
- `primary_option_mentioned`: dialog/subtitle mengarahkan pemain ke rank-1.
- `selected_option_mentioned`: mode selection wajib menyebut pilihan pemain.

End-to-end:

- `end_to_end_success`: request valid, context valid, dialogue valid, dan selection behavior sesuai skenario.
