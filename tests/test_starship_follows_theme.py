"""The subtle pack's red error symbol is Afterburn's: other themes get your own back (issue #5 follow-up)."""
import os
import unittest

try:
    from support import REPO, THEME_SH, UNINSTALL, Sandbox
except ImportError:
    from tests.support import REPO, THEME_SH, UNINSTALL, Sandbox

HOOK = REPO / "extras" / "afterburn-theme-set-hook"
OURS = 'error_symbol = "[❯](bold red)"'


class StarshipFollowsTheme(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox("alice")
        self.addCleanup(self.sb.cleanup)
        self.starship = self.sb.home / ".config" / "starship.toml"

    def install_symbol(self, text):
        """What install.sh does: remember the original line, then put ours in."""
        self.sb.write_state_text(self.starship, text)
        r = self.sb.run(["/bin/bash", "-c", f'source "{THEME_SH}"; ab_starship_record && ab_starship_apply'])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(OURS, self.starship.read_text())

    def hook(self, theme):
        self.sb.write_state_text(self.sb.home / ".local/state/omarchy/current/theme.name", theme)
        r = self.sb.run(["/bin/bash", str(HOOK), theme])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return self.starship.read_text()

    def test_a_hook_that_goes_stale_while_waiting_changes_nothing(self):  # PR #8 review
        import fcntl, subprocess, time
        original = '[character]\nerror_symbol = "[x](red)"\n'
        self.install_symbol(original)
        self.assertEqual(self.hook("nord"), original)
        self.sb.write_state_text(self.sb.marker, "clone_id=afterburn.lock\n")
        self.sb.write_state_text(self.sb.state_dir / "lock-parked", "")
        name = self.sb.home / ".local/state/omarchy/current/theme.name"
        self.sb.write_state_text(name, "afterburn")
        self.sb.calls.write_text("")
        lck = open(self.sb.state_dir / "lock-embers.lck", "w")
        self.addCleanup(lck.close)
        fcntl.flock(lck, fcntl.LOCK_EX)
        p = subprocess.Popen(["/bin/bash", str(HOOK), "afterburn"], env=self.sb.env(),
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(1.0)                      # the hook is now waiting for the lock in lock-embers.sh
        name.write_text("nord")              # meanwhile you picked nord
        fcntl.flock(lck, fcntl.LOCK_UN)
        out, _ = p.communicate(timeout=60)
        self.assertEqual(self.starship.read_text(), original, out)
        self.assertFalse([c for c in self.sb.call_log() if c.startswith(("cursor-fx", "afterburn ", "systemctl"))],
                         self.sb.call_log())

    def round_trip(self, original):
        self.install_symbol(original)
        on = self.starship.read_text()
        self.assertEqual(on.count("error_symbol"), original.count("error_symbol") or 1, on)
        self.assertEqual(self.hook("nord"), original)
        self.hook("afterburn")
        self.assertEqual(self.hook("nord"), original)

    def test_an_indented_error_symbol_is_replaced_not_duplicated(self):  # PR #8 review
        self.round_trip('[character]\n  success_symbol = "[>](green)"\n  error_symbol = "[x](red)"\n')

    def test_the_same_line_in_another_section_is_left_alone(self):  # Codex review C6
        self.round_trip('[status]\nerror_symbol = "[❯](bold red)"\n\n[character]\nerror_symbol = "[x](red)"\n')

    def test_a_character_section_afterburn_added_goes_again(self):  # Codex review C6
        self.round_trip('format = "$all"\n')

    def test_round_trip_gives_back_your_file(self):
        original = 'format = "$all"\n\n[character]\nsuccess_symbol = "[❯](bold green)"\nerror_symbol = "[✗](bold red)"\n'
        self.install_symbol(original)
        self.assertEqual(self.hook("nord"), original)
        self.assertIn(OURS, self.hook("afterburn"))
        self.assertEqual(self.hook("catppuccin"), original)
        r = self.sb.run(["/bin/bash", str(UNINSTALL)])
        self.assertEqual(self.starship.read_text(), original, r.stdout + r.stderr)

    def test_uninstall_on_afterburn_restores_it(self):
        original = '[character]\nerror_symbol = "[x](red)"\n'
        self.install_symbol(original)
        r = self.sb.run(["/bin/bash", str(UNINSTALL)])
        self.assertEqual(self.starship.read_text(), original)
        self.assertIn("✓ starship error_symbol restored", r.stdout)

    def test_edition_switches_never_rewrite_the_file(self):
        self.install_symbol('[character]\nerror_symbol = "[x](red)"\n')
        self.hook("afterburn")
        os.utime(self.starship, (1_000_000_000, 1_000_000_000))
        self.hook("afterburn-redline")
        self.hook("afterburn")
        self.assertEqual(self.starship.stat().st_mtime, 1_000_000_000)

    def test_other_theme_switches_never_rewrite_the_file(self):
        self.install_symbol('[character]\nerror_symbol = "[x](red)"\n')
        self.hook("nord")
        os.utime(self.starship, (1_000_000_000, 1_000_000_000))
        self.hook("tokyo-night")
        self.assertEqual(self.starship.stat().st_mtime, 1_000_000_000)

    def test_many_round_trips_do_not_grow_the_file(self):
        for original in ('format = "$all"\n', '[character]\nsuccess_symbol = "[>](green)"\n', ""):
            with self.subTest(original=original):
                self.starship.unlink(missing_ok=True)
                (self.sb.state_dir / "starship-error-symbol").unlink(missing_ok=True)
                self.install_symbol(original)
                on, off = self.hook("afterburn"), self.hook("nord")
                for _ in range(10):
                    self.assertEqual(self.hook("afterburn"), on)
                    self.assertEqual(self.hook("nord"), off)
                self.assertNotIn(OURS, off)
                self.assertEqual(off, original)   # a [character] Afterburn added goes again (Codex review C6)

    def test_not_chosen_means_never_touched(self):
        text = '[character]\nerror_symbol = "[x](red)"\n'
        self.sb.write_state_text(self.starship, text)   # no starship-error-symbol record: the subtle pack is not in
        self.assertEqual(self.hook("afterburn"), text)
        self.assertEqual(self.hook("nord"), text)

    def test_your_own_change_while_away_is_kept(self):
        self.install_symbol('[character]\nerror_symbol = "[x](red)"\n')
        self.hook("nord")
        mine = '[character]\nerror_symbol = "[!](yellow)"\n'
        self.starship.write_text(mine)
        self.assertIn(OURS, self.hook("afterburn"), "the record says you chose the red prompt on Afterburn")
        self.assertEqual(self.hook("nord"), mine, "your newer line comes back, not the one from install day")
        self.starship.write_text('[character]\n')                 # you removed it altogether
        self.hook("afterburn")
        self.assertEqual(self.hook("nord"), '[character]\n')

    def test_a_symlinked_config_stays_a_link(self):
        real = self.sb.root / "dotfiles" / "starship.toml"
        real.parent.mkdir()
        real.write_text('[character]\nerror_symbol = "[x](red)"\n')
        self.starship.parent.mkdir(parents=True, exist_ok=True)
        self.starship.symlink_to(real)
        r = self.sb.run(["/bin/bash", "-c", f'source "{THEME_SH}"; ab_starship_record && ab_starship_apply'])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.hook("nord")
        self.assertTrue(self.starship.is_symlink())
        self.assertEqual(real.read_text(), '[character]\nerror_symbol = "[x](red)"\n')


if __name__ == "__main__":
    unittest.main()
