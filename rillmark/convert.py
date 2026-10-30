"""Pure Zendesk HTML conversion and serialized Markdown token budgeting."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Sequence
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

import tiktoken
from bs4 import BeautifulSoup, NavigableString, Tag
from markdownify import MarkdownConverter

from rillmark.errors import ConversionError
from rillmark.models import Article, ArticleDoc

_ZERO_WIDTH: dict[int, None] = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"))
_YOUTUBE_HOSTS: set[str] = {
    "youtube.com",
    "www.youtube.com",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}


def _normalize_text(text: str) -> str:
    return unicodedata.normalize("NFC", text.replace("\u00a0", " ").translate(_ZERO_WIDTH))


def _prepare(html: str) -> BeautifulSoup:
    soup = BeautifulSoup(html, "html.parser")
    for tag in list(soup.find_all(["script", "style", "nav"])):
        tag.decompose()
    for image in soup.find_all("img"):
        if image.get("width") in {"0", "1"} and image.get("height") in {"0", "1"}:
            image.decompose()
    for text in list(soup.find_all(string=True)):
        if not text.find_parent(["pre", "code", "kbd", "samp"]):
            text.replace_with(NavigableString(_normalize_text(str(text))))
    return soup


def _language(pre: Tag) -> str:
    code = pre.find("code")
    for node in (code, pre):
        if node is not None:
            for css_class in node.get("class", []):
                if css_class.startswith("language-"):
                    return css_class.removeprefix("language-")
    return ""


class _ZendeskConverter(MarkdownConverter):
    """Adapt markdownify's block formatting to the Zendesk content contract."""

    def __init__(self, **options: object) -> None:
        super().__init__(**options)
        self.inline_code: list[str] = []

    def convert_hN(self, n: int, el: Tag, text: str, parent_tags: set[str]) -> str:  # noqa: N802
        return super().convert_hN(2 if n == 1 else n, el, text, parent_tags)

    def convert_pre(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        content = el.get_text().replace("\r\n", "\n").replace("\r", "\n")
        if not content:
            return ""
        runs = re.findall(r"`+", content)
        fence = "`" * max(3, max(map(len, runs), default=0) + 1)
        language = _language(el)
        # The closing fence needs its own line without removing any source code newlines.
        separator = "" if content.endswith("\n") else "\n"
        return f"\n\n{fence}{language}\n{content}{separator}{fence}\n\n"

    def convert_code(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        if "_noformat" in parent_tags:
            return text
        content = el.get_text().replace("\r\n", "\n").replace("\r", "\n")
        if not content:
            return ""
        runs = re.findall(r"`+", content)
        delimiter = "`" * (max(map(len, runs), default=0) + 1)
        if "`" in content:
            content = f" {content} "
        marker = f"\ue000{len(self.inline_code)}\ue001"
        self.inline_code.append(f"{delimiter}{content}{delimiter}")
        return marker

    def convert_a(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        href = el.get("href")
        if not href:
            return text
        return f"[{text.strip()}]({href})" if text.strip() else ""

    def convert_img(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        src = el.get("src", "")
        alt = el.get("alt") or PurePosixPath(unquote(urlsplit(src).path)).stem or "image"
        return f"![{_normalize_text(alt)}]({src})"

    def convert_iframe(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        src = el.get("src", "")
        parsed = urlsplit(f"https:{src}" if src.startswith("//") else src)
        if parsed.hostname and parsed.hostname.lower() in _YOUTUBE_HOSTS:
            segments = parsed.path.split("/")
            if len(segments) > 2 and segments[1] == "embed" and segments[2]:
                title = _normalize_text(el.get("title") or "embedded video")
                return f"\n\n[Video: {title}](https://www.youtube.com/watch?v={segments[2]})\n\n"
        return f"\n\n[Embedded content](<{src}>)\n\n" if src else ""

    def _render_note(self, cell: Tag) -> str | None:
        first = next(
            (
                node
                for node in cell.descendants
                if isinstance(node, NavigableString) and node.strip()
            ),
            None,
        )
        if first is None:
            return None
        label = re.match(r"(?i)^\s*note\b(?:\s*[:\-]|\s+)", str(first))
        if label is None:
            return None
        # Work on a detached copy so NOTE label removal never changes the input tree.
        clone = BeautifulSoup(str(cell), "html.parser").find(cell.name)
        if clone is None:
            return None
        first_copy = next(
            node for node in clone.descendants if isinstance(node, NavigableString) and node.strip()
        )
        first_copy.replace_with(str(first_copy)[label.end() :])
        for wrapper in list(clone.find_all(["strong", "b"])):
            if not wrapper.get_text(strip=True) and not wrapper.find(["img", "code", "pre"]):
                wrapper.decompose()
        rendered = "".join(
            self.process_element(child, parent_tags=set()) for child in clone.children
        )
        lines = rendered.strip(" \n").splitlines()
        if not lines:
            return "\n\n> **Note:**\n\n"
        if lines[0].startswith("```"):
            quoted = ["> **Note:**", *[f"> {line}" if line else ">" for line in lines]]
        else:
            quoted = [
                f"> **Note:** {lines[0]}",
                *[f"> {line}" if line else ">" for line in lines[1:]],
            ]
        return f"\n\n{'\n'.join(quoted)}\n\n"

    def convert_table(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        rows = el.find_all("tr")
        if len(rows) == 1:
            cells = rows[0].find_all(["td", "th"])
            if len(cells) == 1:
                note = self._render_note(cells[0])
                if note is not None:
                    return note
        if any(
            cell.get("colspan", "1") != "1" or cell.get("rowspan", "1") != "1"
            for cell in el.find_all(["td", "th"])
        ):
            plain_rows = []
            for row in rows:
                cells = row.find_all(["td", "th"], recursive=False)
                parts = [_normalize_text(cell.get_text(" ", strip=True)) for cell in cells]
                plain_rows.append(" | ".join(parts))
            return f"\n\n{'\n'.join(plain_rows)}\n\n"
        return super().convert_table(el, text, parent_tags)

    def convert_figure(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        return f"\n\n{text.strip()}\n\n" if text.strip() else ""


def _clean_markdown(text: str) -> str:
    # Fenced blocks retain their original whitespace; outside lines become hash-stable.
    result: list[str] = []
    fence_length = 0
    blank_count = 0
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        fence = re.match(r"^\s*(?:(?:>|[*+-]|\d+\.)\s*)*(`{3,})([^`\s]*)\s*$", line)
        if fence and (
            not fence_length or (not fence.group(2) and len(fence.group(1)) >= fence_length)
        ):
            fence_length = len(fence.group(1)) if not fence_length else 0
            blank_count = 0
        elif not fence_length:
            line = line.rstrip()
            if not line:
                blank_count += 1
                if blank_count > 1:
                    continue
            else:
                blank_count = 0
        else:
            blank_count = 0
        result.append(line)
    return "\n".join(result).strip("\n") + "\n"


def html_to_markdown(html: str) -> str:
    """Convert article body HTML to stable Markdown with one final LF."""
    converter = _ZendeskConverter(
        heading_style="ATX",
        autolinks=False,
        code_language_callback=_language,
        strip_pre=None,
    )
    result = _clean_markdown(converter.convert_soup(_prepare(html)))
    for index, code in enumerate(converter.inline_code):
        result = result.replace(f"\ue000{index}\ue001", code)
    return result


def count_tokens(text: str) -> int:
    """Count o200k_base tokens in a complete serialized Markdown file."""
    return len(tiktoken.get_encoding("o200k_base").encode_ordinary(text))


def make_slug(title: str) -> str:
    """Return an ASCII lowercase kebab slug no longer than 80 characters."""
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")[:80].rstrip("-")


def build_docs(
    articles: Sequence[Article],
    max_tokens: int,
    count: Callable[[str], int] = count_tokens,
) -> list[ArticleDoc]:
    """Serialize one complete file per article or raise on an oversize file."""
    slugs = [make_slug(article.title) or f"article-{article.id}" for article in articles]
    duplicates = Counter(slugs)
    docs: list[ArticleDoc] = []
    reserved = {slug for slug in slugs if duplicates[slug] == 1}
    used: set[str] = set()
    for article, slug in zip(articles, slugs, strict=True):
        if duplicates[slug] > 1:
            base = slug
            suffix = f"-{article.id}"
            slug = f"{base[: 80 - len(suffix)].rstrip('-')}{suffix}"
            while slug in reserved or slug in used:
                suffix += f"-{article.id}"
                slug = f"{base[: 80 - len(suffix)].rstrip('-')}{suffix}"
        used.add(slug)
        soup = BeautifulSoup(article.body_html, "html.parser")
        for code in soup.find_all(["pre", "code"]):
            if code.find_parent("pre") and code.name == "code":
                continue
            if any(
                line.lstrip().startswith("Article URL:") for line in code.get_text().splitlines()
            ):
                raise ConversionError(f"Article {article.id} has a citation marker inside code")
        body = html_to_markdown(article.body_html)
        body = "\n".join(
            f"Article\\ URL:{line[len('Article URL:') :]}"
            if line.startswith("Article URL:")
            else line
            for line in body.split("\n")
        )
        header = f"# {article.title}\n\nArticle URL: {article.html_url}\n\n"
        markdown = (header + body).rstrip("\n") + "\n"
        citation_lines = [line for line in markdown.splitlines() if line.startswith("Article URL:")]
        if citation_lines != [f"Article URL: {article.html_url}"]:
            raise ConversionError(f"Article {article.id} has an invalid citation header")
        tokens = count(markdown)
        if tokens > max_tokens:
            raise ConversionError(
                f"Article {article.id} serialized size {tokens} tokens exceeds {max_tokens}"
            )
        docs.append(
            ArticleDoc(
                article_id=article.id,
                part=1,
                slug=slug,
                title=article.title,
                url=article.html_url,
                section_id=article.section_id,
                source_updated_at=article.updated_at,
                markdown=markdown,
                tokens=tokens,
            )
        )
    return docs
