from taro.report import build_sentences
from taro.text import clean_answer, parse_citations, remap_citations, split_sentences


def test_parse_citations_formats():
    assert parse_citations("Paris is the capital [1].") == ("Paris is the capital.", [1])
    assert parse_citations("A fact [1][3] and more [3].") == ("A fact and more.", [1, 3])
    assert parse_citations("Range [2-4], list [1, 5].") == ("Range, list.", [2, 3, 4, 1, 5])
    assert parse_citations("No citations here.") == ("No citations here.", [])


def test_split_sentences_keeps_trailing_citations():
    text = "Paris is the capital [1]. It has 2 million people. [2][3] Is it big? Yes [4]."
    assert split_sentences(text) == [
        "Paris is the capital [1].",
        "It has 2 million people. [2][3]",
        "Is it big?",
        "Yes [4].",
    ]


def test_split_sentences_does_not_break_on_initials_and_abbreviations():
    text = ("Awarded to John Clarke, Michel H. Devoret and John M. Martinis [1][6]. "
            "Dr. Smith agreed [2]. Институт им. В. П. Иванникова основан в 1994 г. [3] Он в Москве [3].")
    assert split_sentences(text) == [
        "Awarded to John Clarke, Michel H. Devoret and John M. Martinis [1][6].",
        "Dr. Smith agreed [2].",
        "Институт им. В. П. Иванникова основан в 1994 г. [3]",
        "Он в Москве [3].",
    ]


def test_split_sentences_russian_lists_and_decimals():
    text = "Байкал глубиной 1642 м [1]. Объём 23,6 тыс. км³ [2].\n\n- Впадает 300 рек [3].\n- Вытекает Ангара [3].\n## Итог"
    assert split_sentences(text) == [
        "Байкал глубиной 1642 м [1].",
        "Объём 23,6 тыс. км³ [2].",
        "Впадает 300 рек [3].",
        "Вытекает Ангара [3].",
    ]


def test_clean_answer_strips_model_markers_and_odd_spaces():
    assert clean_answer("It is 330 m tall 【source: 2】 [2].\n\n\n\nEnd.") == "It is 330 m tall [2].\n\nEnd."


def test_build_sentences_drops_out_of_range_citations():
    sentences = build_sentences("A [1][9]. B [2].", n_sources=2)
    assert [(s.text, s.citations) for s in sentences] == [("A.", [1]), ("B.", [2])]


def test_remap_citations_fact_numbers_to_source_numbers():
    # v3: facts 3 and 7 come from source 2, fact 9 from source 1
    mapping = {3: 2, 7: 2, 9: 1}
    assert remap_citations("Founded in 1994 [3][7].", mapping) == "Founded in 1994 [2]."
    assert remap_citations("Both sides [3] and [9] agree.", mapping) == "Both sides [2] and [1] agree."
    assert remap_citations("A list [3, 9] of facts.", mapping) == "A list [2][1] of facts."


def test_remap_citations_drops_invented_fact_numbers():
    assert remap_citations("An unsupported claim [42].", {1: 1}) == "An unsupported claim."
    assert remap_citations("Half supported [1][42].", {1: 3}) == "Half supported [3]."
