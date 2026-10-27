import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from autoqueue.vision import Recognizer, patch_matches


class VisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.rng = np.random.default_rng(42)
        self.config = {"leader": {"markers": {}}}

    def marker(self, name, box, template):
        Image.fromarray(template).save(self.folder / f"{name}.png")
        self.config["leader"]["markers"][name] = {"box": box, "file": f"{name}.png"}

    def test_likes_found_across_row_without_duplicate_hits(self):
        frame = np.zeros((800, 600, 3), dtype=np.uint8)
        template = self.rng.integers(60, 245, (20, 50, 3), dtype=np.uint8)
        for x in (40, 250, 470):
            frame[600:620, x:x + 50] = template
        # Same-looking icon elsewhere must not be clicked.
        frame[300:320, 100:150] = template
        self.marker("like", [40, 600, 90, 620], template)
        recog = Recognizer(self.folder, self.config)
        self.assertEqual(sorted(recog.find_likes("leader", frame)), [(65, 610), (275, 610), (495, 610)])
        frame[600:620, 40:90] = 0
        self.assertEqual(len(recog.find_likes("leader", frame)), 2)

    def test_queue_takes_precedence_over_member_world_label(self):
        frame = self.rng.integers(0, 255, (100, 100, 3), dtype=np.uint8)
        self.marker("world", [0, 0, 20, 20], frame[:20, :20])
        self.marker("queue", [30, 30, 50, 50], frame[30:50, 30:50])
        recog = Recognizer(self.folder, self.config)
        self.assertEqual(recog.inspect("leader", Image.fromarray(frame)).state, "queue")

    def test_ambiguous_states_and_wrong_position_do_not_authorize_clicks(self):
        frame = self.rng.integers(0, 255, (100, 100, 3), dtype=np.uint8)
        for name in ("menu", "accept"):
            self.marker(name, [0, 0, 20, 20], frame[:20, :20])
        recog = Recognizer(self.folder, self.config)
        self.assertEqual(recog.inspect("leader", Image.fromarray(frame)).state, "unknown")
        moved = np.roll(frame, 30, axis=0)
        self.assertEqual(recog.inspect("leader", Image.fromarray(moved)).state, "unknown")

    def test_tolerance_and_changed_button_color(self):
        template = np.full((20, 20, 3), 180, dtype=np.uint8)
        self.assertTrue(patch_matches(template + 5, [0, 0, 20, 20], template))
        changed = template.copy()
        changed[:, :, 2] = 30
        self.assertFalse(patch_matches(changed, [0, 0, 20, 20], template))


if __name__ == "__main__":
    unittest.main()
