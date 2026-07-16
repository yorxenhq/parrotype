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

    # -- app ------------------------------------------------------------------
    "app.already_running_title": {"ru": "Parrotype", "en": "Parrotype"},
    "app.already_running": {
        "ru": "Parrotype уже запущен — ищи иконку в трее.",
        "en": "Parrotype is already running — look for the tray icon.",
    },

    # -- tray ---------------------------------------------------------------
    "tray.loading_model": {"ru": "Загружаю модель…", "en": "Loading model…"},
    "tray.ready": {"ru": "Готов", "en": "Ready"},
    "tray.model_not_loaded": {"ru": "Модель не загружена", "en": "Model not loaded"},
    "tray.paused": {"ru": "Пауза", "en": "Paused"},
    "tray.copy_last": {"ru": "Последняя диктовка → копировать", "en": "Copy last dictation"},
    "tray.pause": {"ru": "Пауза — не слушать хоткей", "en": "Pause — ignore the hotkey"},
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
    "set.insert.type": {"ru": "Печатает как клавиатура", "en": "Types like a keyboard"},
    "set.insert.clipboard": {"ru": "Вставляет через буфер", "en": "Pastes via clipboard"},
    "set.insert_tip": {
        "ru": "«Печатает» не трогает буфер обмена. Если в каком-то приложении текст приходит битым — переключись на буфер.",
        "en": "Typing keeps your clipboard untouched. If some app garbles the text, switch to clipboard.",
    },
    "set.microphone": {"ru": "Микрофон:", "en": "Microphone:"},
    "set.mic_default": {"ru": "Системный по умолчанию", "en": "System default"},
    "set.mic_level": {"ru": "Уровень:", "en": "Level:"},
    "set.autostart": {"ru": "Автозапуск:", "en": "Autostart:"},
    "set.autostart_cb": {"ru": "Запускать вместе с Windows", "en": "Start with Windows"},
    "set.sound": {"ru": "Звук:", "en": "Sound:"},
    "set.sound_cb": {"ru": "Щелчок при записи", "en": "Click on record"},
    "set.model": {"ru": "Модель:", "en": "Model:"},
    "set.device": {"ru": "Устройство:", "en": "Device:"},
    "set.device.auto": {"ru": "Авто", "en": "Auto"},
    "set.device.cuda": {"ru": "GPU (CUDA)", "en": "GPU (CUDA)"},
    "set.device.cpu": {"ru": "CPU", "en": "CPU"},
    "set.context_label": {
        "ru": "Твои слова и имена — чтобы модель писала их правильно:",
        "en": "Your words and names — so the model spells them right:",
    },
    "set.context_ph": {
        "ru": "Например: Claude Code, Cloudflare, Kubernetes…",
        "en": "For example: Claude Code, Cloudflare, Kubernetes…",
    },
    "set.context_tip": {
        "ru": "Всё, что ты часто диктуешь: продукты, фамилии, жаргон. Словарь замен добавляется сюда сам.",
        "en": "Anything you dictate often: products, names, jargon. Dictionary entries are added automatically.",
    },
    "set.latency_btn": {"ru": "Проверить скорость", "en": "Check speed"},
    "set.latency_hint": {
        "ru": "Проверить скорость этой модели на этом компьютере.",
        "en": "See how fast this model runs on this computer.",
    },
    "set.latency_running": {
        "ru": "Проверяю… (если модели ещё нет — сначала скачаю)",
        "en": "Checking… (downloads the model first if needed)",
    },
    "set.latency_result": {
        "ru": "{model} @ {dev} ({compute}): {lat}с на {dur}с аудио",
        "en": "{model} @ {dev} ({compute}): {lat}s per {dur}s of audio",
    },
    "set.latency_fast": {"ru": " — быстро, можно жить.", "en": " — fast, you're set."},
    "set.latency_ok": {"ru": " — нормально.", "en": " — decent."},
    "set.latency_slow": {
        "ru": " — медленно, возьми модель поменьше.",
        "en": " — slow; pick a smaller model.",
    },
    "set.latency_error": {"ru": "Ошибка теста: {err}", "en": "Test failed: {err}"},
    "set.latency_no_wav": {
        "ru": "Тестовый файл assets/latency_test.wav не найден.",
        "en": "Test file assets/latency_test.wav is missing.",
    },
    "set.dict_hint": {
        "ru": "Слева — как ты говоришь, справа — как надо писать.",
        "en": "Left — how you say it, right — how it should be written.",
    },
    "set.dict_empty": {
        "ru": "Пока пусто. Например: «клод» → Claude — и так будет писаться всегда.",
        "en": "Nothing here yet. For example: “clod” → Claude — and it will always be written that way.",
    },
    "set.dict_heard": {"ru": "Слышу", "en": "Heard"},
    "set.dict_written": {"ru": "Пишу", "en": "Written"},
    "set.dict_add": {"ru": "Добавить", "en": "Add"},
    "set.dict_remove": {"ru": "Удалить строку", "en": "Remove row"},
    "set.hist_keep": {"ru": "Помнить последние диктовки", "en": "Remember recent dictations"},
    "set.hist_empty": {
        "ru": "Пока пусто — продиктуй что-нибудь.",
        "en": "Nothing here yet — dictate something.",
    },
    "set.hist_copy": {"ru": "Копировать", "en": "Copy"},
    "set.hist_delete": {"ru": "Удалить", "en": "Delete"},
    "set.hist_clear": {"ru": "Очистить всё", "en": "Clear all"},
    "set.hist_clear_q_title": {"ru": "История", "en": "History"},
    "set.hist_clear_q": {"ru": "Удалить все записи истории?", "en": "Delete all history entries?"},
    "set.about_version": {"ru": "Версия {ver}", "en": "Version {ver}"},
    "set.about_local": {
        "ru": "Всё происходит на этом компьютере. Твой голос и твой текст не уходят никуда — даже к нам.",
        "en": "Everything happens on this computer. Your voice and your text go nowhere — not even to us.",
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
    "wiz.mic.local_note": {
        "ru": "Работает целиком на твоём компьютере — голос никуда не уезжает.",
        "en": "Everything runs on your machine — your voice never leaves it.",
    },
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
    "wiz.model.gpu_missing_libs": {
        "ru": "GPU найден, но CUDA-библиотек нет — работаю на CPU.",
        "en": "GPU detected, but CUDA libraries are missing — running on CPU.",
    },
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
