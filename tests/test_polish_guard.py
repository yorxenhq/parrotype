"""Unit tests for the polish guard and prompt builder (no model needed).

The guard is the safety contract of the polish layer: model output that
could be worse than the raw transcript must be rejected. These tests pin
that contract.
"""

import pytest

from core.polish import PolishEngine, PolishResult

guard = PolishEngine._guard_ok


# -- allowed edits -----------------------------------------------------------

def test_filler_removal_passes():
    raw = "эээ ну короче нам нужно перенести встречу на завтра"
    polished = "Нам нужно перенести встречу на завтра."
    assert guard(raw, polished, [])


def test_self_correction_passes():
    raw = "отправь отчёт в пятницу нет лучше в четверг до обеда"
    polished = "Отправь отчёт в четверг до обеда."
    assert guard(raw, polished, [])


def test_punctuation_and_case_only_passes():
    raw = "привет как дела что нового"
    polished = "Привет! Как дела? Что нового?"
    assert guard(raw, polished, [])


def test_digit_normalization_passes():
    raw = "встретимся в три часа"
    polished = "Встретимся в 3 часа."
    assert guard(raw, polished, [])


def test_dictionary_term_spelling_passes():
    # «клауд код» corrected to the dictionary spelling is legitimate.
    raw = "открой клауд код и проверь логи"
    polished = "Открой Claude Code и проверь логи."
    assert guard(raw, polished, ["Claude Code"])


def test_identity_passes():
    raw = "просто обычный текст без правок"
    assert guard(raw, raw, [])


# -- rejected output ---------------------------------------------------------

def test_invented_word_rejected():
    raw = "нам нужно перенести встречу"
    polished = "Нам нужно срочно перенести важную встречу."
    assert not guard(raw, polished, [])


def test_answering_the_question_rejected():
    # Dictated text contains a question; model must not answer it.
    raw = "как называется столица франции спроси у него"
    polished = "Столица Франции — Париж."
    assert not guard(raw, polished, [])


def test_translation_rejected():
    raw = "нам нужно отправить отчёт завтра"
    polished = "We need to send the report tomorrow."
    assert not guard(raw, polished, [])


def test_substantial_growth_rejected():
    raw = "короткий текст"
    polished = "короткий текст " * 4
    assert not guard(raw, polished, [])


def test_non_dictionary_term_injection_rejected():
    raw = "проверь деплой пожалуйста"
    polished = "Проверь деплой на Kubernetes, пожалуйста."
    assert not guard(raw, polished, [])


# -- prompt builder / short-input path ----------------------------------------

def test_short_input_skipped_without_model():
    engine = PolishEngine()          # no model on purpose
    result = engine.polish("ок")
    assert isinstance(result, PolishResult)
    assert result.text == "ок"
    assert result.reason == "short"
    assert not result.changed


def test_messages_include_dictionary_and_fewshot():
    engine = PolishEngine()
    messages = engine._build_messages("тестовый текст", ["Claude Code", "Cloudflare"])
    assert messages[0]["role"] == "system"
    assert "Claude Code, Cloudflare" in messages[0]["content"]
    # dictation goes in as enveloped DATA, not as a bare instruction
    assert messages[-1] == {"role": "user", "content": "Диктовка: тестовый текст"}
    # few-shot pairs present between system and the final user turn
    roles = [m["role"] for m in messages[1:-1]]
    assert roles == ["user", "assistant"] * (len(roles) // 2) and roles


def test_language_tracks():
    engine = PolishEngine()
    ru = engine._build_messages("привет мир как дела", [])
    en = engine._build_messages("hello world how are you", [])
    assert ru[0]["content"].startswith("Ты — фильтр диктовки")
    assert en[0]["content"].startswith("You are a dictation filter")
    assert en[-1]["content"].startswith("Dictation: ")
    # explicit language hint wins over script detection
    forced = engine._build_messages("hello world", [], language="ru")
    assert forced[0]["content"].startswith("Ты — фильтр диктовки")


def test_error_path_falls_back_to_raw(monkeypatch):
    engine = PolishEngine()

    def boom():
        raise RuntimeError("no model")

    monkeypatch.setattr(engine, "load", boom)
    result = engine.polish("это достаточно длинный текст для полировки")
    assert result.text == "это достаточно длинный текст для полировки"
    assert result.fell_back
    assert result.reason.startswith("error")
