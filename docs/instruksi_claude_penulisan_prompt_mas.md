# Instruksi untuk Claude: Penulisan System Prompt dan User Prompt pada MAS

Gunakan instruksi ini untuk membantu menulis bagian skripsi tentang perancangan `system prompt` dan `user prompt` pada sistem Multi-Agent System (MAS) untuk refactoring Kotlin Android.

## Tujuan Penulisan

Tuliskan penjelasan akademik yang jelas, runtut, dan tidak sekadar mengikuti asumsi bahwa:

> User prompt adalah prompt yang hanya dipahami user/developer, sedangkan system prompt adalah prompt yang hanya dipahami sistem.

Pernyataan tersebut perlu dikoreksi. Jelaskan bahwa pembeda utama antara system prompt dan user prompt bukan terletak pada "siapa yang memahami", tetapi pada:

1. tingkat otoritas instruksi,
2. fungsi instruksi dalam pemanggilan model,
3. stabilitas isi prompt,
4. perannya dalam pipeline MAS.

## Landasan Konseptual yang Harus Dijelaskan

Gunakan konsep berikut sebagai dasar:

1. `System prompt` atau `developer prompt` berisi instruksi tingkat tinggi yang relatif statis, seperti persona agent, ruang lingkup tugas, metode kerja, batasan, aturan, dan format output.
2. `User prompt` berisi input dinamis untuk satu eksekusi tertentu, misalnya kode sumber, file target, hasil agent sebelumnya, error build, metrik kualitas kode, riwayat dialog, atau permintaan aktual dari pengguna.
3. Dalam konteks MAS, user prompt tidak selalu berarti pesan yang diketik langsung oleh end-user. User prompt dapat dibangun otomatis oleh orchestrator berdasarkan state pipeline.
4. Analogi yang dapat digunakan: system/developer prompt seperti definisi fungsi, sedangkan user prompt seperti argumen yang diberikan ke fungsi tersebut.
5. System/developer prompt memiliki prioritas lebih tinggi daripada user prompt ketika terjadi konflik instruksi.

Rujukan konseptual yang boleh disebut:

- OpenAI API documentation tentang message roles: developer/system message berisi aturan dan business logic, sedangkan user message berisi input atau konfigurasi kasus.
- OpenAI Model Spec tentang instruction hierarchy: root/system/developer/user.
- Jika menyebut Chain-of-Thought, hindari mengatakan bahwa model harus menampilkan seluruh proses berpikir internal. Gunakan frasa seperti "penalaran internal bertahap" dan minta output berupa ringkasan alasan, bukan chain-of-thought lengkap.

## Gaya Penulisan

Tulis dalam bahasa Indonesia akademik, tetapi tetap jelas dan tidak terlalu kaku. Gunakan istilah teknis secara konsisten:

- `system prompt`
- `developer prompt`
- `user prompt`
- `orchestrator`
- `agent`
- `pipeline`
- `runtime context`
- `output schema`

Jangan terlalu sering memakai bahasa promosi seperti "sangat penting" atau "sangat efektif". Fokus pada argumentasi metodologis.

## Struktur Bagian yang Diminta

Susun bagian tulisan dengan struktur berikut.

### 1. Definisi System Prompt dan User Prompt

Jelaskan bahwa:

```text
System prompt merupakan instruksi statis yang mendefinisikan perilaku,
batasan, metode kerja, dan format keluaran agent.

User prompt merupakan instruksi dinamis yang membawa data kasus pada
iterasi tertentu, seperti kode sumber, metrik, error, hasil agent sebelumnya,
atau permintaan aktual dari pengguna.
```

Tekankan bahwa dalam MAS, user prompt bisa dibangun oleh orchestrator, sehingga tidak selalu berupa pesan mentah dari pengguna.

### 2. Peran Prompt dalam Multi-Agent System

Jelaskan bahwa setiap agent memiliki system prompt yang berbeda sesuai tugasnya. Contoh:

- Dialogue Agent: memahami intent user dan menentukan rute pipeline.
- Context Agent: membangun konteks teknis dari kode dan dependency.
- Code Analysis Agent: menganalisis SOLID dan clean code.
- Refactoring Strategy Agent: menyusun rencana refactoring.
- Refactoring Execution Agent: menerapkan refactoring.
- Error Correction Agent: memperbaiki error kompilasi.

