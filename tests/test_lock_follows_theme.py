"""The ember lock is Afterburn's: other themes get Omarchy's own lock back (issue #5 follow-up).

lock-embers.sh park/unpark, and the theme-set hook that runs them. At every step some lock stays enabled.
"""
import subprocess
import unittest

try:
    from support import REPO, Sandbox
except ImportError:
    from tests.support import REPO, Sandbox

HOOK = REPO / "extras" / "afterburn-theme-set-hook"


class LockFollowsTheme(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox("alice")
        self.addCleanup(self.sb.cleanup)
        r = self.sb.lock("install")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.sb.enabled_locks(), ["afterburn.lock"])
        self.parked = self.sb.state_dir / "lock-parked"

    def hook(self, theme, **env):
        self.sb.write_state_text(self.sb.home / ".local/state/omarchy/current/theme.name", theme)
        r = self.sb.run(["/bin/bash", str(HOOK), theme], **env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    # --- through the hook -------------------------------------------------------------------------
    def test_leaving_afterburn_brings_the_builtin_lock_back(self):
        self.hook("nord")
        self.assertEqual(self.sb.enabled_locks(), ["omarchy.lock"])
        self.assertTrue(self.parked.exists())
        self.assertTrue((self.sb.plugins_dir / "afterburn.lock").is_dir(), "the clone itself stays installed")

    def test_coming_back_brings_the_embers_back(self):
        self.hook("nord")
        self.hook("afterburn")
        self.assertEqual(self.sb.enabled_locks(), ["afterburn.lock"])
        self.assertFalse(self.parked.exists())

    def test_edition_to_edition_never_touches_the_lock(self):
        self.hook("afterburn")
        before = [c for c in self.sb.call_log() if "plugin-enable" in c or "plugin-disable" in c]
        self.hook("afterburn-redline")
        after = [c for c in self.sb.call_log() if "plugin-enable" in c or "plugin-disable" in c]
        self.assertEqual(before, after)
        self.assertEqual(self.sb.enabled_locks(), ["afterburn.lock"])

    def test_other_theme_to_other_theme_is_a_no_op(self):
        self.hook("nord")
        n = len(self.sb.call_log())
        self.hook("tokyo-night")
        self.assertFalse(any("plugin-enable" in c for c in self.sb.call_log()[n:]))
        self.assertEqual(self.sb.enabled_locks(), ["omarchy.lock"])

    def test_a_lock_you_picked_meanwhile_stays_yours(self):
        self.hook("nord")
        self.sb.add_user_plugin("hello.lock", "disabled")
        subprocess.run([str(self.sb.bin / "omarchy-plugin-enable"), "hello.lock"], env=self.sb.env(), check=True,
                       capture_output=True)
        self.hook("afterburn")
        self.assertEqual(self.sb.enabled_locks(), ["hello.lock"])
        self.assertFalse(self.parked.exists())

    def test_a_shell_with_many_locks_still_ends_with_one(self):
        """If Omarchy ever stops keeping one lock at a time, park and unpark switch the other one off themselves."""
        self.hook("nord", STUB_MANY_LOCKS="1")
        self.assertEqual(self.sb.enabled_locks(), ["omarchy.lock"])
        self.hook("afterburn", STUB_MANY_LOCKS="1")
        self.assertEqual(self.sb.enabled_locks(), ["afterburn.lock"])

    def test_quick_switches_end_in_one_consistent_state(self):
        lock_sh = REPO / "extras" / "lock" / "lock-embers.sh"
        procs = [subprocess.Popen(["/bin/bash", str(lock_sh), cmd], env=self.sb.env(),
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                 for cmd in ("park", "unpark", "park", "unpark", "park")]
        for p in procs:
            p.wait(timeout=60)
        locks = self.sb.enabled_locks()
        self.assertEqual(len(locks), 1, locks)
        self.assertEqual(self.parked.exists(), locks == ["omarchy.lock"])

    def test_a_hook_for_a_superseded_theme_changes_nothing(self):
        """Quick switches: a hook for nord that waited for the lock runs after the newer afterburn hook unparked.
        Seen on a real machine: without the check, it parked the lock while Afterburn was the theme."""
        self.hook("afterburn")
        r = self.sb.lock("park", LOCK_EMBERS_FOR_THEME="nord")    # theme.name is afterburn now
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.sb.enabled_locks(), ["afterburn.lock"])
        self.hook("nord")
        r = self.sb.lock("unpark", LOCK_EMBERS_FOR_THEME="afterburn")
        self.assertEqual(self.sb.enabled_locks(), ["omarchy.lock"])

    def test_quick_hooks_end_on_the_last_theme(self):
        name = self.sb.home / ".local/state/omarchy/current/theme.name"
        procs = []
        for theme in ("nord", "afterburn", "tokyo-night", "afterburn-redline", "nord", "afterburn"):
            self.sb.write_state_text(name, theme)
            procs.append(subprocess.Popen(["/bin/bash", str(HOOK), theme], env=self.sb.env(),
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        for p in procs:
            p.wait(timeout=60)
        self.assertEqual(self.sb.enabled_locks(), ["afterburn.lock"])
        self.assertFalse(self.parked.exists())

    # --- failures keep a lock ------------------------------------------------------------------------
    def test_a_failed_park_keeps_the_clone(self):
        self.hook("nord", STUB_ENABLE_FAIL="1")
        self.assertEqual(self.sb.enabled_locks(), ["afterburn.lock"])
        self.assertFalse(self.parked.exists())

    def test_a_failed_unpark_keeps_the_builtin_and_tries_again(self):
        self.hook("nord")
        self.hook("afterburn", STUB_ENABLE_FAIL="1")
        self.assertEqual(self.sb.enabled_locks(), ["omarchy.lock"])
        self.assertTrue(self.parked.exists(), "the next theme change tries again")
        self.hook("afterburn")
        self.assertEqual(self.sb.enabled_locks(), ["afterburn.lock"])

    def test_a_failed_plugin_list_keeps_the_park_for_a_retry(self):  # Codex review C2
        self.hook("nord")
        self.hook("afterburn", STUB_LIST_FAIL="1")
        self.assertTrue(self.parked.exists(), "cannot tell is not 'you changed it'")
        self.assertEqual(self.sb.enabled_locks(), ["omarchy.lock"])
        self.hook("afterburn")
        self.assertEqual(self.sb.enabled_locks(), ["afterburn.lock"])
        self.assertFalse(self.parked.exists())

    def test_a_lock_wait_that_times_out_changes_nothing(self):  # PR #8 review
        import fcntl
        lck = open(self.sb.state_dir / "lock-embers.lck", "w")
        self.addCleanup(lck.close)
        fcntl.flock(lck, fcntl.LOCK_EX)
        r = self.sb.lock("park", LOCK_EMBERS_WAIT="1")
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertIn("nothing changed", r.stdout + r.stderr)
        self.assertEqual(self.sb.enabled_locks(), ["afterburn.lock"])
        self.assertFalse(self.parked.exists())

    def test_no_shell_means_no_change(self):
        (self.sb.bin / "omarchy-plugin-list").write_text("#!/bin/bash\nexit 1\n")
        self.hook("nord")
        self.assertEqual(self.sb.enabled_locks(), ["afterburn.lock"])
        self.assertFalse(self.parked.exists())

    def test_park_does_nothing_without_the_embers_installed(self):
        self.sb.marker.unlink()
        r = self.sb.lock("park")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.sb.enabled_locks(), ["afterburn.lock"])

    # --- afterburn doctor -------------------------------------------------------------------------------
    def test_doctor_shows_the_lock_state(self):
        r = self.sb.afterburn("doctor")
        self.assertIn("lock:       afterburn.lock enabled, omarchy.lock disabled", r.stdout, r.stderr)
        self.assertIn("loader:   current", r.stdout)
        self.assertIn("embers:   embers.", r.stdout)
        self.hook("nord")
        r = self.sb.afterburn("doctor")
        self.assertIn("afterburn.lock disabled, omarchy.lock enabled  (parked", r.stdout)

    def test_doctor_flags_an_old_loader(self):
        (self.sb.plugins_dir / "afterburn.lock" / "EmberLayer.qml").write_text("// the 2.0.5 loader\n")
        self.assertIn("loader:   OUTDATED", self.sb.afterburn("doctor").stdout)

    # --- uninstall -----------------------------------------------------------------------------------
    def test_uninstall_while_parked(self):
        self.hook("nord")
        r = self.sb.lock("uninstall")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.sb.plugins_dir / "afterburn.lock").exists())
        self.assertEqual(self.sb.enabled_locks(), ["omarchy.lock"])
        self.assertFalse(self.parked.exists())


if __name__ == "__main__":
    unittest.main()
