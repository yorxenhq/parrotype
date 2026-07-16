from core.postfilter import PostFilter


def test_empty_filter_passthrough():
    assert PostFilter().apply("привет мир") == "привет мир"


def test_basic_replacement():
    pf = PostFilter({"клод": "Claude"})
    assert pf.apply("спроси клод об этом") == "спроси Claude об этом"


def test_case_insensitive():
    pf = PostFilter({"клод": "Claude"})
    assert pf.apply("Клод, привет") == "Claude, привет"


def test_word_boundary_no_substring():
    pf = PostFilter({"гит": "git"})
    assert pf.apply("гитара лежит") == "гитара лежит"
    assert pf.apply("открой гит") == "открой git"


def test_longest_key_wins():
    pf = PostFilter({"гит": "git", "гит хаб": "GitHub"})
    assert pf.apply("залей на гит хаб") == "залей на GitHub"


def test_multiword_and_punctuation():
    pf = PostFilter({"фейбл": "Fable"})
    assert pf.apply("модель фейбл, пять") == "модель Fable, пять"


def test_latin_replacement():
    pf = PostFilter({"vs code": "VS Code"})
    assert pf.apply("открой vs code сейчас") == "открой VS Code сейчас"


def test_empty_text():
    pf = PostFilter({"a": "b"})
    assert pf.apply("") == ""
