"""Optional resources attached to a video: links and code snippets."""

import pytest
from pydantic import ValidationError

from app.schemas.video import LinkIn, SnippetIn


def test_links_must_be_http():
    with pytest.raises(ValidationError, match="http"):
        LinkIn(kind="doc", url="javascript:alert(1)")
    with pytest.raises(ValidationError, match="http"):
        LinkIn(kind="doc", url="ftp://files.example.com")
    assert LinkIn(kind="confluence", url="  https://wiki.example.com/x  ").url == "https://wiki.example.com/x"


def test_snippet_language_is_restricted():
    assert SnippetIn(language="bash", code="ls").language == "bash"
    with pytest.raises(ValidationError):
        SnippetIn(language="Bash; DROP TABLE", code="ls")


def test_snippet_needs_code():
    with pytest.raises(ValidationError):
        SnippetIn(code="")
