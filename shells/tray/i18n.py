"""UI strings layer: RU/EN, default follows the system language.

Usage:
    from shells.tray.i18n import tr, set_language
    set_language(config.ui_language)     # "auto" | "ru" | "en"
    label.setText(tr("tray.settings"))
"""

from __future__ import annotations

import locale
import logging

log = logging.getLogger(__name__)

_STRINGS: dict[str, dict[str, str]] = {
    # -- overlay pill -----------------------------------------------------
    "pill.release_to_insert": {"ru": "отпусти — вставлю", "en": "release to insert"},
    "pill.hotkey_to_stop": {"ru": "хоткей — стоп", "en": "hotkey to stop"},
    "pill.transcribing": {"ru": "распознаю…", "en": "transcribing…"},
    "pill.empty": {"ru": "(пусто)", "en": "(empty)"},
    "pill.downloading_model": {"ru": "скачиваю модель — {pct}%", "en": "downloading model — {pct}%"},
    "pill.mic_muted": {
        "ru": "микрофон замьючен системой — кликни, чтобы включить",
        "en": "microphone is muted by the system — click to unmute",
    },
    "pill.insert_failed": {
        "ru": "не смог вставить — текст в буфере, нажми Ctrl+V",
        "en": "couldn't insert — text is on the clipboard, press Ctrl+V",
    },
    "pill.no_speech": {
        "ru": "речь не распознана — в записи не нашлось слов",
        "en": "no speech recognized in the recording",
    },
    "pill.mic_unavailable": {"ru": "микрофон недоступен: {err}", "en": "microphone unavailable: {err}"},
    "pill.mic_silent": {
        "ru": "микрофон молчит (уровень ~0) — проверь mute и устройство в настройках",
        "en": "the microphone is silent (level ~0) — check mute and the device in Settings",
    },
    "pill.mic_unmuted": {"ru": "микрофон включён — говори", "en": "microphone unmuted — go ahead"},
    "pill.transcribe_error": {"ru": "ошибка распознавания: {err}", "en": "recognition error: {err}"},
    "pill.model_failed": {"ru": "модель не загрузилась: {err}", "en": "model failed to load: {err}"},

    # -- tray ---------------------------------------------------------------
    "tray.loading_model": {"ru": "Загружаю модель…", "en": "Loading model…"},
    "tray.ready": {"ru": "Готов", "en": "Ready"},
    "tray.model_not_loaded": {"ru": "Модель не загружена", "en": "Model not loaded"},
    "tray.paused": {"ru": "Пауза", "en": "Paused"},
    "tray.copy_last": {"ru": "Последняя диктовка → копировать", "en": "Copy last dictation"},
    "tray.pause": {"ru": "Пауза (глушит хоткей)", "en": "Pause (mutes the hotkey)"},
    "tray.settings": {"ru": "Настройки…", "en": "Settings…"},
    "tray.history": {"ru": "История…", "en": "History…"},
    "tray.quit": {"ru": "Выход", "en": "Quit"},
    "tray.mic_silent_title": {"ru": "Микрофон молчит", "en": "Microphone is silent"},
    "tray.mic_silent_body": {
        "ru": "Стартовая проверка: с микрофона идёт цифровая тишина. Проверь устройство в настройках.",
        "en": "Startup check: the microphone delivers digital silence. Check the device in Settings.",
    },

    # -- settings window ---------------------------------------------------
    "set.title": {"ru": "Parrotype — настройки", "en": "Parrotype — Settings"},
    "set.nav.general": {"ru": "Общее", "en": "General"},
    "set.nav.model": {"ru": "Модель", "en": "Model"},
    "set.nav.dictionary": {"ru": "Словарь", "en": "Dictionary"},
    "set.nav.history": {"ru": "История", "en": "History"},
    "set.nav.about": {"ru": "О программе", "en": "About"},
    "set.hotkey_ptt": {"ru": "Хоткей (удерживать):", "en": "Hotkey (hold):"},
    "set.hotkey_toggle": {"ru": "Хоткей (вкл/выкл):", "en": "Hotkey (toggle):"},
    "set.hotkey_ptt_ph": {"ru": "например: ctrl+alt", "en": "e.g. ctrl+alt"},
    "set.hotkey_toggle_ph": {"ru": "например: ctrl+shift+space", "en": "e.g. ctrl+shift+space"},
    "set.language": {"ru": "Язык распознавания:", "en": "Recognition language:"},
    "set.ui_language": {"ru": "Язык интерфейса:", "en": "Interface language:"},
    "set.ui_lang.auto": {"ru": "Как в системе", "en": "System default"},
    "set.insert_method": {"ru": "Способ вставки:", "en": "Insert method:"},
    "set.insert.type": {"ru": "Печать (быстро, не трогает буфер)", "en": "Typing (fast, clipboard untouched)"},
    "set.insert.clipboard": {"ru": "Через буфер обмена (совместимость)", "en": "Clipboard (compatibility)"},
    "set.microphone": {"ru": "Микрофон:", "en": "Microphone:"},
    "set.mic_default": {"ru": "Системный по умолчанию", "en": "System default"},
    "set.mic_level": {"ru": "Уровень:", "en": "Level:"},
    "set.autostart": {"ru": "Автозапуск:", "en": "Autostart:"},
    "set.autostart_cb": {"ru": "Запускать вместе с Windows", "en": "Start with Windows"},
    "set.sound": {"ru": "Звук:", "en": "Sound:"},
    "set.sound_cb": {"ru": "Тихий тик старта/стопа записи", "en": "Quiet start/stop tick"},
    "set.model": {"ru": "Модель:", "en": "Model:"},
    "set.device": {"ru": "Устройство:", "en": "Device:"},
    "set.device.auto": {"ru": "Авто", "en": "Auto"},
    "set.device.cuda": {"ru": "GPU (CUDA)", "en": "GPU (CUDA)"},
    "set.device.cpu": {"ru": "CPU", "en": "CPU"},
    "set.context_label": {
        "ru": "Контекст распознавания (термины, имена — подсказка модели):",
        "en": "Recognition context (terms and names the model should expect):",
    },
    "set.context_ph": {
        "ru": "Например: Claude Code, Cloudflare, Kubernetes…",
        "en": "For example: Claude Code, Cloudflare, Kubernetes…",
    },
    "set.latency_btn": {"ru": "Тест латентности", "en": "Latency test"},
    "set.latency_hint": {
        "ru": "Замер на 10-сек аудио покажет реальную скорость выбранной модели.",
        "en": "A 10-second audio benchmark shows the real speed of the selected model.",
    },
    "set.latency_running": {
        "ru": "Замеряю… (первый запуск скачивает модель)",
        "en": "Measuring… (first run downloads the model)",
    },
    "set.latency_result": {
        "ru": "{model} @ {dev} ({compute}): {lat}с на {dur}с аудио",
        "en": "{model} @ {dev} ({compute}): {lat}s per {dur}s of audio",
    },
    "set.latency_fast": {"ru": " — на этой машине работает быстро.", "en": " — fast on this machine."},
    "set.latency_ok": {"ru": " — приемлемо.", "en": " — acceptable."},
    "set.latency_slow": {
        "ru": " — медленно, попробуй модель поменьше.",
        "en": " — slow; try a smaller model.",
    },
    "set.latency_error": {"ru": "Ошибка теста: {err}", "en": "Test failed: {err}"},
    "set.latency_no_wav": {
        "ru": "Тестовый файл assets/latency_test.wav не найден.",
        "en": "Test file assets/latency_test.wav is missing.",
    },
    "set.dict_hint": {
        "ru": "Словарь замен: «слышу → пишу». Применяется после распознавания.",
        "en": "Replacement dictionary: “heard → written”. Applied after recognition.",
    },
    "set.dict_heard": {"ru": "Слышу", "en": "Heard"},
    "set.dict_written": {"ru": "Пишу", "en": "Written"},
    "set.dict_add": {"ru": "Добавить", "en": "Add"},
    "set.dict_remove": {"ru": "Удалить строку", "en": "Remove row"},
    "set.hist_keep": {"ru": "Хранить историю диктовок (локально)", "en": "Keep dictation history (local)"},
    "set.hist_copy": {"ru": "Копировать", "en": "Copy"},
    "set.hist_delete": {"ru": "Удалить", "en": "Delete"},
    "set.hist_clear": {"ru": "Очистить всё", "en": "Clear all"},
    "set.hist_clear_q_title": {"ru": "История", "en": "History"},
    "set.hist_clear_q": {"ru": "Удалить все записи истории?", "en": "Delete all history entries?"},
    "set.about_version": {"ru": "Версия {ver}", "en": "Version {ver}"},
    "set.about_local": {
        "ru": "Всё работает локально: аудио и текст никуда не отправляются.",
        "en": "Everything runs locally: audio and text never leave this machine.",
    },
    "set.about_slogan": {"ru": "You talk. The parrot types.", "en": "You talk. The parrot types."},

    # -- wizard --------------------------------------------------------------
    "wiz.title": {"ru": "Parrotype — первый запуск", "en": "Parrotype — first run"},
    "wiz.step": {"ru": "ШАГ {n} · 3", "en": "STEP {n} · 3"},
    "wiz.mic.title": {"ru": "Микрофон", "en": "Microphone"},
    "wiz.mic.desc": {
        "ru": "Скажи что-нибудь — полоски должны двигаться.",
        "en": "Say something — the bars should move.",
    },
    "wiz.mic.ok": {"ru": "✓ слышу тебя — уровень хороший", "en": "✓ hearing you — good level"},
    "wiz.mic.silent": {"ru": "пока тишина…", "en": "silence so far…"},
    "wiz.mic.none": {
        "ru": "Микрофон не найден — подключи его и вернись к этому шагу.",
        "en": "No microphone found — plug one in and come back to this step.",
    },
    "wiz.model.title": {"ru": "Модель", "en": "Model"},
    "wiz.model.desc": {
        "ru": "Рекомендация под это железо. Модель скачается один раз.",
        "en": "Recommended for this hardware. The model downloads once.",
    },
    "wiz.model.rec_gpu": {"ru": "РЕКОМЕНДУЕМ · GPU", "en": "RECOMMENDED · GPU"},
    "wiz.model.rec_cpu": {"ru": "РЕКОМЕНДУЕМ · CPU", "en": "RECOMMENDED · CPU"},
    "wiz.model.downloading": {"ru": "Скачиваю модель — {pct}%", "en": "Downloading model — {pct}%"},
    "wiz.model.cached": {"ru": "Модель уже скачана.", "en": "Model already downloaded."},
    "wiz.model.failed": {
        "ru": "Не получилось скачать — проверь интернет и попробуй ещё раз.",
        "en": "Download failed — check your internet connection and try again.",
    },
    "wiz.model.retry": {"ru": "Повторить", "en": "Retry"},
    "wiz.hotkey.title": {"ru": "Хоткей и проба", "en": "Hotkey & try it"},
    "wiz.hotkey.desc": {
        "ru": "Зажми и держи, чтобы говорить:",
        "en": "Press and hold to talk:",
    },
    "wiz.hotkey.try": {"ru": "Попробуй продиктовать сюда:", "en": "Try dictating here:"},
    "wiz.next": {"ru": "Дальше", "en": "Next"},
    "wiz.done": {"ru": "Готово", "en": "Done"},
    "wiz.back": {"ru": "Назад", "en": "Back"},
}

_language = "ru"


def system_language() -> str:
    try:
        lang = locale.getlocale()[0] or ""
    except ValueError:
        lang = ""
    return "ru" if lang.lower().startswith(("ru", "russian")) else "en"


def set_language(ui_language: str) -> None:
    """ui_language: "auto" | "ru" | "en"."""
    global _language
    _language = system_language() if ui_language == "auto" else (
        ui_language if ui_language in ("ru", "en") else "en"
    )


def current_language() -> str:
    return _language


def tr(key: str, **kwargs) -> str:
    entry = _STRINGS.get(key)
    if entry is None:
        log.warning("Missing i18n key: %s", key)
        return key
    text = entry.get(_language) or entry["en"]
    return text.format(**kwargs) if kwargs else text
