"""Offline conversion and serialized file budget contract tests."""

import unicodedata
from pathlib import Path

import pytest

from rillmark.convert import build_docs, count_tokens, html_to_markdown, make_slug
from rillmark.errors import ConversionError
from rillmark.models import Article

FIXTURES: Path = Path(__file__).parent / "fixtures" / "html"


def article(article_id: int, title: str = "Example", body: str = "<p>Body</p>") -> Article:
    """Build a minimal Zendesk article for converter tests."""
    return Article(
        id=article_id,
        title=title,
        body_html=body,
        html_url=f"https://support.optisigns.com/hc/en-us/articles/{article_id}",
        section_id=1,
        locale="en-us",
        draft=False,
        updated_at="2026-10-30T00:00:00Z",
    )


def test_media_keeps_figure_links_images_and_embed_destinations() -> None:
    html = (FIXTURES / "media.html").read_text()
    result = html_to_markdown(html)
    assert "![photo](/attachments/photo.png)" in result
    assert "A caption" in result
    assert "[Video: Walkthrough](https://www.youtube.com/watch?v=GyWZd10ure0)" in result
    assert "[Embedded content](<https://www.canva.com/design/example>)" in result
    assert "[Jump](#Needed)" in result
    assert "[Relative](/hc/en-us/articles/example)" in result


def test_video_without_title_and_non_youtube_iframe() -> None:
    html = (
        '<iframe src="https://www.youtube.com/embed/abc-12"></iframe>'
        '<iframe src="//fast.wistia.net/embed/abc"></iframe>'
    )
    result = html_to_markdown(html)
    assert "[Video: embedded video](https://www.youtube.com/watch?v=abc-12)" in result
    assert "[Embedded content](<//fast.wistia.net/embed/abc>)" in result


def test_note_table_and_named_anchor_keep_content() -> None:
    result = html_to_markdown((FIXTURES / "note.html").read_text())
    assert "> **Note:** Keep this warning." in result
    assert "Anchor text" in result
    assert "name=" not in result


def test_code_and_unicode_are_normalized_only_outside_code() -> None:
    result = html_to_markdown((FIXTURES / "code.html").read_text())
    assert "## Body title" in result
    assert "café text" in result
    assert '```python\nx = "a\u00a0b"\n  y = 2\n```' in result
    assert "`a\u00a0b`" in result
    assert "\u200b" not in result


def test_tables_support_headers_without_merges() -> None:
    html = "<table><tr><th>Key</th><th>Value</th></tr><tr><td>A</td><td>B</td></tr></table>"
    result = html_to_markdown(html)
    assert "| Key | Value |" in result
    assert "| --- | --- |" in result


def test_merged_colspan_uses_exact_plain_rows() -> None:
    html = "<table><tr><th>Key</th><th>Value</th></tr><tr><td colspan='2'>Both</td></tr></table>"
    assert html_to_markdown(html) == "Key | Value\nBoth\n"


def test_merged_rowspan_uses_exact_plain_rows() -> None:
    html = (
        "<table><tr><td rowspan='2'>Shared</td><td>First</td></tr><tr><td>Second</td></tr></table>"
    )
    assert html_to_markdown(html) == "Shared | First\nSecond\n"


def test_quote_cleanup_and_wrappers_preserve_nonempty_content() -> None:
    html = (
        "<script>secret</script><style>css</style><nav>menu</nav>"
        "<div class='x'><span>Keep</span><blockquote>Important\nline</blockquote></div>"
        "<img src='track.gif' width='1' height='1'>"
    )
    result = html_to_markdown(html)
    assert "Keep" in result
    assert "> Important" in result
    assert "secret" not in result
    assert "css" not in result
    assert "menu" not in result
    assert "track.gif" not in result
    assert result.endswith("\n") and not result.endswith("\n\n")
    assert "\n\n\n" not in result


def test_code_blank_lines_and_zero_width_are_preserved_inside_fences() -> None:
    html = "<pre><code>alpha\n\n\n\nbeta\u200b  \n</code></pre><p>after\u200b</p>"
    result = html_to_markdown(html)
    assert "alpha\n\n\n\nbeta\u200b  \n" in result
    assert "after\u200b" not in result
    assert "\n\n\n" not in result.split("```")[-1]


def test_conversion_is_byte_identical_for_same_html() -> None:
    html = (FIXTURES / "media.html").read_text()
    assert html_to_markdown(html).encode() == html_to_markdown(html).encode()


def test_slug_is_ascii_kebab_with_eighty_character_limit() -> None:
    assert make_slug("Café & YouTube: Setup!") == "cafe-youtube-setup"
    assert len(make_slug("A " * 100)) <= 80


def test_build_docs_serializes_one_header_url_and_counts_entire_file() -> None:
    source = article(42, body="<h1>Intro</h1><p>Body</p>")
    observed: list[str] = []

    def fake_count(text: str) -> int:
        observed.append(text)
        return len(text)

    doc = build_docs([source], 1000, count=fake_count)[0]
    assert doc.markdown.startswith(f"# Example\n\nArticle URL: {source.html_url}\n\n")
    assert doc.markdown.count("Article URL:") == 1
    assert doc.markdown == observed[0]
    assert doc.tokens == len(doc.markdown)
    assert doc.part == 1 and doc.filename == "example.md"


def test_slug_collision_appends_id_only_to_colliding_articles() -> None:
    docs = build_docs([article(1, "Café"), article(2, "Cafe")], 1000, count=len)
    assert [doc.filename for doc in docs] == ["cafe-1.md", "cafe-2.md"]


def test_slug_collision_avoids_existing_id_suffixed_title() -> None:
    docs = build_docs(
        [article(1, "Cafe"), article(2, "Cafe"), article(3, "Cafe 1")],
        1000,
        count=len,
    )
    assert len({doc.filename for doc in docs}) == 3


