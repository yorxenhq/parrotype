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
    "pill.polishing": {"ru": "полирую…", "en": "polishing…"},
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
        "ru": "не расслышал слов — попробуй ещё раз",
        "en": "couldn't make out any words — try again",
    },
    "pill.mic_unavailable": {"ru": "микрофон недоступен: {err}", "en": "microphone unavailable: {err}"},
    "pill.mic_silent": {
        "ru": "микрофон молчит — проверь mute и устройство в настройках",
        "en": "the microphone is silent — check mute and the device in Settings",
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
    "tray.copy_last": {"ru": "Копировать последнюю диктовку", "en": "Copy last dictation"},
    "tray.update": {"ru": "Вышла версия {ver} — скачать", "en": "Version {ver} is out — download"},
    "tray.pause": {"ru": "Пауза — не слушать хоткей", "en": "Pause — ignore the hotkey"},
    "tray.settings": {"ru": "Настройки…", "en": "Settings…"},
    "tray.history": {"ru": "История…", "en": "History…"},
    "tray.quit": {"ru": "Выход", "en": "Quit"},
    "tray.mic_silent_title": {"ru": "Микрофон молчит", "en": "Microphone is silent"},
    "tray.mic_silent_body": {
        "ru": "Микрофон отдаёт полную тишину. Проверь устройство в настройках.",
        "en": "The microphone is picking up nothing at all. Check the device in Settings.",
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
    "set.mic_default": {"ru": "Как в системе", "en": "System default"},
    "set.mic_level": {"ru": "Уровень:", "en": "Level:"},
    "set.autostart": {"ru": "Автозапуск:", "en": "Autostart:"},
    "set.autostart_cb": {"ru": "Запускать вместе с Windows", "en": "Start with Windows"},
    "set.sound": {"ru": "Звук:", "en": "Sound:"},
    "set.sound_cb": {"ru": "Щелчок при записи", "en": "Click on record"},
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
    "set.polish_cb": {
        "ru": "Полировать текст после распознавания",
        "en": "Polish the transcript",
    },
    "set.polish_hint": {
        "ru": "Убирает «эээ» и слова-паразиты, склеивает самоисправления "
              "(«в три… нет, в четыре» — останется «в четыре»), расставляет знаки. "
              "Работает на этом компьютере, как и всё остальное. Если модель "
              "сомневается — вставится исходный текст без изменений.",
        "en": "Removes “um” and filler words, resolves self-corrections "
              "(“at three… no, at four” keeps “at four”), fixes punctuation. "
              "Runs on this computer like everything else. When the model is "
              "unsure, the original text is inserted unchanged.",
    },
    "set.polish_downloading": {
        "ru": "Скачиваю модель полировки (~1.1 ГБ, один раз) — {pct}%",
        "en": "Downloading the polish model (~1.1 GB, one time) — {pct}%",
    },
    "set.polish_ready": {
        "ru": "Полировка включена. Исходный текст каждой диктовки сохраняется в истории.",
        "en": "Polish is on. The raw transcript of every dictation is kept in History.",
    },
    "set.polish_failed": {
        "ru": "Не получилось скачать модель: {err}",
        "en": "Could not download the model: {err}",
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
        "ru": "{model} на {dev}: {lat} с на {dur} с записи",
        "en": "{model} on {dev}: {lat}s for {dur}s of audio",
    },
    "set.latency_fast": {"ru": " — быстро, можно жить.", "en": " — fast, you're set."},
    "set.latency_ok": {"ru": " — нормально.", "en": " — decent."},
    "set.latency_slow": {
        "ru": " — медленно, возьми модель поменьше.",
        "en": " — slow; pick a smaller model.",
    },
    "set.latency_error": {"ru": "Ошибка теста: {err}", "en": "Test failed: {err}"},
    "set.latency_unstable": {
        "ru": "{model} упала на этой машине во время теста — приложение не пострадало. "
              "Модель отмечена как нестабильная: возьми другую или включи GPU.",
        "en": "{model} crashed on this machine during the test — the app itself is fine. "
              "It is now marked unstable: pick another model or enable the GPU.",
    },
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
    "set.hist_clear": {"ru": "Очистить всё", "en": "Clear all"},
    "set.hist_copied": {"ru": "✓ скопировано", "en": "✓ copied"},
    "set.hist_today": {"ru": "сегодня", "en": "today"},
    "set.hist_yesterday": {"ru": "вчера", "en": "yesterday"},
    "set.hist_secs": {"ru": "{n} с", "en": "{n}s"},
    "set.hist_delete_tip": {"ru": "Удалить эту диктовку", "en": "Delete this dictation"},
    "set.hist_clear_confirm": {"ru": "Удалить все диктовки?", "en": "Delete all dictations?"},
    "set.hist_clear_yes": {"ru": "Да, удалить", "en": "Yes, delete"},
    "set.hist_clear_no": {"ru": "Оставить", "en": "Keep them"},
    "set.about_version": {"ru": "Версия {ver}", "en": "Version {ver}"},
    "set.about_local": {
        "ru": "Всё происходит на этом компьютере. Твой голос и твой текст не уходят никуда — даже к нам. "
              "Сеть нужна только на два случая: скачать модель и раз в неделю спросить GitHub про новую версию — это можно выключить.",
        "en": "Everything happens on this computer. Your voice and your text go nowhere — not even to us. "
              "The network is used for two things only: downloading the model and asking GitHub once a week whether a new version is out — you can turn that off.",
    },
    "set.about_slogan": {"ru": "You talk. The parrot types.", "en": "You talk. The parrot types."},
    "set.about_free": {
        "ru": "Бесплатно для всех — и останется бесплатным.",
        "en": "Free for everyone — and staying that way.",
    },
    "set.about_coffee": {
        "ru": "Если Parrotype экономит тебе время — можешь угостить Eugene кофе.",
        "en": "If Parrotype saves you time, you can buy Eugene a coffee.",
    },
    "set.about_coffee_btn": {"ru": "Угостить кофе", "en": "Buy a coffee"},
    "set.updates_cb": {"ru": "Проверять обновления раз в неделю", "en": "Check for updates once a week"},
    "set.updates_note": {
        "ru": "Один анонимный запрос к GitHub, ничего о тебе не отправляется.",
        "en": "One anonymous request to GitHub; nothing about you is sent.",
    },
    "set.about_update": {
        "ru": 'Вышла версия {ver} — <a href="{url}">скачать на GitHub</a>',
        "en": 'Version {ver} is out — <a href="{url}">get it on GitHub</a>',
    },

    # -- model picker ---------------------------------------------------------
    "model.rec": {"ru": "рекомендуем", "en": "recommended"},
    "model.meta.speed": {"ru": "~{sec} с на фразу", "en": "~{sec}s per phrase"},
    "model.meta.speed_measured": {
        "ru": "{sec} с — замер на этой машине",
        "en": "{sec}s — measured on this machine",
    },
    "model.meta.unstable": {
        "ru": "падала на этой машине",
        "en": "crashed on this machine",
    },
    "model.machine": {"ru": "Эта машина: {hw}", "en": "This machine: {hw}"},
    "model.meta.size_mb": {"ru": "скачать ~{n} МБ", "en": "~{n} MB download"},
    "model.meta.size_gb": {"ru": "скачать ~{n} ГБ", "en": "~{n} GB download"},
    "model.desc.gpu.turbo": {
        "ru": "лучше всего слышит — видеокарте это легко",
        "en": "hears best — easy work for your graphics card",
    },
    "model.desc.gpu.medium": {
        "ru": "золотая середина — чуть меньше скачивать",
        "en": "the middle ground — a slightly smaller download",
    },
    "model.desc.gpu.small": {
        "ru": "самая лёгкая — если место на диске дорого",
        "en": "the lightest one — if disk space is tight",
    },
    "model.desc.cpu.small": {
        "ru": "слышит лучше всех — за это платишь парой секунд ожидания",
        "en": "hears best — you pay for it with a couple seconds of waiting",
    },
    "model.desc.cpu.base": {
        "ru": "компромисс: заметно быстрее, слышит чуть хуже",
        "en": "the trade-off: noticeably faster, hears slightly worse",
    },
    "model.desc.cpu.tiny": {
        "ru": "самая быстрая — и слышит хуже всех",
        "en": "the fastest — and the least accurate",
    },
    "model.desc.other": {
        "ru": "выбрана вручную — вне рекомендованного набора",
        "en": "picked by hand — outside the recommended set",
    },
    "model.device_note.cpu": {
        "ru": "Распознавать будет процессор — видеокарта NVIDIA не найдена.",
        "en": "Recognition runs on the processor — no NVIDIA graphics card found.",
    },
    "model.device_note.gpu": {
        "ru": "Распознавать будет видеокарта NVIDIA — самый быстрый вариант.",
        "en": "Recognition runs on your NVIDIA graphics card — the fastest option.",
    },

    # -- GPU runtime on-demand -------------------------------------------------
    "gpu.offer_note": {
        "ru": "В компьютере есть видеокарта NVIDIA. Один раз скачаем её библиотеки — "
              "и диктовка станет заметно быстрее и точнее (лучшие модели за доли секунды).",
        "en": "This computer has an NVIDIA graphics card. A one-time library download "
              "makes dictation much faster and more accurate (the best models in a fraction of a second).",
    },
    "gpu.offer_btn": {"ru": "Включить GPU", "en": "Enable GPU"},
    "gpu.offer_btn_size": {
        "ru": "Включить GPU — скачать {size} ГБ",
        "en": "Enable GPU — {size} GB download",
    },
    "gpu.downloading": {"ru": "Скачиваю GPU-библиотеки — {pct}%", "en": "Downloading GPU libraries — {pct}%"},
    "gpu.installing": {"ru": "Подключаю GPU…", "en": "Setting up the GPU…"},
    "gpu.done": {
        "ru": "GPU включён. Модели ниже пересчитаны под видеокарту.",
        "en": "GPU enabled. The models below are re-ranked for your graphics card.",
    },
    "gpu.failed": {
        "ru": "Не получилось подключить GPU: {err}. Всё продолжит работать на процессоре.",
        "en": "Could not set up the GPU: {err}. Everything keeps working on the processor.",
    },

    # -- wizard --------------------------------------------------------------
    "wiz.title": {"ru": "Parrotype — первый запуск", "en": "Parrotype — first run"},
    "wiz.step": {"ru": "шаг {n} из 3", "en": "step {n} of 3"},
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
        "ru": "Скачивается один раз и живёт только на этом компьютере.",
        "en": "Downloads once and lives only on this computer.",
    },
    "wiz.model.downloading": {"ru": "Скачиваю модель — {pct}%", "en": "Downloading model — {pct}%"},
    "wiz.model.cached": {"ru": "Модель уже скачана.", "en": "Model already downloaded."},
    "wiz.model.gpu_missing_libs": {
        "ru": "Пока распознаёт процессор — видеокарту можно включить выше.",
        "en": "Running on the processor for now — the GPU can be enabled above.",
    },
    "wiz.model.failed": {
        "ru": "Не получилось скачать — проверь интернет и попробуй ещё раз.",
        "en": "Download failed — check your internet connection and try again.",
    },
    "wiz.model.retry": {"ru": "Повторить", "en": "Retry"},
    "wiz.hotkey.title": {"ru": "Хоткей и первая диктовка", "en": "Hotkey & first dictation"},
    "wiz.hotkey.desc": {
        "ru": "Зажми и держи, чтобы говорить:",
        "en": "Press and hold to talk:",
    },
    "wiz.hotkey.try": {"ru": "Попробуй продиктовать сюда:", "en": "Try dictating here:"},
    "wiz.done_note": {
        "ru": "Parrotype бесплатный для всех. Понравится — в «О программе» можно угостить автора кофе.",
        "en": "Parrotype is free for everyone. If you end up liking it, there's a coffee button in About.",
    },
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
