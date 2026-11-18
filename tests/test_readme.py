"""The README is the user-facing spec: its names, pin and counts must match the code."""
import re
import unittest

from support import AFTERBURN, INSTALL, REPO, THEME_SH

README = (REPO / "README.md").read_text()
BACKGROUNDS = REPO / "backgrounds"

NUMBERS = {"three": 3, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
           "eleven": 11, "twelve": 12, "thirteen": 13, "nineteen": 19, "twenty": 20}


def number(word):
    return int(word) if word.isdigit() else NUMBERS[word.lower()]


class ReadmeMatchesCode(unittest.TestCase):
    def test_cursor_fx_list_matches_the_names_list(self):
        names = re.search(r'^AB_CURSOR_FX_NAMES="([^"]+)"', THEME_SH.read_text(), re.M).group(1)
        row = next(line for line in README.splitlines() if "`CURSOR_FX` (`embers`)" in line)
        listed = re.search(r"effect for the theme: `([^`]+)`", row).group(1)
        self.assertEqual(listed.split(), names.split())

    def test_cursor_fx_pin_matches_the_installer(self):
        pin = re.search(r"^CFX_PIN=([0-9a-f]+)", INSTALL.read_text(), re.M).group(1)
        quoted = re.search(r"pinned to commit `([0-9a-f]+)`", README).group(1)
        self.assertTrue(pin.startswith(quoted), f"README pin {quoted} is not a prefix of {pin}")

    def test_every_subcommand_is_documented(self):
        script = AFTERBURN.read_text()
        dispatch = script[script.rindex("case "):]
        commands = re.findall(r"^\s+([a-z]+)\)\s+cmd_", dispatch, re.M)
        self.assertGreater(len(commands), 5)
        for command in commands:
            self.assertIn(f"`afterburn {command}", README, f"afterburn {command} is not in the README")

    def test_wallpaper_counts_match_backgrounds(self):
        stills = len(list(BACKGROUNDS.glob("*.jpg")))
        loops = len(list(BACKGROUNDS.glob("*.mp4")))
        m = re.search(r"(\w+) wallpapers: (\w+) stills and (\w+) live loops", README)
        self.assertEqual((number(m.group(1)), number(m.group(2)), number(m.group(3))),
                         (stills + loops, stills, loops))
        m = re.search(r"^(\w+) still wallpapers at 3440×1440, plus (\w+) live loops", README, re.M)
        self.assertEqual((number(m.group(1)), number(m.group(2))), (stills, loops))

    def test_every_edition_is_in_the_editions_table(self):
        editions = sorted(p.name for p in (REPO / ".editions").iterdir() if p.is_dir())
        self.assertTrue(editions)
        for name in editions:
            self.assertIn(f"(`afterburn-{name}`)", README, f"edition {name} is missing from the table")
        # base + editions = the thumbnails the selector-preview section promises
        m = re.search(r"All (\w+) selector thumbnails", README)
        self.assertEqual(number(m.group(1)), len(editions) + 1)

    def test_internal_anchors_resolve(self):
        def slug(heading):
            return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")
        anchors = {slug(h) for h in re.findall(r"^#+ (.+)$", README, re.M)}
        anchors |= set(re.findall(r'<a id="([^"]+)"', README))
        for target in set(re.findall(r"\]\(#([^)]+)\)", README)):
            self.assertIn(target, anchors, f"#{target} has no heading")


if __name__ == "__main__":
    unittest.main()