User prompt pada setiap agent berubah mengikuti state pipeline. Misalnya:

- Dialogue Agent menerima pesan user dan status pipeline.
- Context Agent menerima file target, struktur proyek, dan dependency.
- Strategy Agent menerima GapReport, ContextReport, dan kode.
- Execution Agent menerima RefactoringPlan dan kode asli.
- Error Correction Agent menerima error build dan kode gagal kompilasi.

### 3. Prinsip Desain Prompt pada MAS

Jelaskan prinsip berikut:

1. Separation of responsibility: setiap agent hanya menerima instruksi sesuai tugasnya.
2. Minimal sufficient context: user prompt hanya memuat konteks yang dibutuhkan agent.
3. Constraint-driven generation: system prompt memuat batasan eksplisit untuk mengurangi halusinasi.
4. Structured output: setiap agent menghasilkan output dalam format terstruktur agar mudah diproses orchestrator.
5. Iteration awareness: agent tertentu, terutama Error Correction Agent, menerima ringkasan percobaan sebelumnya.

### 4. Contoh Penulisan untuk Context Agent

Tuliskan contoh seperti ini, lalu boleh diperhalus agar cocok dengan gaya skripsi.

```text
System Prompt Context Agent

=== [I] INSTRUCTION PERSONA ===
Kamu adalah Context Analysis Agent untuk sistem multi-agent refactoring Kotlin Android.

=== [II] INSTRUCTION TASK ===
Bangun konteks teknis dari file target, termasuk layer arsitektur, dependency,
tanggung jawab utama, file terkait, dan informasi yang relevan untuk agent
analisis/refactoring berikutnya.

=== [III] INSTRUCTION METHOD ===
1. Identifikasi layer arsitektur berdasarkan path, import, dan isi kode.
2. Petakan dependency langsung dari import, constructor, function call, dan class reference.
3. Ringkas responsibility utama file.
4. Pilih hanya konteks yang relevan untuk analisis SOLID, clean code, dan refactoring.

=== [IV] RULE ===
✗ Jangan menyarankan refactoring.
✗ Jangan mengubah kode.
✗ Jangan membuat asumsi tanpa bukti dari kode/path/dependency.
✗ Jika informasi tidak cukup, beri nilai "unknown" dan jelaskan alasannya.

=== [V] OUTPUT FORMAT ===
{
  "file_path": string,
  "architecture_layer": string,
  "main_responsibility": string,
  "related_files": [],
  "dependencies": [],
  "context_summary": string,
  "confidence": number
}
```

Contoh user prompt Context Agent:

```text
User Prompt Context Agent

Bangun ContextReport untuk file berikut.

=== FILE TARGET ===
Path: {FILE_PATH}

=== STRUKTUR PROYEK TERKAIT ===
{RELEVANT_PROJECT_TREE}

=== KONTEN FILE TARGET ===
```kotlin
{KOTLIN_FILE_CONTENT}
```

=== FILE/DEPENDENCY TERKAIT ===
{RELATED_FILES_OR_DEPENDENCY_GRAPH}

Hasilkan ContextReport sesuai format JSON yang ditentukan.
```

### 5. Contoh Penulisan untuk Dialogue Agent

Tuliskan contoh seperti ini.

```text
System Prompt Dialogue Agent

=== [I] INSTRUCTION PERSONA ===
Kamu adalah Dialogue Management Agent untuk sistem multi-agent refactoring.

=== [II] INSTRUCTION TASK ===
Pahami pesan user, identifikasi intent, ekstrak target file/aksi/batasan,
deteksi informasi yang kurang, dan tentukan instruksi berikutnya untuk orchestrator.

=== [III] INSTRUCTION METHOD ===
1. Intent Detection: tentukan maksud utama user.
2. Slot Extraction: ambil file target, aksi yang diminta, batasan, dan preferensi.
3. Ambiguity Check: cek apakah ada informasi penting yang belum tersedia.
4. Orchestrator Routing: tentukan agent berikutnya yang perlu dijalankan.

=== [IV] RULE ===
✗ Jangan melakukan analisis kode mendalam.
✗ Jangan mengarang status pipeline.
✗ Jangan menyarankan refactoring teknis tanpa output dari analysis/strategy agent.
✗ Jika informasi tidak cukup, minta klarifikasi.

=== [V] OUTPUT FORMAT ===
{
  "user_intent": string,
  "requested_action": string,
  "target_files": [],
  "constraints": [],
  "needs_clarification": boolean,
  "clarification_questions": [],
  "next_agent": string,
  "orchestrator_instruction": string,
  "user_facing_response": string
}
```

