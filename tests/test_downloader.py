import pathlib
import tempfile
import unittest

from src.downloader import tail_file


class TestDownloader(unittest.TestCase):
    def test_tail_file_missing(self):
        missing = pathlib.Path("does_not_exist_12345.log")
        pos, lines = tail_file(missing, 0)
        self.assertEqual(pos, 0)
        self.assertEqual(lines, [])

    def test_tail_file_normal_and_append(self):
        with tempfile.TemporaryDirectory() as td:
            log = pathlib.Path(td) / "test.log"
            log.write_text("line 1\nline 2\n", encoding="utf-8")

            pos, lines = tail_file(log, 0)
            self.assertEqual(len(lines), 2)
            self.assertEqual(lines, ["line 1", "line 2"])
            self.assertGreater(pos, 0)

            # Append more content
            with log.open("a", encoding="utf-8") as f:
                f.write("line 3\n")

            new_pos, new_lines = tail_file(log, pos)
            self.assertEqual(new_lines, ["line 3"])
            self.assertGreater(new_pos, pos)

    def test_tail_file_truncated(self):
        with tempfile.TemporaryDirectory() as td:
            log = pathlib.Path(td) / "test.log"
            log.write_text("a very long line that takes up space\n" * 10, encoding="utf-8")
            pos, lines = tail_file(log, 0)

            # Truncate file
            log.write_text("short\n", encoding="utf-8")
            reset_pos, new_lines = tail_file(log, pos)
            self.assertEqual(new_lines, ["short"])
            self.assertEqual(reset_pos, log.stat().st_size)

    def test_tail_file_filter(self):
        with tempfile.TemporaryDirectory() as td:
            log = pathlib.Path(td) / "test.log"
            log.write_text("keep: alpha\nignore: beta\nkeep: gamma\n", encoding="utf-8")

            pos, lines = tail_file(log, 0, line_filter=lambda l: "keep" in l)
            self.assertEqual(lines, ["keep: alpha", "keep: gamma"])


if __name__ == "__main__":
    unittest.main()
