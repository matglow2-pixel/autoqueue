import unittest

import cv2
import numpy as np
from PIL import Image

from autoqueue.vision import Recognizer, Text, classify, find_likes, find_return


def text(value, x, y, confidence=.99):
    return Text(value, (x - 30, y - 10, x + 30, y + 10), confidence)


def results_image(scale=1, liked=0):
    image = np.full((1100, 600, 3), (25, 52, 49), dtype=np.uint8)
    for i, x in enumerate((100, 360, 500)):
        cv2.rectangle(image, (x - 22, 703), (x + 22, 727), (225, 225, 225), -1)
        cv2.circle(image, (x - 22, 715), 12, (225, 225, 225), -1)
        cv2.circle(image, (x + 22, 715), 12, (225, 225, 225), -1)
        color = (245, 190, 25) if i < liked else (20, 20, 20)
        cv2.rectangle(image, (x - 8, 709), (x + 8, 721), color, -1)
        cv2.rectangle(image, (x - 4, 705), (x + 2, 713), color, -1)
    arrow = np.array([(80, 1030), (60, 1050), (80, 1070), (87, 1063), (74, 1050), (87, 1037)])
    cv2.fillPoly(image, [arrow], (240, 240, 240))
    # Bright chest-shaped artwork should not be treated as a like button.
    cv2.rectangle(image, (60, 540), (140, 600), (245, 210, 80), -1)
    if scale != 1:
        image = cv2.resize(image, None, fx=scale, fy=scale)
    return image


class VisionTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((1100, 600, 3), dtype=np.uint8)
        self.title = text("Demonseal Gorge - Hard", 300, 80)

    def test_accept_requires_decline_and_dungeon_title(self):
        labels = [self.title, text("Accept", 440, 950), text("Decline", 160, 950)]
        view = classify(self.frame, labels)
        self.assertEqual(view.state, "accept")
        self.assertEqual(view.targets["accept"], (440, 950))
        self.assertEqual(classify(self.frame, labels[1:]).state, "unknown")
        self.assertEqual(classify(self.frame, labels[:2]).state, "unknown")

    def test_match_and_cancel_are_not_confused_with_matchmaking(self):
        labels = [self.title, text("Team 2/4", 150, 940), text("Match", 440, 940)]
        self.assertEqual(classify(self.frame, labels).targets["match"], (440, 940))
        labels[-1] = text("Cancel", 440, 940)
        self.assertEqual(classify(self.frame, labels).state, "queue")
        labels[-1] = text("Matchmaking...", 100, 340)
        self.assertEqual(classify(self.frame, labels).state, "queue")

    def test_chat_text_and_low_confidence_labels_never_authorize_match(self):
        labels = [self.title, text("Team 2/4", 150, 940), text("Match", 440, 940, .2)]
        self.assertEqual(classify(self.frame, labels).state, "unknown")
        labels[-1] = text("Match", 440, 500)
        self.assertEqual(classify(self.frame, labels).state, "unknown")

    def test_world_does_not_misread_combat_title_as_dungeon_entrance(self):
        labels = [text("Demonseal Gorge", 510, 280), text("Explore", 430, 1070)]
        self.assertEqual(classify(self.frame, labels).targets["dungeon"], (312, 385))
        labels[0] = self.title
        self.assertEqual(classify(self.frame, labels).state, "unknown")

    def test_likes_and_return_detected_without_templates_at_multiple_sizes(self):
        for scale in (.6, 1, 1.5):
            with self.subTest(scale=scale):
                image = results_image(scale)
                likes, ready = find_likes(image, int(760 * scale))
                self.assertTrue(ready)
                self.assertEqual(len(likes), 3)
                point = find_return(image)
                self.assertIsNotNone(point)
                self.assertLess(abs(point[0] / scale - 74), 3)

    def test_clicked_gold_thumbs_are_not_liked_twice(self):
        for liked in range(4):
            likes, ready = find_likes(results_image(liked=liked), 760)
            self.assertTrue(ready)
            self.assertEqual(len(likes), 3 - liked)

    def test_missing_buttons_are_not_treated_as_finished_results(self):
        view = classify(self.frame, [self.title, text("Drops", 70, 760)])
        self.assertEqual(view.state, "results")
        self.assertFalse(view.likes_ready)

    def test_ocr_box_coordinates_are_translated_out_of_letterboxing(self):
        frame = np.zeros((1100, 1400, 3), dtype=np.uint8)
        frame[:, 400:1000] = 70
        labels = [("Demonseal Gorge - Hard", (300, 80)), ("Accept", (440, 950)), ("Decline", (160, 950))]
        def reader(image, **kwargs):
            return [([[x-30, y-10], [x+30, y-10], [x+30, y+10], [x-30, y+10]], value, .99)
                    for value, (x, y) in labels], None
        view = Recognizer(reader).inspect(Image.fromarray(frame))
        self.assertEqual(view.targets["accept"], (840, 950))


if __name__ == "__main__":
    unittest.main()