Contoh user prompt Dialogue Agent:

```text
User Prompt Dialogue Agent

Analisis pesan user berikut.

=== PESAN USER ===
{USER_MESSAGE}

=== RIWAYAT DIALOG TERKAIT ===
{RECENT_DIALOG_HISTORY}

=== STATUS PIPELINE ===
Tahap saat ini: {CURRENT_STAGE}
File aktif: {ACTIVE_FILES}
Agent terakhir: {LAST_AGENT}
Status terakhir: {LAST_STATUS}

=== OUTPUT AGENT TERAKHIR ===
{LATEST_AGENT_OUTPUT_SUMMARY}

Tentukan intent user, informasi yang kurang, dan instruksi berikutnya
untuk orchestrator dalam format JSON.
```

## Rumusan yang Disarankan untuk Skripsi

Gunakan paragraf inti berikut sebagai basis:

```text
Dalam penelitian ini, prompt pada setiap agent dibedakan menjadi system prompt
dan user prompt. System prompt digunakan untuk mendefinisikan perilaku tetap
agent, termasuk persona, ruang lingkup tugas, metode kerja, batasan, dan skema
keluaran. Dengan demikian, system prompt berfungsi sebagai instruksi statis
yang menjaga konsistensi perilaku agent pada setiap pemanggilan.

Sebaliknya, user prompt digunakan untuk menyediakan konteks dinamis pada suatu
iterasi pipeline. Pada sistem multi-agent yang dikembangkan, user prompt tidak
selalu berasal langsung dari pengguna akhir, melainkan dapat dibangun oleh
orchestrator berdasarkan state pipeline, artefak hasil agent sebelumnya, kode
sumber, metrik kualitas kode, error kompilasi, atau riwayat dialog. Dengan
pemisahan ini, setiap agent dapat menjalankan tugas yang spesifik dengan
konteks yang cukup tanpa menerima informasi yang tidak relevan.
```

## Hal yang Harus Dihindari

Jangan menulis:

```text
User prompt adalah prompt yang hanya dipahami user.
System prompt adalah prompt yang hanya dipahami system.
```

Ganti dengan:

```text
Perbedaan system prompt dan user prompt terletak pada tingkat otoritas,
stabilitas isi, dan fungsinya dalam pemanggilan model. System prompt
mendefinisikan aturan dan perilaku agent, sedangkan user prompt membawa
data kasus yang diproses oleh agent pada iterasi tertentu.
```

Jangan menyatakan bahwa user prompt selalu diketik oleh user. Dalam MAS, user prompt dapat berupa payload yang dihasilkan oleh orchestrator.

Jangan menyatakan bahwa system prompt "hanya dipahami sistem". System prompt tetap berupa instruksi bahasa alami atau terstruktur yang dibaca model, tetapi memiliki prioritas lebih tinggi dan biasanya tidak ditampilkan kepada end-user.

## Output yang Diminta dari Claude

Minta Claude menghasilkan:

1. Penjelasan konseptual system prompt vs user prompt.
2. Penjelasan penerapan pada MAS.
3. Contoh system prompt dan user prompt untuk Context Agent.
4. Contoh system prompt dan user prompt untuk Dialogue Agent.
5. Paragraf siap pakai untuk dimasukkan ke Bab 3 bagian perancangan prompt.

Pastikan hasil akhirnya koheren dengan pola penulisan agent lain, misalnya:

```text
=== [I] INSTRUCTION PERSONA ===
=== [II] INSTRUCTION TASK ===
=== [III] INSTRUCTION METHOD ===
=== [IV] TEKNIK PROMPT ===
=== [V] RULE ===
=== [VI] OUTPUT FORMAT ===
```

