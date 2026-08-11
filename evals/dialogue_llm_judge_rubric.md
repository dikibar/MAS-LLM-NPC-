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

Runner mengirim seluruh dimensi dalam satu panggilan batch. Request skenario,
expected output, ContextOutput, dan DialogueOutput dipisahkan sebagai data tidak
tepercaya agar teks kandidat tidak dapat mengganti instruksi evaluator.

Berikan skor 1-5 untuk setiap dimensi:

1. `context_relevance`: dialog relevan dengan rekomendasi aktual dan tujuan aktif.
2. `faithfulness`: dialog tidak mengarang fakta budaya, koordinat, atau status yang tidak ada di context.
3. `navigation_clarity`: pemain jelas diarahkan ke tujuan berikutnya.
4. `persona_alignment`: gaya bicara hangat, ringkas, dan terasa seperti pemandu budaya bernama Arif.
5. `language_quality`: bahasa Indonesia natural, tidak kaku, dan tidak bercampur Inggris.
6. `ui_usefulness`: recommendation_dialogue dan recommendation_options membantu pemain memilih.
7. `technical_leak_safety`: tidak ada koordinat, tool name, backend token, NavMesh, atau istilah internal.

Output hanya JSON valid. Setiap dimensi wajib memiliki skor dan reasoning berbasis
bukti:

```json
{
  "scores": {
    "context_relevance": {
      "score": 1,
      "reasoning": "bukti spesifik"
    },
    "faithfulness": {
      "score": 1,
      "reasoning": "bukti spesifik"
    }
  }
}
```

## Ambang Batas Yang Disarankan

- Runner menghitung weighted overall score; model judge tidak menentukan kelulusannya sendiri.
- `passed=true` jika weighted overall score minimal 4.0.
- Tidak boleh pass jika `grounded_response_correctness < 4`.
- Tidak boleh pass jika `technical_leak_safety < 5`.
- Tidak boleh pass jika `faithfulness < 4`.
- Untuk mode `selection_confirmation`, tidak boleh pass jika selected option tidak disebut eksplisit.

## Catatan Validitas

LLM-as-a-judge berguna untuk aspek dialog yang subjektif, tetapi tetap memiliki bias. Untuk laporan skripsi, gunakan bersama:

- checks deterministic dari runner;
- sampling human judgement;
- analisis failure case.
- benchmark clean-vs-corrupted untuk memeriksa kemampuan diskriminatif judge;
- model judge yang berbeda dari model agent jika tersedia.
