"""This public repo must work without Mitch's private home repo: every mention of it is conditional."""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HOME_REF = re.compile(r"mitchross/home\b|programming/home\b|workspace/home\b")
# Hermes's own config runs only in Mitch's pod, where the seed clones home.
SKIP = ("my-apps/development/hermes/",)


def agent_files():
    for pattern in ("AGENTS.md", "CLAUDE.md", "**/AGENTS.md", "**/CLAUDE.md", ".claude/commands/*.md", ".agents/skills/**/*.md"):
        for path in ROOT.glob(pattern):
            rel = path.relative_to(ROOT).as_posix()
            if not rel.startswith(SKIP) and "node_modules" not in rel:
                yield path


class HomeRepoOptional(unittest.TestCase):
    def test_home_mentions_are_conditional(self):
        bad = []
        for path in set(agent_files()):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if HOME_REF.search(line) and not re.search(r"\bif\b", line, re.I):
                    bad.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()}")
        self.assertEqual(bad, [], "Mention the home repo only as 'If ... exists':\n" + "\n".join(bad))


if __name__ == "__main__":
    unittest.main()
