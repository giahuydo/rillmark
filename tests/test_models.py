from rillmark.models import MANAGED_BY, ArticleDoc, FileStatus, RemoteFile


def make_doc(part: int = 1) -> ArticleDoc:
    return ArticleDoc(
        article_id=360051014713,
        part=part,
        slug="how-to-use-youtube-with-optisigns",
        title="How to Use YouTube with OptiSigns",
        url="https://support.optisigns.com/hc/en-us/articles/360051014713",
        section_id=26324076807315,
        source_updated_at="2026-10-26T13:22:13Z",
        markdown="# How to Use YouTube with OptiSigns\n",
        tokens=10,
    )


def test_doc_key_and_filename_unsplit() -> None:
    doc = make_doc()
    assert doc.key == "360051014713/1"
    assert doc.filename == "how-to-use-youtube-with-optisigns.md"


def test_doc_filename_for_split_part() -> None:
    assert make_doc(part=2).filename == "how-to-use-youtube-with-optisigns--p2.md"


def test_remote_file_key_requires_managed_marker() -> None:
    owned = RemoteFile(
        "file-1", FileStatus.COMPLETED, {"managed_by": MANAGED_BY, "article_id": "7"}
    )
    foreign = RemoteFile("file-2", FileStatus.COMPLETED, {"article_id": "7"})
    assert owned.managed
    assert owned.key == "7/1"
    assert not foreign.managed
    assert foreign.key is None
