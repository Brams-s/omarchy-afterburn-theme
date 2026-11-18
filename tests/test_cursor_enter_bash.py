"""cursor-fx's Enter and done moments in bash (issue #5 follow-up: Enter never played in bash).

A real interactive bash in a pty sources extras/cursor-fx-enter.bash; the cursor-fx stub logs each call.
"""
import os
import pty
import select
import time
import unittest

from support import REPO, Sandbox

ENTER_BASH = REPO / "extras" / "cursor-fx-enter.bash"
FAIL_BASH = REPO / "extras" / "afterburn-fail.bash"


def interactive(sb, lines, before="", **env_extra):
    """Run bash -i in a pty, source the hook (after `before`), send each line, wait for each prompt."""
    env = sb.env(PS1="PRMT> ", **env_extra)
    pid, fd = pty.fork()
    if pid == 0:
        os.execve(str(sb.bin / "bash"), ["bash", "--norc", "--noprofile", "-i"], env)

    def read():
        out = b""
        end = time.monotonic() + 10
        while not out.endswith(b"PRMT> ") and (left := end - time.monotonic()) > 0:
            if select.select([fd], [], [], left)[0]:
                try:
                    chunk = os.read(fd, 65536)
                except OSError:
                    break
                if not chunk:
                    break
                out += chunk
        return out.decode(errors="replace")

    read()
    os.write(fd, f"{before}source {ENTER_BASH}\n".encode())
    seen = [read()]
    for line in lines:
        os.write(fd, line.encode())
        seen.append(read())
    time.sleep(1.5)   # the signals run detached: let them log before the pty closes (it hangs them up)
    os.write(fd, b"exit\n")
    os.waitpid(pid, 0)
    return seen


class CursorEnterBashTests(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.cleanup)

    def signals(self):
        return [l for l in self.sb.call_log() if l.startswith("cursor-fx signal")]

    def test_enter_sends_the_signal_to_this_terminal(self):
        interactive(self.sb, ["true\n", "echo hi\n"], GHOSTTY_RESOURCES_DIR="/x")
        sig = self.signals()
        self.assertEqual(len(sig), 2, sig)
        self.assertTrue(all(s.startswith("cursor-fx signal --tty /dev/") for s in sig), sig)

    def test_empty_enter_sends_nothing(self):
        interactive(self.sb, ["\n", "\n"], GHOSTTY_RESOURCES_DIR="/x")
        self.assertEqual(self.signals(), [])

    def test_a_long_command_also_sends_done(self):
        interactive(self.sb, ["sleep 1.2\n", "true\n"], GHOSTTY_RESOURCES_DIR="/x", AFTERBURN_CFX_DONE_SECS="1")
        sig = self.signals()
        self.assertEqual(sum(s.startswith("cursor-fx signal done --tty /dev/") for s in sig), 1, sig)
        self.assertEqual(sum(s.startswith("cursor-fx signal --tty") for s in sig), 2, sig)

    def test_outside_ghostty_nothing_is_hooked(self):
        out = interactive(self.sb, ["true\n", "declare -p PS0 2>&1; echo \"pc=$PROMPT_COMMAND\"\n"])
        self.assertEqual(self.signals(), [])
        self.assertNotIn("__afb_cfx", out[2])

    def test_no_output_no_job_notices_and_exit_status_kept(self):
        out = interactive(self.sb, ["false\n", "echo rc=$?\n", "sleep 0.2\n"], GHOSTTY_RESOURCES_DIR="/x",
                          AFTERBURN_CFX_DONE_SECS="0")
        self.assertIn("rc=1", out[2])
        joined = "".join(out[1:])
        self.assertNotRegex(joined, r"\[\d+\]")   # no "[1] 1234" or "[1]+ Done"
        self.assertNotIn("signal", joined)

    def test_existing_ps0_and_prompt_command_are_kept_and_fail_flash_stays_first(self):
        before = f"PS0='mine'; source {FAIL_BASH}; "
        out = interactive(self.sb, ["declare -p PS0 PROMPT_COMMAND\n"], before=before, GHOSTTY_RESOURCES_DIR="/x")
        self.assertIn("mine", out[1])
        self.assertRegex(out[1], r"PROMPT_COMMAND=.*__afterburn_fail_hook.*__afb_cfx_done")

    def test_sourcing_twice_hooks_once(self):
        interactive(self.sb, [f"source {ENTER_BASH}\n", "true\n"], GHOSTTY_RESOURCES_DIR="/x")
        # the re-source line itself and `true`: one signal each, not two
        self.assertEqual(len(self.signals()), 2, self.signals())


class InstallAddsTheLine(unittest.TestCase):
    def setUp(self):
        self.sb = Sandbox()
        self.addCleanup(self.sb.cleanup)

    def test_install_adds_it_and_uninstall_puts_bashrc_back_byte_for_byte(self):
        from support import UNINSTALL
        rc = self.sb.home / ".bashrc"
        rc.write_text("alias x=1")   # no final newline
        r = self.sb.install()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = rc.read_text()
        self.assertIn("cursor-fx-enter.bash", text)
        self.assertIn("afterburn-fail.bash", text)
        self.assertLess(text.index("cursor-fx-enter.bash"), text.index("afterburn-fail.bash"))
        r = self.sb.run(["/bin/bash", str(UNINSTALL), "--keep-cursor-fx"])
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(rc.read_text(), "alias x=1")

    def test_install_twice_adds_it_once(self):
        self.sb.install()
        self.sb.install()
        self.assertEqual((self.sb.home / ".bashrc").read_text().count("cursor-fx-enter.bash"), 2)  # guard + source


if __name__ == "__main__":
    unittest.main()
