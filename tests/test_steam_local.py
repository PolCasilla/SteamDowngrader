import os
import pathlib
import stat
import tempfile
import unittest

from src.steam_local import (
    parse_acf_depots,
    copy_tree_with_progress,
    freeze_app_manifest,
)


class TestSteamLocal(unittest.TestCase):
    def test_parse_acf_depots_valid(self):
        sample = """
        "AppState"
        {
            "InstalledDepots"
            {
                "582161"
                {
                    "manifest"      "899343151187474389"
                }
                "660081"
                {
                    "manifest"      "1246424898343738572"
                    "dlcappid"      "662352"
                }
            }
        }
        """
        depots = parse_acf_depots(sample)
        self.assertEqual(len(depots), 2)
        self.assertEqual(depots[0], {"id": "582161", "manifest": "899343151187474389"})
        self.assertEqual(depots[1], {"id": "660081", "manifest": "1246424898343738572"})

    def test_parse_acf_depots_empty_or_malformed(self):
        self.assertEqual(parse_acf_depots(""), [])
        self.assertEqual(parse_acf_depots('"AppState" { "appid" "582160" }'), [])

    def test_copy_tree_with_progress(self):
        with tempfile.TemporaryDirectory() as td:
            src = pathlib.Path(td) / "src"
            dst = pathlib.Path(td) / "dst"
            src.mkdir()
            (src / "sub").mkdir()

            test_payload = b"Hello world depot data" * 1024
            (src / "sub" / "file.bin").write_bytes(test_payload)
            (src / "empty.bin").write_bytes(b"")

            copy_tree_with_progress(src, dst, label="test")

            self.assertTrue((dst / "sub" / "file.bin").exists())
            self.assertEqual((dst / "sub" / "file.bin").read_bytes(), test_payload)
            self.assertTrue((dst / "empty.bin").exists())
            self.assertEqual((dst / "empty.bin").read_bytes(), b"")

    def test_copy_tree_overwrites_readonly_dest(self):
        with tempfile.TemporaryDirectory() as td:
            src = pathlib.Path(td) / "src"
            dst = pathlib.Path(td) / "dst"
            src.mkdir()
            dst.mkdir()
            (src / "read_only.bin").write_bytes(b"new content")

            target_file = dst / "read_only.bin"
            target_file.write_bytes(b"old content")
            os.chmod(target_file, stat.S_IREAD)

            try:
                copy_tree_with_progress(src, dst, label="readonly test")
                self.assertEqual(target_file.read_bytes(), b"new content")
            finally:
                os.chmod(target_file, stat.S_IWRITE)

    def test_freeze_app_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            acf_path = pathlib.Path(td) / "appmanifest_123.acf"
            acf_path.write_text('"AppState"\n{\n\t"AutoUpdateBehavior"\t\t"0"\n}\n', encoding="utf-8")

            freeze_app_manifest(acf_path)

            content = acf_path.read_text(encoding="utf-8")
            self.assertIn('"AutoUpdateBehavior"\t\t"1"', content)

            # Check that file is read-only (stat & S_IWRITE == 0 on Windows)
            mode = acf_path.stat().st_mode
            self.assertEqual(mode & stat.S_IWRITE, 0)

            # Cleanup permissions so tempdir can clean up
            os.chmod(acf_path, stat.S_IWRITE)


if __name__ == "__main__":
    unittest.main()