def test_slug_collision_keeps_long_filenames_under_eighty_chars() -> None:
    title = "A" * 100
    docs = build_docs([article(1, title), article(22, title)], 1000, count=len)
    assert len(docs[0].slug) <= 80 and len(docs[1].slug) <= 80
    assert docs[0].slug.endswith("-1") and docs[1].slug.endswith("-22")


def test_oversize_article_raises_without_truncation() -> None:
    with pytest.raises(ConversionError, match=r"42.*1001"):
        build_docs([article(42)], 1000, count=lambda _: 1001)


def test_count_tokens_uses_o200k_encoding() -> None:
    assert count_tokens("Hello world") == 2


# Independent TASK-727 review probes, retained as focused offline regressions.
@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<p><code>a  b</code></p>", "`a  b`"),
        ("<pre><code>\nfirst\n\n</code></pre>", "```\n\nfirst\n\n"),
        ("<ul><li><pre><code>first  \n\n\n\nlast  </code></pre></li></ul>", "first  "),
    ],
)
def test_preserve_code_whitespace(html: str, expected: str) -> None:
    assert expected in html_to_markdown(html)


def test_fence_nested_in_quote_preserves_code_whitespace() -> None:
    html = "<blockquote><pre><code>first  \n\n\n\nlast  </code></pre></blockquote>"
    markdown = html_to_markdown(html)
    assert "> first  \n>\n>\n>\n> last  " in markdown
    assert markdown.endswith("\n")


def test_fence_does_not_close_on_literal_backticks() -> None:
    markdown = html_to_markdown("<pre><code>first\n```\nx  \n</code></pre>")
    assert markdown.splitlines()[0] == "````"
    assert "first\n```\nx  \n````" in markdown


def test_note_keeps_link_and_image() -> None:
    html = '<table><tr><td>NOTE: <a href="/guide">Guide</a><img src="/step.png"></td></tr></table>'
    markdown = html_to_markdown(html)
    assert markdown == "> **Note:** [Guide](/guide)![step](/step.png)\n"


def test_note_multiline_prefixes_each_line() -> None:
    html = "<table><tr><td>NOTE: First<br>Second</td></tr></table>"
    assert html_to_markdown(html) == "> **Note:** First\n> Second\n"


@pytest.mark.parametrize("word", ["Notebook setup", "Noteworthy detail"])
def test_notebook_is_not_a_note_prefix(word: str) -> None:
    assert word in html_to_markdown(f"<table><tr><td>{word}</td></tr></table>")


def test_merged_cells_use_plain_rows() -> None:
    html = '<table><tr><th>A</th><th>B</th></tr><tr><td colspan="2">Both</td></tr></table>'
    assert html_to_markdown(html) == "A | B\nBoth\n"


def test_attribute_prose_is_normalized() -> None:
    markdown = html_to_markdown('<img src="/image.png" alt="cafe\u0301\u00a0name\u200b">')
    assert unicodedata.is_normalized("NFC", markdown)
    assert "\u00a0" not in markdown and "\u200b" not in markdown
    assert "![café name](/image.png)" in markdown
    fallback = html_to_markdown('<img src="/cafe\u0301\u00a0name\u200b.png">')
    assert "![café name](/cafe\u0301\u00a0name\u200b.png)" in fallback


def test_serialized_doc_has_exactly_one_citation_line() -> None:
    source = article(42, body="<p>Article URL: https://other.invalid/article</p>")
    markdown = build_docs([source], 4096, count=len)[0].markdown
    assert [line for line in markdown.splitlines() if line.startswith("Article URL:")] == [
        f"Article URL: {source.html_url}"
    ]
    assert "Article\\ URL: https://other.invalid/article" in markdown


def test_empty_body_doc_has_one_final_newline() -> None:
    markdown = build_docs([article(42, body="")], 4096, count=len)[0].markdown
    assert markdown.endswith("\n") and not markdown.endswith("\n\n")


def test_special_token_text_is_counted_as_literal_content() -> None:
    assert count_tokens("<|endoftext|>") > 0
    docs = build_docs([article(42, body="<pre><code><|endoftext|></code></pre>")], 4096)
    assert docs[0].tokens == count_tokens(docs[0].markdown)


# TASK-728 review probes: all seven cases are tracked as offline tests.
@pytest.mark.parametrize(
    "html",
    [
        (
            "<blockquote><blockquote><pre><code>first  \n\n\n\n  last  "
            "</code></pre></blockquote></blockquote>"
        ),
        '<pre><code class="language-c#">first  \n\n\n\n  last  </code></pre>',
        "<p><code>first  \n  last  </code></p>",
    ],
)
def test_code_spaces_survive_all_supported_contexts(html: str) -> None:
    assert "first  \n" in html_to_markdown(html)


def test_note_fenced_code_keeps_source_spaces() -> None:
    html = "<table><tr><td>NOTE: <pre><code>first  \n\n  last  </code></pre></td></tr></table>"
    markdown = html_to_markdown(html)
    assert "> first  \n" in markdown
    assert ">   last  \n" in markdown


@pytest.mark.parametrize("padding", ["", "\n"])
def test_note_formatted_label_is_removed_once(padding: str) -> None:
    html = f"<table><tr><td>{padding}<strong>NOTE:</strong> First<br>Second</td></tr></table>"
    assert html_to_markdown(html) == "> **Note:** First\n> Second\n"


def test_serialization_does_not_edit_code_to_escape_citation_marker() -> None:
    source = article(42, body="<pre><code>Article URL: https://other.invalid\n</code></pre>")
    with pytest.raises(ConversionError, match=r"42.*citation"):
        build_docs([source], 4096)
