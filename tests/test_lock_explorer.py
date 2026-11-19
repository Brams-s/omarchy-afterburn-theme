"""Lock Screen Explorer mode of lock-embers.sh: an Afterburn design in ~/.config/omarchy/lock-designs, chosen over the
explorer's IPC, and never an edit to the explorer's own files."""
import unittest

from support import Sandbox

EXPLORER = "io.github.sirjul1337.lock-explorer"

# `omarchy-shell lock ...` as Lock Screen Explorer answers it: the current design lives in $SB/design. setDesign only
# knows my-afterburn once lock-designs/Afterburn.qml exists (the explorer's rescan lists files in that folder).
SHELL_STUB = r'''#!/bin/bash
echo "omarchy-shell $*" >> "$SB/calls.log"
[[ $1 == lock ]] || exit 0
case $2 in
  design) cat "$SB/design" ;;
  rescanDesigns) echo ok ;;
  setDesign)
    if [[ $3 == my-afterburn && ! -f $HOME/.config/omarchy/lock-designs/Afterburn.qml ]]; then echo unknown-design
    else echo "$3" > "$SB/design"; echo ok; fi ;;
esac
'''


class LockExplorerTests(unittest.TestCase):
    def sandbox(self, design="editorial"):
        sb = Sandbox()
        self.addCleanup(sb.cleanup)
        (sb.bin / "omarchy-shell").write_text(SHELL_STUB)
        sb.write_state_text(sb.root / "design", design + "\n")
        sb.set_plugin("omarchy.lock", "disabled")
        sb.add_user_plugin(EXPLORER)
        self.explorer_dir = sb.plugins_dir / EXPLORER
        self.explorer_files = sorted(p.name for p in self.explorer_dir.iterdir())
        return sb

    def design(self, sb):
        return (sb.root / "design").read_text().strip()

    def designs(self, sb):
        return sb.home / ".config/omarchy/lock-designs"

    def test_install_writes_the_design_selects_it_and_remembers_the_old_one(self):
        sb = self.sandbox()
        r = sb.lock("install")
        self.assertEqual(r.returncode, 0, r.stderr)
        d = self.designs(sb)
        self.assertTrue((d / "Afterburn.qml").read_text().startswith("// afterburn:lock-explorer"))
        self.assertTrue((d / "afterburn/EmberLayer.qml").is_file())
        self.assertEqual(len(list((d / "afterburn").glob("embers.*/Embers.qml"))), 1)
        self.assertEqual(sb.marker.read_text(), "mode=explorer\n")
        self.assertEqual((sb.state_dir / "lock-explorer-prev").read_text(), "editorial\n")
        self.assertEqual(self.design(sb), "my-afterburn")
        # No clone, no enable/disable, and the explorer's folder untouched.
        self.assertFalse((sb.plugins_dir / "afterburn.lock").exists())
        self.assertEqual(sb.enabled_locks(), [EXPLORER])
        self.assertEqual(sorted(p.name for p in self.explorer_dir.iterdir()), self.explorer_files)

    def test_install_refuses_a_design_file_that_is_not_ours(self):
        sb = self.sandbox()
        sb.write_state_text(self.designs(sb) / "Afterburn.qml", "// my own design\n")
        r = sb.lock("install")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual((self.designs(sb) / "Afterburn.qml").read_text(), "// my own design\n")
        self.assertEqual(self.design(sb), "editorial")

    def test_recolor_writes_new_embers_into_the_design_folder(self):
        sb = self.sandbox()
        sb.lock("install")
        r = sb.lock("recolor", "112233", "445566", "778899", "fall")
        self.assertEqual(r.returncode, 0, r.stderr)
        embers = list((self.designs(sb) / "afterburn").glob("embers.*/Embers.qml"))
        self.assertEqual(len(embers), 1)
        text = embers[0].read_text()
        self.assertIn("445566", text)
        self.assertNotIn("ff5a1f", text)

    def test_park_and_unpark_swap_designs(self):
        sb = self.sandbox()
        sb.lock("install")
        sb.write_state_text(sb.home / ".local/state/omarchy/current/theme.name", "nord\n")
        self.assertEqual(sb.lock("park").returncode, 0)
        self.assertEqual(self.design(sb), "editorial")
        sb.write_state_text(sb.home / ".local/state/omarchy/current/theme.name", "afterburn\n")
        self.assertEqual(sb.lock("unpark").returncode, 0)
        self.assertEqual(self.design(sb), "my-afterburn")

    def test_a_design_picked_while_parked_stays(self):
        sb = self.sandbox()
        sb.lock("install")
        sb.lock("park")
        sb.write_state_text(sb.root / "design", "zen\n")
        sb.lock("unpark")
        self.assertEqual(self.design(sb), "zen")
        self.assertFalse((sb.state_dir / "lock-parked").exists())

    def test_uninstall_restores_the_old_design_and_removes_ours(self):
        sb = self.sandbox()
        sb.lock("install")
        r = sb.lock("uninstall")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.design(sb), "editorial")
        self.assertFalse((self.designs(sb) / "Afterburn.qml").exists())
        self.assertFalse((self.designs(sb) / "afterburn").exists())
        self.assertFalse(sb.marker.exists())
        self.assertEqual(sb.enabled_locks(), [EXPLORER])

    def test_stock_lock_still_gets_the_clone(self):
        sb = Sandbox()
        self.addCleanup(sb.cleanup)
        r = sb.lock("install")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((sb.plugins_dir / "afterburn.lock").is_dir())
        self.assertIn("clone_id=afterburn.lock", sb.marker.read_text())


if __name__ == "__main__":
    unittest.main()
