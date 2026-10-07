"""Checks the parts of the feature page generator that decide what search sees.

scripts/generate_features.py rebuilds every page under
v3/expert-models/features/ each day from the /v3/info API, so a rule about
those pages has to live in the generator: an edit to a page is gone by the
next run. Two of its outputs reach Google directly. The page description is
the snippet under the search result, and a page the API drops leaves a URL
behind that Google has indexed. These tests cover both and make no requests.
"""

import json

from scripts import generate_features as gen
from tests.page_metadata import frontmatter, schema_props

FEATURES = [{"name": "text", "subfeatures": [{"name": "moderation"}]}]


# --- the page -------------------------------------------------------------


def test_a_generated_page_gives_its_structured_data_the_same_title(
    tmp_path, monkeypatch
):
    """The search title carries "API", in the frontmatter and in <TechArticleSchema> alike."""
    monkeypatch.setattr(gen, "FEATURES_DIR", tmp_path)
    subfeature = {
        "name": "moderation",
        "fullname": "Text Moderation",
        "description": "Scan text for offensive content.",
    }
    page = tmp_path / "page.mdx"
    page.write_text(gen.generate_subfeature_page("text", subfeature, {}, "Text"))

    meta, schema = frontmatter(page), schema_props(page)

    assert meta["title"] == "Text Moderation API"
    assert meta["sidebarTitle"] == "Text Moderation"
    assert schema["title"] == meta["title"]
    assert schema["description"] == meta["description"]


# --- the description ------------------------------------------------------


def test_e_g_does_not_end_a_sentence():
    """An abbreviation once cut a published description off at "(e.g."."""
    text = "Compare two faces. The first is the reference (e.g. an ID) and the other a selfie."

    assert gen.truncate_at_sentence(text, 60) == "Compare two faces."


def test_a_capitalised_e_g_does_not_end_a_sentence_either():
    text = (
        "Works on scanned documents. E.g. passports, "
        + "ID cards, " * 20
        + "and licences."
    )

    assert len(text) > gen.PAGE_DESCRIPTION_MAX
    assert gen.page_description(text) == "Works on scanned documents."


def test_a_page_description_ends_at_the_last_sentence_that_fits():
    first = "Detect deepfake and synthetically manipulated video."
    second = " Returns an overall score and a prediction for each frame."
    third = (
        " It also reports"
        + " the score of each frame," * 6
        + " when the provider has one."
    )

    assert gen.page_description(first + second + third) == first + second


def test_a_first_sentence_too_long_to_fit_is_kept_whole_rather_than_cut():
    """Google adds its own ellipsis to a long description; a cut one just reads as broken."""
    sentence = "Named Entity Recognition identifies " + "entities, " * 30 + "and dates."

    assert len(sentence) > 200
    assert gen.page_description(sentence) == sentence


def test_the_note_on_allowed_file_types_is_left_out():
    text = "Face Detection finds the faces in an image (type of file allowed: jpg, jpeg, png)"

    assert gen.page_description(text) == "Face Detection finds the faces in an image."


def test_a_description_with_no_full_stop_gets_one():
    text = "The Plagiarism Detection API scans a text for plagiarism"

    assert gen.page_description(text) == text + "."


# --- the redirects --------------------------------------------------------


def test_cleanup_reports_each_page_it_deletes(tmp_path, monkeypatch):
    features_dir = tmp_path / "v3" / "expert-models" / "features"
    (features_dir / "text").mkdir(parents=True)
    for name in ("index.mdx", "text/moderation.mdx", "text/old-thing.mdx"):
        (features_dir / name).write_text("---\n---\n")
    monkeypatch.setattr(gen, "DOCS_ROOT", tmp_path)
    monkeypatch.setattr(gen, "FEATURES_DIR", features_dir)

    removed = gen.cleanup_stale_pages(FEATURES)

    assert removed == ["v3/expert-models/features/text/old-thing"]
    assert not (features_dir / "text" / "old-thing.mdx").exists()
    assert (features_dir / "text" / "moderation.mdx").exists()


def test_a_deleted_page_redirects_to_the_features_index():
    redirects = gen.updated_redirects(
        [], removed=["v3/expert-models/features/text/old-thing"], generated=set()
    )

    assert redirects == [
        {
            "source": "/v3/expert-models/features/text/old-thing",
            "destination": "/v3/expert-models/features",
        }
    ]


def test_a_redirect_is_not_added_twice_and_others_are_kept():
    existing = [
        {"source": "/v2", "destination": "/index"},
        {
            "source": "/v3/expert-models/features/text/old-thing",
            "destination": "/v3/expert-models/features",
        },
    ]

    redirects = gen.updated_redirects(
        existing, removed=["v3/expert-models/features/text/old-thing"], generated=set()
    )

    assert redirects == existing


def test_a_page_the_api_brings_back_loses_its_redirect():
    """Otherwise the redirect would shadow the live page."""
    existing = [
        {"source": "/v2", "destination": "/index"},
        {
            "source": "/v3/expert-models/features/text/moderation",
            "destination": "/v3/expert-models/features",
        },
    ]

    redirects = gen.updated_redirects(
        existing, removed=[], generated=gen.generated_pages(FEATURES)
    )

    assert redirects == [{"source": "/v2", "destination": "/index"}]


def test_docs_json_gets_the_redirects_for_the_pages_cleanup_deleted(
    tmp_path, monkeypatch
):
    docs_json = tmp_path / "docs.json"
    expert = {"group": "Expert Models", "pages": ["v3/expert-models/webhooks"]}
    docs_json.write_text(
        json.dumps(
            {
                "redirects": [{"source": "/v2", "destination": "/index"}],
                "navigation": {
                    "versions": [{"version": "V3", "tabs": [{"groups": [expert]}]}]
                },
            }
        )
    )
    monkeypatch.setattr(gen, "DOCS_JSON_PATH", docs_json)

    gen.update_docs_json(FEATURES, removed=["v3/expert-models/features/text/old-thing"])

    assert json.loads(docs_json.read_text())["redirects"] == [
        {"source": "/v2", "destination": "/index"},
        {
            "source": "/v3/expert-models/features/text/old-thing",
            "destination": "/v3/expert-models/features",
        },
    ]
