"""AI writing-assist tests: output cleanup and guard rails (no model calls)."""

import pytest

from app.services.ai_assist import clean, drop_preamble, parse_tags


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('"How to fix BigQuery table creation"', "How to fix BigQuery table creation"),
        ("Here's the revised title: Kafka consumer lag", "Kafka consumer lag"),
        ("Sure! Here is a better title:\nGKE pods OOMKilled", "GKE pods OOMKilled"),
        ("Fix BigQuery table creation.", "Fix BigQuery table creation"),
        ("```\nPub/Sub redelivery\n```", "Pub/Sub redelivery"),
    ],
)
def test_clean_title_strips_model_chatter(raw, expected):
    assert clean("title", raw) == expected


def test_clean_title_is_one_line_and_bounded():
    assert clean("title", "First line\nSecond line") == "First line"
    assert len(clean("title", "x" * 500)) <= 200


def test_description_preamble_before_headings_is_dropped():
    text = "Here is a summary of the fix.\n\nProblem\nLoads timed out.\n\nFix\nMore slots."
    assert drop_preamble(text).startswith("Problem")


def test_description_without_headings_is_left_alone():
    text = "How to create a BigQuery table from the UI."
    assert drop_preamble(text) == text


def test_comment_is_an_assist_field():
    from app.services.ai_assist import FIELDS, load_prompt

    assert "comment" in FIELDS
    assert "comment" in load_prompt("comment").lower()


def test_parse_tags_normalises_and_limits():
    tags = parse_tags("BigQuery, Slot Contention, slot contention, nightly load, a, x" * 3)
    assert "bigquery" in tags and "slot-contention" in tags
    assert len(tags) <= 6
    assert all(tag == tag.lower() for tag in tags)
