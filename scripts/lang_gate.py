"""Language auto-gate: measure real recognition quality per language.

For each candidate language: synthesize a native test sentence with
edge-tts (free MS neural voices; dev-time tool only, NOT a product
dependency), transcribe it with the production engine settings
(large-v3-turbo on the available device, language forced), and score
keyword recall.

GATE THRESHOLD: >= 0.8 keyword recall (5 of 6 content keywords).
Rationale: content keywords are the words a dictation must not lose;
80% recall on clean synthetic speech is the floor below which real-world
(noisy, accented) dictation would be frustrating. Punctuation and case
are ignored — the post-filter dictionary handles cosmetics.

Run: python scripts/lang_gate.py [--models large-v3-turbo]
Output: markdown table (stdout) + design/preview/lang-gate.md
"""

from __future__ import annotations

import asyncio
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import Config, Engine  # noqa: E402

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

THRESHOLD = 0.8
OUT_DIR = Path(__file__).resolve().parents[1] / "design" / "preview"
AUDIO_DIR = Path(__file__).resolve().parents[1] / "tests" / "data" / "langs"

# language -> (edge-tts voice, test sentence, content keywords)
CASES: dict[str, tuple[str, str, list[str]]] = {
    "en": (
        "en-US-GuyNeural",
        "Open the settings window, check the latency table and restart the local server before the meeting.",
        ["settings", "latency", "table", "restart", "server", "meeting"],
    ),
    "ru": (
        "ru-RU-DmitryNeural",
        "Открой окно настроек, проверь таблицу задержек и перезапусти локальный сервер перед совещанием.",
        ["настроек", "таблицу", "задержек", "перезапусти", "сервер", "совещанием"],
    ),
    "es": (
        "es-ES-AlvaroNeural",
        "Abre la ventana de configuración, revisa la tabla de latencia y reinicia el servidor local antes de la reunión.",
        ["ventana", "configuración", "tabla", "latencia", "servidor", "reunión"],
    ),
    "de": (
        "de-DE-ConradNeural",
        "Öffne das Einstellungsfenster, prüfe die Latenztabelle und starte den lokalen Server vor der Besprechung neu.",
        ["einstellungsfenster", "latenztabelle", "lokalen", "server", "besprechung", "starte"],
    ),
    "fr": (
        "fr-FR-HenriNeural",
        "Ouvre la fenêtre des paramètres, vérifie le tableau de latence et redémarre le serveur local avant la réunion.",
        ["fenêtre", "paramètres", "tableau", "latence", "serveur", "réunion"],
    ),
    "it": (
        "it-IT-DiegoNeural",
        "Apri la finestra delle impostazioni, controlla la tabella della latenza e riavvia il server locale prima della riunione.",
        ["finestra", "impostazioni", "tabella", "latenza", "server", "riunione"],
    ),
    "pt": (
        "pt-BR-AntonioNeural",
        "Abra a janela de configurações, verifique a tabela de latência e reinicie o servidor local antes da reunião.",
        ["janela", "configurações", "tabela", "latência", "servidor", "reunião"],
    ),
    "pl": (
        "pl-PL-MarekNeural",
        "Otwórz okno ustawień, sprawdź tabelę opóźnień i zrestartuj lokalny serwer przed spotkaniem.",
        ["okno", "ustawień", "tabelę", "opóźnień", "serwer", "spotkaniem"],
    ),
    "uk": (
        "uk-UA-OstapNeural",
        "Відкрий вікно налаштувань, перевір таблицю затримок і перезапусти локальний сервер перед нарадою.",
        ["вікно", "налаштувань", "таблицю", "затримок", "перезапусти", "сервер"],
    ),
    "nl": (
        "nl-NL-MaartenNeural",
        "Open het instellingenvenster, controleer de latentietabel en herstart de lokale server voor de vergadering.",
        ["instellingenvenster", "latentietabel", "herstart", "lokale", "server", "vergadering"],
    ),
    "tr": (
        "tr-TR-AhmetNeural",
        "Ayarlar penceresini aç, gecikme tablosunu kontrol et ve toplantıdan önce yerel sunucuyu yeniden başlat.",
        ["ayarlar", "penceresini", "gecikme", "tablosunu", "yerel", "sunucuyu"],
    ),
    "ja": (
        "ja-JP-KeitaNeural",
        "設定ウィンドウを開いて、遅延テーブルを確認し、会議の前にローカルサーバーを再起動してください。",
        ["設定", "遅延", "確認", "会議", "サーバー", "再起動"],
    ),
    "ko": (
        "ko-KR-InJoonNeural",
        "설정 창을 열고 지연 시간 테이블을 확인한 다음 회의 전에 로컬 서버를 다시 시작하세요.",
        ["설정", "지연", "테이블", "확인", "회의", "서버"],
    ),
    "zh": (
        "zh-CN-YunxiNeural",
        "打开设置窗口，检查延迟表格，并在会议之前重启本地服务器。",
        ["设置", "延迟", "表格", "会议", "重启", "服务器"],
    ),
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    return "".join(ch for ch in text if ch.isalnum() or ch.isspace())


async def _synthesize(voice: str, text: str, path: Path) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(path))


def synthesize_all() -> dict[str, Path]:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    async def run() -> None:
        for lang, (voice, text, _) in CASES.items():
            path = AUDIO_DIR / f"gate_{lang}.mp3"
            if not path.exists() or path.stat().st_size < 1000:
                print(f"  synthesizing {lang} ({voice})…", file=sys.stderr)
                await _synthesize(voice, text, path)
            paths[lang] = path

    asyncio.run(run())
    return paths


def main() -> None:
    model = "large-v3-turbo"
    if "--model" in sys.argv:
        model = sys.argv[sys.argv.index("--model") + 1]

    paths = synthesize_all()

    cfg = Config()
    cfg.model_size = model
    cfg.device = "auto"
    cfg.compute_type = "auto"
    engine = Engine(cfg)
    engine.load_model()
    device, compute = cfg.resolve_device()

    rows: list[tuple[str, float, str, str]] = []
    for lang, (_, sentence, keywords) in CASES.items():
        engine.config.language = lang        # forced: gate measures the language itself
        result = engine.transcribe(str(paths[lang]))
        norm = _norm(result.raw_text)
        hits = sum(1 for kw in keywords if _norm(kw) in norm)
        recall = hits / len(keywords)
        verdict = "PASS" if recall >= THRESHOLD else "FAIL"
        rows.append((lang, recall, verdict, result.raw_text))
        print(f"  {lang}: {hits}/{len(keywords)} ({recall:.0%}) {verdict}", file=sys.stderr)

    lines = [
        "# Language gate results",
        "",
        f"Engine: {model} @ {device} ({compute}), production decode params, "
        f"language forced per case. Test speech: edge-tts neural voices "
        f"(dev-time tool). Gate: keyword recall >= {THRESHOLD:.0%}.",
        "",
        "| Language | Keyword recall | Verdict | Transcript |",
        "|---|---|---|---|",
    ]
    for lang, recall, verdict, transcript in rows:
        clean = transcript.replace("|", "\\|")[:90]
        lines.append(f"| {lang} | {recall:.0%} | {verdict} | {clean} |")
    lines.append("")
    passed = [lang for lang, recall, verdict, _ in rows if verdict == "PASS"]
    lines.append(f"Passed ({len(passed)}): {', '.join(passed)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "lang-gate.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
