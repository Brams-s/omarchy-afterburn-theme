"""uninstall.sh removes cursor-fx when Afterburn installed it, if you say so (issue #5 follow-up).

The proof that Afterburn installed it is its checkout in ~/.local/share/afterburn/ghostty-cursor-fx. Everything
removed is moved into ~/.local/state/afterburn/cursor-fx-removed-<time>/, so it can be put back.
"""
import subprocess
import unittest

try:
    from support import UNINSTALL, Sandbox
except ImportError:
    from tests.support import UNINSTALL, Sandbox

CONFIG = """font-size = 12
# Cursor effect preset from cursor-effects/ (switch with `cursor-fx <name>`, list with `cursor-fx`).
# cursor-fx-panes = on (`cursor-fx panes on|off`: Claude Code in herdr or tmux panes)
config-file = cursor-effects/embers.conf
theme = dark
"""


class UninstallCursorFx(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.cleanup)
        h = self.sb.home
        self.checkout = h / ".local/share/afterburn/ghostty-cursor-fx"
        self.ghostty = h / ".config/ghostty"
        for sub, names in (("shaders", ("embers.glsl", "rain.glsl")), ("cursor-effects", ("embers.conf", "rain.conf"))):
            for n in names:
                self.sb.write_state_text(self.checkout / sub / n, f"// shipped {n}\n")
                self.sb.write_state_text(self.ghostty / sub / n, f"// installed {n}\n")
        self.sb.write_state_text(self.checkout / "bin/cursor-fx", "#!/usr/bin/env python3\n# v1\n")
        self.sb.write_state_text(h / ".local/bin/cursor-fx", "#!/usr/bin/env python3\n# v2, upgraded itself\n")
        self.sb.write_state_text(self.ghostty / "config", CONFIG)
        self.pi = h / ".pi/agent/extensions/cursor-fx.ts"
        self.sb.write_state_text(self.pi, "// pi\n")

    def uninstall(self, *args, answer=None, **env):
        r = subprocess.run(["/bin/bash", str(UNINSTALL), *args], env=self.sb.env(**env), capture_output=True, text=True,
                           timeout=60, input=answer if answer is not None else None,
                           stdin=None if answer is not None else subprocess.DEVNULL)
        return r

    def backup(self):
        found = list((self.sb.state_dir).glob("cursor-fx-removed-*"))
        self.assertEqual(len(found), 1, found)
        return found[0]

    def assert_removed(self, r):
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.sb.home / ".local/bin/cursor-fx").exists(), "an upgraded binary goes too")
        self.assertFalse((self.ghostty / "shaders").exists())
        self.assertFalse((self.ghostty / "cursor-effects").exists())
        self.assertEqual((self.ghostty / "config").read_text(), "font-size = 12\ntheme = dark\n")
        self.assertFalse(self.pi.exists())
        bak = self.backup()
        self.assertEqual((bak / "ghostty-config").read_text(), CONFIG)
        self.assertEqual((bak / "shaders/embers.glsl").read_text(), "// installed embers.glsl\n")
        self.assertTrue((bak / "cursor-fx").exists())
        self.assertTrue((bak / "pi-extension-cursor-fx.ts").exists())
        self.assertIn("✓ cursor-fx removed", r.stdout)
        self.assertIn("cursor-fx off", self.sb.call_log())
        self.assertFalse(self.checkout.exists())

    def test_yes_removes_it_into_a_backup(self):
        self.assert_removed(self.uninstall(answer="y\n"))

    def test_enter_means_yes(self):
        self.assert_removed(self.uninstall(answer="\n"))

    def test_the_flag_removes_it_without_asking(self):
        self.assert_removed(self.uninstall("--remove-cursor-fx"))

    def test_no_keeps_it(self):
        r = self.uninstall(answer="n\n")
        self.assert_kept(r)

    def test_no_terminal_keeps_it(self):
        self.assert_kept(self.uninstall())

    def test_keep_flag_keeps_it(self):
        self.assert_kept(self.uninstall("--keep-cursor-fx", answer="y\n"))

    def assert_kept(self, r):
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.sb.home / ".local/bin/cursor-fx").exists())
        self.assertTrue((self.ghostty / "shaders/embers.glsl").exists())
        self.assertEqual(list(self.sb.state_dir.glob("cursor-fx-removed-*")), [])
        self.assertTrue(self.checkout.exists(), "kept, so a later --remove-cursor-fx still knows the files")
        self.assertIn("--remove-cursor-fx", r.stdout)
        # ...and that later run does remove it.
        self.assert_removed(self.uninstall("--remove-cursor-fx"))

    def test_your_own_shader_stays(self):
        self.sb.write_state_text(self.ghostty / "shaders/mine.glsl", "// mine\n")
        r = self.uninstall("--remove-cursor-fx")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.ghostty / "shaders/mine.glsl").read_text(), "// mine\n")
        self.assertFalse((self.ghostty / "shaders/embers.glsl").exists())
        self.assertIn("kept 1 file(s) of your own", r.stdout)

    def test_cursor_fx_you_had_before_is_never_touched(self):
        import shutil
        shutil.rmtree(self.checkout)
        r = self.uninstall("--remove-cursor-fx")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((self.sb.home / ".local/bin/cursor-fx").exists())
        self.assertEqual((self.ghostty / "config").read_text(), CONFIG)
        self.assertEqual(list(self.sb.state_dir.glob("cursor-fx-removed-*")), [])

    def test_a_different_xdg_data_home_still_finds_the_checkout(self):  # PR #8 review
        other = self.sb.root / "elsewhere"
        other.mkdir()
        self.assert_removed(self.uninstall("--remove-cursor-fx", XDG_DATA_HOME=str(other)))

    def test_a_failed_removal_keeps_the_checkout_so_a_retry_finishes_it(self):  # PR #8 review
        import shutil as sh
        real = sh.which("mv")
        flag = self.sb.root / "mv-fails"
        flag.touch()
        stub = self.sb.bin / "mv"
        stub.unlink()
        stub.write_text(f'''#!/bin/bash
if [[ -e {flag} && $* == *.local/bin/cursor-fx* ]]; then echo "mv: boom" >&2; exit 1; fi
exec {real} "$@"
''')
        stub.chmod(0o755)
        r = self.uninstall("--remove-cursor-fx")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("not fully removed", r.stdout)
        self.assertTrue(self.checkout.exists(), "the checkout names what is left to remove")
        self.assertTrue((self.sb.home / ".local/bin/cursor-fx").exists())
        flag.unlink()
        r = self.uninstall("--remove-cursor-fx")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("✓ cursor-fx removed", r.stdout)
        self.assertFalse((self.sb.home / ".local/bin/cursor-fx").exists())
        self.assertFalse(self.checkout.exists())

    def test_assets_beside_a_symlinked_config_are_found(self):  # PR #8 review
        import shutil as sh
        dots = self.sb.home / "dotfiles/ghostty"
        dots.parent.mkdir(parents=True)
        sh.move(str(self.ghostty), str(dots))
        self.ghostty.mkdir()
        (self.ghostty / "config").symlink_to(dots / "config")
        r = self.uninstall("--remove-cursor-fx")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((dots / "shaders").exists(), r.stdout)
        self.assertFalse((dots / "cursor-effects").exists())
        self.assertEqual((dots / "config").read_text(), "font-size = 12\ntheme = dark\n")
        self.assertTrue((self.ghostty / "config").is_symlink())

    def test_unknown_argument_changes_nothing(self):
        r = self.uninstall("--bogus")
        self.assertEqual(r.returncode, 2)
        self.assertTrue((self.sb.home / ".local/bin/cursor-fx").exists())


if __name__ == "__main__":
    unittest.main()
