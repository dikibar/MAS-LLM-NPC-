# Dialogue Agent LLM-as-a-Judge Rubric

Gunakan rubrik ini ketika ingin mengevaluasi kualitas natural language Dialogue Agent dengan evaluator LLM yang lebih kuat. Rubrik ini bersifat pelengkap untuk checks deterministic di `run_agent_evaluation.py`, bukan pengganti.

## Input Untuk Evaluator

```json
{
  "context": {
    "timestamp": "...",
    "scene": "...",
    "user_action": "...",
    "recommendations": [
      {"rank": 1, "id": "...", "name": "...", "cultural_position": "..."}
    ],
    "nav_target": "..."
  },
  "dialogue": {
    "spoken_output": "...",
    "subtitle_output": "...",
    "recommendation_dialogue": "...",
    "recommendation_options": ["..."]
  },
  "mode": "recommendation_synthesis | selection_confirmation",
  "selected_option": "optional"
}
```

## Prompt Evaluator

Anda adalah evaluator independen untuk Dialogue Agent dalam sistem VR museum budaya.
Nilai kualitas output berdasarkan context yang diberikan. Jangan menilai berdasarkan pengetahuan eksternal. Jika detail budaya tidak ada di context, output yang tidak mengarang detail harus diberi nilai lebih baik.

Berikan skor 1-5 untuk setiap dimensi:

1. `context_relevance`: dialog relevan dengan rekomendasi aktual dan tujuan aktif.
2. `faithfulness`: dialog tidak mengarang fakta budaya, koordinat, atau status yang tidak ada di context.
3. `navigation_clarity`: pemain jelas diarahkan ke tujuan berikutnya.
4. `persona_alignment`: gaya bicara hangat, ringkas, dan terasa seperti pemandu budaya bernama Arif.
5. `language_quality`: bahasa Indonesia natural, tidak kaku, dan tidak bercampur Inggris.
6. `ui_usefulness`: recommendation_dialogue dan recommendation_options membantu pemain memilih.
7. `technical_leak_safety`: tidak ada koordinat, tool name, backend token, NavMesh, atau istilah internal.

Output hanya JSON valid:

```json
{
  "scores": {
    "context_relevance": 1,
    "faithfulness": 1,
    "navigation_clarity": 1,
    "persona_alignment": 1,
    "language_quality": 1,
    "ui_usefulness": 1,
    "technical_leak_safety": 1
  },
  "overall_score": 1,
  "passed": false,
  "failure_reasons": ["..."],
  "recommendation": "..."
}
```

## Ambang Batas Yang Disarankan

- `passed=true` jika `overall_score >= 4.0`.
- Tidak boleh pass jika `technical_leak_safety < 5`.
- Tidak boleh pass jika `faithfulness < 4`.
- Untuk mode `selection_confirmation`, tidak boleh pass jika selected option tidak disebut eksplisit.

## Catatan Validitas

LLM-as-a-judge berguna untuk aspek dialog yang subjektif, tetapi tetap memiliki bias. Untuk laporan skripsi, gunakan bersama:

- checks deterministic dari runner;
- sampling human judgement;
- analisis failure case.
