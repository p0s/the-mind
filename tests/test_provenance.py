import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


from _core.provenance import format_src_comment, parse_src_comment_payload, strip_src_comment_eol  # noqa: E402


class TestProvenance(unittest.TestCase):
    def test_parse_single_ref(self) -> None:
        c = parse_src_comment_payload("yt_abc @ 00:01:02")
        assert c is not None
        self.assertEqual(c.refs, (("yt_abc", "00:01:02"),))
        self.assertEqual(c.meta_dict, {})

    def test_parse_single_pdf_page_ref(self) -> None:
        c = parse_src_comment_payload("web_x @ p16")
        assert c is not None
        self.assertEqual(c.refs, (("web_x", "p16"),))

    def test_parse_single_pdf_page_ref_normalizes(self) -> None:
        c = parse_src_comment_payload("web_x @ P.016")
        assert c is not None
        self.assertEqual(c.refs, (("web_x", "p16"),))

    def test_parse_single_pdf_page_range_normalizes(self) -> None:
        c = parse_src_comment_payload("web_x @ p19–20")
        assert c is not None
        self.assertEqual(c.refs, (("web_x", "p19-20"),))

    def test_parse_multi_ref_with_meta(self) -> None:
        c = parse_src_comment_payload("yt_abc @ 00:01:02; ccc_def @ 00:03:04 | auto=needs_review score=0")
        assert c is not None
        self.assertEqual(
            c.refs,
            (
                ("yt_abc", "00:01:02"),
                ("ccc_def", "00:03:04"),
            ),
        )
        self.assertEqual(c.meta_dict.get("auto"), "needs_review")
        self.assertEqual(c.meta_dict.get("score"), "0")

    def test_strip_src_comment_eol(self) -> None:
        text, c = strip_src_comment_eol("Hello world <!-- src: yt_abc @ 00:01:02 -->")
        self.assertEqual(text, "Hello world")
        assert c is not None
        self.assertEqual(c.refs, (("yt_abc", "00:01:02"),))

    def test_strip_src_comment_not_eol(self) -> None:
        text, c = strip_src_comment_eol("Hello <!-- src: yt_abc @ 00:01:02 --> world")
        self.assertEqual(text, "Hello <!-- src: yt_abc @ 00:01:02 --> world")
        self.assertIsNone(c)

    def test_format_is_canonical(self) -> None:
        s = format_src_comment([("yt_abc", "00:01:02"), ("ccc_def", "00:03:04")], meta={"auto": "needs_review", "score": "0"})
        self.assertEqual(s, "<!-- src: yt_abc @ 00:01:02; ccc_def @ 00:03:04 | auto=needs_review score=0 -->")

    def test_format_normalizes_pdf_locator(self) -> None:
        s = format_src_comment([("web_x", "P.016")])
        self.assertEqual(s, "<!-- src: web_x @ p16 -->")


if __name__ == "__main__":
    unittest.main()
