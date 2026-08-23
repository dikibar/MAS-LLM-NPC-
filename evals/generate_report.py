"""Generate a plain-language Markdown report from evaluation result JSON files.

Reads the JSON output(s) produced by run_agent_evaluation.py (main run,
optional UQ controlled-failure run, optional judge validation benchmark) and
writes a single explained report to evals/results/report_<timestamp>.md,
ready to be lifted into the thesis write-up.

Usage:
    PYTHONPATH=src .venv/bin/python evals/generate_report.py
    PYTHONPATH=src .venv/bin/python evals/generate_report.py \
        --main evals/results/eval_results_20260725_101500.json \
        --uq-failure evals/results/eval_results_20260725_102200.json \
        --judge-validation evals/results/judge_validation_20260725_103000.json
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

EVALS_DIR = Path(__file__).parent
RESULTS_DIR = EVALS_DIR / "results"
FIGURES_DIR = EVALS_DIR / "figures"

DIMENSION_EXPLANATIONS = {
    "grounded_response_correctness": (
        "Apakah dialog benar secara faktual dan konsisten dengan context "
        "(rekomendasi, ranking, dan target yang diberikan backend)."
    ),
    "context_relevance": "Dialog relevan dengan rekomendasi aktual dan tujuan pemain saat itu.",
    "faithfulness": "Dialog tidak mengarang fakta budaya, koordinat, atau status yang tidak ada di context.",
    "navigation_clarity": "Pemain jelas diarahkan ke tujuan berikutnya.",
    "persona_alignment": "Gaya bicara hangat, ringkas, dan konsisten sebagai pemandu budaya (Arif).",
    "technical_leak_safety": "Tidak ada koordinat, nama tool, token backend, NavMesh, atau istilah internal yang bocor ke pemain.",
}

IR_EXPLANATIONS = {
    "precision_at_3": "Dari 3 rekomendasi teratas yang ditampilkan, berapa proporsi yang benar-benar relevan.",
    "recall_at_3": "Dari seluruh objek relevan, berapa proporsi yang berhasil masuk ke 3 rekomendasi teratas.",
    "mrr": "Mean Reciprocal Rank - seberapa tinggi posisi rekomendasi relevan pertama muncul (1.0 = selalu di posisi 1).",
    "ndcg_at_3": "Normalized Discounted Cumulative Gain@3 - kualitas urutan ranking, menghukum rekomendasi relevan yang muncul di posisi rendah.",
}


def latest_file(pattern: str) -> Path | None:
    matches = sorted(RESULTS_DIR.glob(pattern), key=lambda path: path.stat().st_mtime)
    return matches[-1] if matches else None


def latest_file_with_key(pattern: str, key: str) -> Path | None:
    matches = sorted(RESULTS_DIR.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in matches:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if payload.get("summary", {}).get(key):
            return path
    return None


def load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "Ya" if value else "Tidak"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def pct(value: Any) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2%}"


def section_executive_summary(lines: list[str], summary: dict[str, Any]) -> None:
    lines.append("## 1. Ringkasan Eksekutif\n")
    lines.append(
        "`overall_pass_rate` menghitung proporsi skenario yang lulus **seluruh** kriteria "
        "(deterministic checks + LLM judge jika diwajibkan). `check_pass_rate` menghitung "
        "proporsi butir deterministic check individual yang lulus, digabung dari semua skenario.\n"
    )
    lines.append("| Metrik | Nilai |")
    lines.append("|---|---|")
    lines.append(f"| Total skenario | {summary.get('total_scenarios', 'N/A')} |")
    lines.append(f"| Skenario lulus penuh | {summary.get('passed', 'N/A')} |")
    lines.append(f"| Overall pass rate | {pct(summary.get('overall_pass_rate'))} |")
    lines.append(f"| Check pass rate (deterministic) | {pct(summary.get('check_pass_rate'))} |")
    if summary.get("faithfulness_avg") is not None:
        lines.append(f"| Faithfulness rata-rata (heuristik nama entitas) | {fmt(summary.get('faithfulness_avg'))} |")
    lines.append(f"| Model agent | {summary.get('agent_model', 'N/A')} |")
    lines.append(f"| Model judge | {summary.get('judge_model', 'N/A')} |")
    lines.append(f"| Waktu run (UTC) | {summary.get('timestamp', 'N/A')} |")
    lines.append("")
    if summary.get("judge_model_warning"):
        lines.append(f"> **Peringatan:** {summary['judge_model_warning']}\n")


def section_ir_metrics(lines: list[str], summary: dict[str, Any]) -> None:
    ir_summary = summary.get("ir_summary") or {}
    if not ir_summary:
        return
    lines.append("## 2. Metrik Information Retrieval (Kualitas Ranking Rekomendasi)\n")
    lines.append(
        "Metrik ini membandingkan ranking rekomendasi Context Agent terhadap ranking "
        "referensi (jarak Euclidean dari backend), bukan penilaian subjektif.\n"
    )
    lines.append("| Metrik | Nilai | Penjelasan |")
    lines.append("|---|---|---|")
    for metric, value in ir_summary.items():
        lines.append(f"| {metric} | {fmt(value)} | {IR_EXPLANATIONS.get(metric, '')} |")
    lines.append("")


def section_llm_judge(lines: list[str], summary: dict[str, Any]) -> None:
    judge_summary = summary.get("judge_summary") or {}
    judge_execution = summary.get("judge_execution") or {}
    if not judge_summary and not judge_execution.get("required_scenarios"):
        return
    lines.append("## 3. LLM-as-a-Judge (Kualitas Dialog Agent)\n")
    lines.append(
        "Judge menilai `spoken_output`, `subtitle_output`, `recommendation_dialogue`, dan "
        "`recommendation_options` dari Dialogue Agent, dengan request dan expected output "
        "sebagai referensi grounding. Context Agent tidak pernah dinilai judge; kualitasnya "
        "diverifikasi lewat deterministic checks dan UQ metrics (bagian 4).\n"
    )
    lines.append("**Cakupan eksekusi judge:**\n")
    lines.append("| Metrik | Nilai |")
    lines.append("|---|---|")
    lines.append(
        f"| Skenario wajib dinilai / berhasil | "
        f"{judge_execution.get('required_scenarios', 'N/A')} / "
        f"{judge_execution.get('successful_scenarios', 'N/A')} |"
    )
    lines.append(f"| Scenario coverage | {pct(judge_execution.get('scenario_coverage'))} |")
    lines.append(f"| Dimension coverage | {pct(judge_execution.get('dimension_coverage'))} |")
    lines.append(f"| Assessment pass rate | {pct(judge_execution.get('assessment_pass_rate'))} |")
    lines.append(f"| Overall score rata-rata | {fmt(judge_execution.get('overall_score_mean'), 2)} |")
    status_counts = judge_execution.get("status_counts") or {}
    if status_counts:
        lines.append(
            f"| Status (ok/skipped/error) | "
            f"{status_counts.get('ok', 0)} / {status_counts.get('skipped', 0)} / {status_counts.get('error', 0)} |"
        )
    lines.append("")

    if judge_summary:
        lines.append("**Skor per dimensi (skala 1-5):**\n")
        lines.append("| Dimensi | Mean ± Std | n | Pass rate | Threshold | Yang dinilai |")
        lines.append("|---|---|---|---|---|---|")
        for dimension, stats in judge_summary.items():
            thresholds = ", ".join(fmt(t, 1) for t in stats.get("thresholds", []))
            explanation = DIMENSION_EXPLANATIONS.get(dimension, "")
            lines.append(
                f"| {dimension} | {fmt(stats.get('mean'), 2)} ± {fmt(stats.get('std'), 2)} | "
                f"{stats.get('n', 0)} | {pct(stats.get('pass_rate'))} | {thresholds} | {explanation} |"
            )
        lines.append("")
        lines.append(
            "Kelulusan judge per skenario mensyaratkan weighted overall score ≥ 4.0, "
            "`grounded_response_correctness` ≥ 4, `faithfulness` ≥ 4, dan "
            "`technical_leak_safety` = 5 (lihat `evals/dialogue_llm_judge_rubric.md`).\n"
        )

    agreement = summary.get("human_judge_agreement") or {}
    if agreement.get("status") == "available":
        lines.append("**Kalibrasi dengan penilai manusia:**\n")
        lines.append("| Metrik | Nilai |")
        lines.append("|---|---|")
        lines.append(f"| Sampel | {agreement.get('sample_count', 'N/A')} |")
        lines.append(f"| Exact agreement | {pct(agreement.get('exact_agreement'))} |")
        lines.append(f"| Within-one agreement | {pct(agreement.get('within_one_agreement'))} |")
        lines.append(f"| Quadratic weighted kappa | {fmt(agreement.get('quadratic_weighted_kappa'), 2)} |")
        lines.append(f"| Korelasi Spearman | {fmt(agreement.get('spearman_correlation'), 2)} |")
        lines.append("")
    elif agreement.get("status") == "not_provided":
        lines.append(
            "> Kalibrasi manusia belum dijalankan. Tambahkan `--human-annotations "
            "evals/human_annotations.json` (lihat `human_annotations.example.json`) untuk "
            "menghitung agreement dengan penilai manusia.\n"
        )


def _uq_metric_block(lines: list[str], agent_label: str, metrics: dict[str, Any]) -> None:
    lines.append(f"**{agent_label}**\n")
    if metrics.get("status") == "unavailable":
        lines.append(f"> {metrics.get('note', 'Data UDeg tidak tersedia.')}\n")
        return
    lines.append("| Metrik | Nilai | Penjelasan |")
    lines.append("|---|---|---|")
    lines.append(f"| Sample count | {metrics.get('sample_count', 0)} | Jumlah output yang punya nilai UDeg. |")
    lines.append(
        f"| Correct / Error | {metrics.get('correct_count', 0)} / {metrics.get('error_count', 0)} | "
        "Jumlah output yang lulus/tidak lulus deterministic correctness checks. |"
    )
    lines.append(
        f"| Accuracy at zero rejection | {fmt(metrics.get('accuracy_at_zero_rejection'))} | "
        "Akurasi jika seluruh output diterima tanpa penolakan. |"
    )
    lines.append(
        f"| AUARC | {fmt(metrics.get('auarc'))} | "
        "Area under accuracy-rejection curve; 1.0 = menolak output paling tidak pasti selalu meningkatkan akurasi. |"
    )
    auroc = metrics.get("error_detection_auroc")
    if auroc is not None:
        lines.append(
            f"| Error-detection AUROC | {fmt(auroc)} | "
            "Kemampuan UDeg memisahkan output salah dari output benar (0.5 = acak, 1.0 = sempurna). |"
        )
    else:
        lines.append("| Error-detection AUROC | N/A | Tidak ada variasi error pada sampel ini (semua benar/semua salah). |")
    if metrics.get("mean_cdeg_correct") is not None:
        lines.append(
            f"| Mean CDeg (correct) | {fmt(metrics.get('mean_cdeg_correct'))} | "
            "Rata-rata confidence degree (CDeg) dari sampel yang dipilih agent pada output yang lulus correctness checks. "
            "Semakin tinggi = sampel-sampel yang dibangkitkan semakin konsisten satu sama lain. |"
        )
        lines.append(f"| Mean CDeg (incorrect) | {fmt(metrics.get('mean_cdeg_incorrect'))} | |")
    if metrics.get("mean_udeg_correct") is not None:
        lines.append(
            f"| Mean UDeg (correct) | {fmt(metrics.get('mean_udeg_correct'))} | "
            "UDeg = 1 - rata-rata CDeg seluruh sampel; baris ini adalah pasangan komplemen dari Mean CDeg di atas. |"
        )
        lines.append(f"| Mean UDeg (incorrect) | {fmt(metrics.get('mean_udeg_incorrect'))} | |")
        lines.append(
            f"| Higher uncertainty on errors | {fmt(metrics.get('higher_uncertainty_on_errors'))} | "
            "True jika rata-rata UDeg output salah lebih tinggi dari output benar (perilaku yang diharapkan). |"
        )
    lines.append("")


def _uq_group_summary_block(lines: list[str], group_summary: dict[str, Any]) -> None:
    if not group_summary:
        return
    lines.append("**Rincian CDeg/UDeg per kelompok skenario**\n")
    lines.append(
        "CDeg pada tabel ini adalah `selected_cdeg`, yaitu confidence degree dari sampel yang "
        "akhirnya dipakai agent (bukan rata-rata mentah seluruh sampel). Bandingkan dengan kolom "
        "UDeg untuk melihat hubungan 1 - CDeg secara langsung.\n"
    )
    lines.append(
        "| Kelompok | Jumlah | Pass rate | CDeg Context | UDeg Context | "
        "CDeg Dialogue | UDeg Dialogue | Grounding Dialogue |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for group_name, metrics in group_summary.items():
        lines.append(
            f"| {group_name} | {metrics.get('scenario_count', 0)} | {pct(metrics.get('pass_rate'))} | "
            f"{fmt(metrics.get('context_cdeg_mean'))} | {fmt(metrics.get('context_udeg_mean'))} | "
            f"{fmt(metrics.get('dialogue_cdeg_mean'))} | {fmt(metrics.get('dialogue_udeg_mean'))} | "
            f"{fmt(metrics.get('dialogue_grounding_mean'))} |"
        )
    lines.append("")


def section_uq_selective(lines: list[str], summary: dict[str, Any]) -> None:
    uncertainty_validation = summary.get("uncertainty_validation") or {}
    if not uncertainty_validation:
        return
    lines.append("## 4. UQ Selective Validation (50 Skenario Utama)\n")
    lines.append(
        "Mengukur apakah UDeg (uncertainty degree) yang lebih tinggi berkorelasi dengan output "
        "yang seharusnya ditolak. Catatan: jika seluruh 50 skenario lulus, AUROC tidak dapat "
        "dihitung (`N/A`) karena tidak ada kelas error untuk dibandingkan - gunakan bagian 5 "
        "untuk validasi dengan kegagalan terkontrol.\n"
    )
    for key, label in (("context_agent", "Context Agent"), ("dialogue_agent", "Dialogue Agent")):
        if key in uncertainty_validation:
            _uq_metric_block(lines, label, uncertainty_validation[key])
    _uq_group_summary_block(lines, summary.get("uq_group_summary") or {})


def section_uq_failure_validation(lines: list[str], summary: dict[str, Any] | None) -> None:
    if not summary or not summary.get("uq_failure_validation"):
        return
    lines.append("## 5. UQ Failure Validation (Benchmark Kegagalan Terkontrol)\n")
    lines.append(
        f"> {summary.get('benchmark_caveat', '')}\n"
        if summary.get("benchmark_caveat")
        else ""
    )
    failure_validation = summary["uq_failure_validation"]
    for key, label in (("context_agent", "Context Agent"), ("dialogue_agent", "Dialogue Agent")):
        metrics = failure_validation.get(key)
        if not metrics:
            continue
        lines.append(f"**{label}**\n")
        lines.append("| Metrik | Nilai | Penjelasan |")
        lines.append("|---|---|---|")
        lines.append(
            f"| Validation confirmed | {fmt(metrics.get('validation_confirmed'))} | "
            "True jika AUROC ≥ 0.70, UDeg error > UDeg benar, dan label benchmark konsisten (≥80% agreement). |"
        )
        lines.append(f"| Error-detection AUROC | {fmt(metrics.get('error_detection_auroc'))} | |")
        lines.append(f"| Mean CDeg correct / incorrect | {fmt(metrics.get('mean_cdeg_correct'))} / {fmt(metrics.get('mean_cdeg_incorrect'))} | |")
        lines.append(f"| Mean UDeg correct / incorrect | {fmt(metrics.get('mean_udeg_correct'))} / {fmt(metrics.get('mean_udeg_incorrect'))} | |")
        lines.append(f"| Mean UDeg gap | {fmt(metrics.get('mean_udeg_gap'))} | Selisih rata-rata UDeg salah dikurangi benar; semakin positif semakin baik. |")
        lines.append(f"| Mann-Whitney p (greater) | {fmt(metrics.get('mann_whitney_greater_p'), 6)} | p < 0.05 mendukung bahwa UDeg error signifikan lebih tinggi. |")
        lines.append(f"| Expected label agreement | {pct(metrics.get('expected_label_agreement'))} | Kesesuaian antara label yang dirancang dan hasil deterministic checks. |")
        threshold = metrics.get("benchmark_threshold") or {}
        if threshold:
            lines.append(
                f"| Threshold terbaik (benchmark) | UDeg ≥ {fmt(threshold.get('udeg_threshold'))} | "
                f"Balanced accuracy {fmt(threshold.get('balanced_accuracy'))}, "
                f"sensitivity {fmt(threshold.get('sensitivity'))}, specificity {fmt(threshold.get('specificity'))}. "
                "Diturunkan dari benchmark ini, belum tervalidasi pada data independen. |"
            )
        lines.append("")


def section_judge_validation(lines: list[str], payload: dict[str, Any] | None) -> None:
    if not payload:
        return
    summary = payload.get("summary", {})
    lines.append("## 6. Validasi Diskriminatif LLM Judge (Clean vs Corrupted)\n")
    lines.append(
        "Mengukur apakah judge benar-benar bisa membedakan output bersih dari output yang "
        "sengaja dirusak (target salah, hallucination, technical leak, prompt injection).\n"
    )
    lines.append("| Metrik | Nilai | Penjelasan |")
    lines.append("|---|---|---|")
    lines.append(f"| Total kasus / selesai | {summary.get('total_cases', 'N/A')} / {summary.get('completed_cases', 'N/A')} | |")
    lines.append(f"| Execution coverage | {pct(summary.get('execution_coverage'))} | |")
    lines.append(f"| Label accuracy | {pct(summary.get('label_accuracy'))} | Proporsi kasus di mana keputusan pass/fail judge sesuai label yang diharapkan. |")
    lines.append(f"| Sensitivity (clean pass) | {pct(summary.get('sensitivity_clean_pass'))} | Dari kasus bersih, berapa proporsi yang benar diloloskan judge. |")
    lines.append(f"| Specificity (corruption rejection) | {pct(summary.get('specificity_corruption_rejection'))} | Dari kasus yang dirusak, berapa proporsi yang benar ditolak judge. |")
    confusion = summary.get("confusion") or {}
    if confusion:
        lines.append(
            f"| Confusion matrix | TP={confusion.get('true_positive', 0)}, "
            f"FN={confusion.get('false_negative', 0)}, TN={confusion.get('true_negative', 0)}, "
            f"FP={confusion.get('false_positive', 0)} | |"
        )
    lines.append(f"| Validation confirmed | {fmt(summary.get('validation_confirmed'))} | True jika accuracy ≥ 0.80 dan kedua kelas (bersih & rusak) terwakili. |")
    lines.append("")


def section_reliability_ablation(lines: list[str], summary: dict[str, Any]) -> None:
    reliability = summary.get("reliability")
    ablation = summary.get("ablation")
    if not reliability and not ablation:
        return
    lines.append("## 7. Reliability & Ablation\n")
    if reliability:
        lines.append(
            f"- **Pass^{reliability.get('k')} score**: {fmt(reliability.get('pass_k_score'))} "
            "- probabilitas seluruh {k} run berulang pada skenario yang sama tetap lulus judge.\n"
        )
    if ablation:
        confirmed = "dikonfirmasi" if ablation.get("hypothesis_confirmed") else "tidak dikonfirmasi"
        lines.append(f"- **Hipotesis ablation**: {confirmed}. Delta scores: `{ablation.get('delta')}`\n")


def section_appendix(lines: list[str], main_path: Path | None, uq_path: Path | None, judge_path: Path | None) -> None:
    lines.append("## 8. Lampiran\n")
    lines.append("Sumber data mentah untuk laporan ini:\n")
    if main_path:
        lines.append(f"- Hasil evaluasi utama: `{main_path.relative_to(EVALS_DIR.parent)}`")
    if uq_path:
        lines.append(f"- Hasil UQ failure-validation: `{uq_path.relative_to(EVALS_DIR.parent)}`")
    if judge_path:
        lines.append(f"- Hasil judge validation: `{judge_path.relative_to(EVALS_DIR.parent)}`")
    lines.append("")
    figures = sorted(FIGURES_DIR.glob("*.png")) if FIGURES_DIR.exists() else []
    if figures:
        lines.append("Grafik yang tersedia (diperbarui setiap run evaluasi utama):\n")
        for figure in figures:
            lines.append(f"- `{figure.relative_to(EVALS_DIR.parent)}`")
        lines.append("")


def build_report(main: dict[str, Any] | None, uq_failure: dict[str, Any] | None, judge_validation: dict[str, Any] | None,
                  main_path: Path | None, uq_path: Path | None, judge_path: Path | None) -> str:
    lines: list[str] = []
    lines.append("# Laporan Evaluasi Multi-Agent (UQ + LLM-as-a-Judge)\n")
    lines.append(f"Dibuat: {datetime.utcnow().isoformat()} UTC\n")

    main_summary = (main or {}).get("summary", {})
    uq_summary = (uq_failure or {}).get("summary", {}) if uq_failure else None

    if main_summary:
        section_executive_summary(lines, main_summary)
        section_ir_metrics(lines, main_summary)
        section_llm_judge(lines, main_summary)
        section_uq_selective(lines, main_summary)
    else:
        lines.append("> Tidak ada file hasil evaluasi utama ditemukan. Jalankan "
                      "`run_agent_evaluation.py` terlebih dahulu.\n")

    section_uq_failure_validation(lines, uq_summary if uq_summary else main_summary)
    section_judge_validation(lines, judge_validation)
    if main_summary:
        section_reliability_ablation(lines, main_summary)
    section_appendix(lines, main_path, uq_path, judge_path)

    lines.append("## Catatan Metodologis\n")
    lines.append(
        "- Controlled corruption (bagian 5) membuktikan sensitivitas UQ terhadap gangguan yang "
        "diketahui; hasil ini perlu dilengkapi natural-error benchmark dari run model nyata.\n"
        "- `benchmark_threshold` diturunkan dari benchmark yang sama sehingga belum menjadi "
        "threshold produksi yang tervalidasi pada data independen.\n"
        "- Jika model agent dan model judge sama, ada risiko self-preference bias pada skor judge.\n"
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate readable Markdown report from eval results")
    parser.add_argument("--main", type=Path, help="Path to main eval_results_*.json (default: latest)")
    parser.add_argument("--uq-failure", type=Path, help="Path to eval_results_*.json with --uq-failure-validation data (default: latest with that data)")
    parser.add_argument("--judge-validation", type=Path, help="Path to judge_validation_*.json (default: latest)")
    parser.add_argument("--output", type=Path, help="Output Markdown path (default: evals/results/report_<timestamp>.md)")
    args = parser.parse_args()

    main_path = args.main or latest_file_with_key("eval_results_*.json", "total_scenarios")
    uq_path = args.uq_failure or latest_file_with_key("eval_results_*.json", "uq_failure_validation")
    if uq_path == main_path:
        # Same file already covers both sections; avoid loading it twice as "separate" UQ run.
        uq_path = args.uq_failure
    judge_path = args.judge_validation or latest_file("judge_validation_*.json")

    main_payload = load_json(main_path)
    uq_payload = load_json(uq_path) if uq_path and uq_path != main_path else None
    judge_payload = load_json(judge_path)

    report = build_report(main_payload, uq_payload, judge_payload, main_path, uq_path if uq_payload else None, judge_path)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    output_path = args.output or (RESULTS_DIR / f"report_{timestamp}.md")
    output_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nLaporan tersimpan: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
