import unittest

import cv2
import numpy as np
from PIL import Image

from autoqueue.vision import (Recognizer, Text, classify, find_likes, find_return,
                             results_fast, remember_like_patches, clicked_likes_cleared)


def text(value, x, y, confidence=.99):
    return Text(value, (x - 30, y - 10, x + 30, y + 10), confidence)


def results_image(scale=1, liked=0):
    image = np.full((1100, 600, 3), (25, 52, 49), dtype=np.uint8)
    image[180:280] = (205, 215, 100)
    for i, x in enumerate((100, 360, 500)):
        cv2.rectangle(image, (x - 22, 703), (x + 22, 727), (225, 225, 225), -1)
        cv2.circle(image, (x - 22, 715), 12, (225, 225, 225), -1)
        cv2.circle(image, (x + 22, 715), 12, (225, 225, 225), -1)
        if i < liked:
            cv2.rectangle(image, (x - 22, 703), (x + 22, 727), (90, 95, 45), -1)
            cv2.circle(image, (x - 22, 715), 12, (90, 95, 45), -1)
            cv2.circle(image, (x + 22, 715), 12, (90, 95, 45), -1)
            cv2.rectangle(image, (x - 22, 705), (x + 22, 725), (25, 40, 38), -1)
            cv2.circle(image, (x - 22, 715), 10, (25, 40, 38), -1)
            cv2.circle(image, (x + 22, 715), 10, (25, 40, 38), -1)
        color = (245, 190, 25) if i < liked else (20, 20, 20)
        cv2.rectangle(image, (x - 8, 709), (x + 8, 721), color, -1)
        cv2.rectangle(image, (x - 4, 705), (x + 2, 713), color, -1)
    arrow = np.array([(80, 1030), (60, 1050), (80, 1070), (87, 1063), (74, 1050), (87, 1037)])
    cv2.fillPoly(image, [arrow], (240, 240, 240))
    # Bright chest-shaped artwork should not be treated as a like button.
    cv2.rectangle(image, (60, 540), (140, 600), (245, 210, 80), -1)
    cv2.line(image, (20, 780), (580, 780), (170, 170, 170), 2)
    # The player's own like counter is a gold hexagon, not a teammate button.
    cv2.fillPoly(image, [np.array([(235, 698), (250, 706), (250, 724), (235, 732),
                                  (220, 724), (220, 706)])], (190, 200, 70))
    if scale != 1:
        image = cv2.resize(image, None, fx=scale, fy=scale)
    return image


class VisionTests(unittest.TestCase):
    def setUp(self):
        self.frame = np.zeros((1100, 600, 3), dtype=np.uint8)
        self.title = text("Demonseal Gorge - Hard", 300, 80)

    def test_accept_requires_the_shared_button_pair_without_a_dungeon_title(self):
        cv2.rectangle(self.frame, (30, 925), (285, 975), (225, 225, 225), -1)
        cv2.rectangle(self.frame, (310, 925), (575, 975), (205, 216, 75), -1)
        labels = [self.title, text("Accept", 440, 950), text("Decline", 160, 950)]
        view = classify(self.frame, labels)
        self.assertEqual(view.state, "accept")
        self.assertEqual(view.targets["accept"], (440, 950))
        self.assertEqual(classify(self.frame, labels[1:]).state, "accept")
        self.assertEqual(classify(self.frame, labels[:2]).state, "unknown")

    def test_disabled_accept_is_not_an_actionable_button(self):
        cv2.rectangle(self.frame, (30, 925), (575, 975), (225, 225, 225), -1)
        labels = [self.title, text("Accept", 440, 950), text("Decline", 160, 950)]
        view = classify(self.frame, labels)
        self.assertEqual(view.state, "accepted")
        self.assertNotIn("accept", view.targets)

    def test_cached_accept_is_invalidated_when_button_becomes_disabled(self):
        frame = self.frame.copy()
        cv2.rectangle(frame, (30, 925), (285, 975), (225, 225, 225), -1)
        cv2.rectangle(frame, (310, 925), (575, 975), (205, 216, 75), -1)
        for x in (150, 440):
            cv2.putText(frame, 'Text', (x-30, 960), cv2.FONT_HERSHEY_SIMPLEX,
                        .6, (0, 0, 0), 2)
        def reader(image, **kwargs):
            # Force full-frame fallback so test labels have absolute coordinates.
            if image.shape[0] != 1100:
                return None, None
            return [([[x-30, y-10], [x+30, y-10], [x+30, y+10], [x-30, y+10]], value, .99)
                    for value, x, y in (("Demonseal Gorge", 300, 80),
                                        ("Decline", 150, 950), ("Accept", 440, 950))], None
        recognizer = Recognizer(reader)
        self.assertEqual(recognizer.inspect(Image.fromarray(frame)).state, 'accept')
        self.assertIn('default', recognizer.cache)
        # Gray the background but preserve label pixels: text-only cache hits
        # must not authorize another Accept click.
        yellow = (frame[:, :, 0] == 205) & (frame[:, :, 1] == 216)
        frame[yellow] = (225, 225, 225)
        for (x1, y1, x2, y2), patch in recognizer.cache['default'][3]:
            frame[y1:y2, x1:x2] = patch
        view = recognizer.inspect(Image.fromarray(frame))
        self.assertNotEqual(view.state, 'accept')

    def test_new_match_button_overrides_a_cached_outside_hud(self):
        frame = self.frame.copy()
        cv2.putText(frame, 'Explore', (400, 1070), cv2.FONT_HERSHEY_SIMPLEX,
                    .6, (225, 225, 225), 2)
        menu_open = [False]
        def reader(image, **kwargs):
            if image.shape[0] != 1100:
                return None, None
            labels = [('Explore', 430, 1060)]
            if menu_open[0]:
                labels.extend([('Team 2/4', 150, 940), ('Match', 440, 940)])
            return [([[x-30, y-10], [x+30, y-10], [x+30, y+10], [x-30, y+10]], value, .99)
                    for value, x, y in labels], None
        recognizer = Recognizer(reader)
        self.assertEqual(recognizer.inspect(Image.fromarray(frame)).state, 'world')
        self.assertIn('default', recognizer.cache)
        menu_open[0] = True
        cv2.rectangle(frame, (30, 915), (285, 975), (225, 225, 225), -1)
        cv2.rectangle(frame, (310, 915), (575, 975), (205, 216, 75), -1)
        view = recognizer.inspect(Image.fromarray(frame))
        self.assertEqual(view.state, 'menu')
        self.assertEqual(view.targets['match'], (440, 940))

    def test_gold_reward_badges_do_not_turn_a_queue_into_results(self):
        frame = results_image(liked=3)
        frame[180:280] = (25, 52, 49)  # No results rank banner on the queue.
        self.assertIsNone(results_fast(frame))

    def test_accept_pair_survives_misread_dungeon_heading(self):
        frame = self.frame.copy()
        cv2.rectangle(frame, (30, 925), (285, 975), (225, 225, 225), -1)
        cv2.rectangle(frame, (310, 925), (575, 975), (205, 216, 75), -1)
        labels = [text("Enter Dem0nseai G0rge - Hard", 300, 80),
                  text("Decline", 160, 950), text("Accept", 440, 950)]
        self.assertEqual(classify(frame, labels).state, "accept")
        self.assertEqual(classify(frame, labels).targets["accept"], (440, 950))

    def test_queue_detection_does_not_depend_on_dungeon_name_ocr(self):
        labels = [text("Team 2/4", 150, 940), text("Cancel", 440, 940)]
        self.assertEqual(classify(self.frame, labels).state, "queue")
        self.assertEqual(classify(self.frame, [text("Matchmaking...", 100, 340)]).state, "queue")

    def test_full_frame_fallback_recovers_unreadable_control_atlas(self):
        frame = self.frame.copy()
        cv2.rectangle(frame, (30, 925), (285, 975), (225, 225, 225), -1)
        cv2.rectangle(frame, (310, 925), (575, 975), (205, 216, 75), -1)
        calls = []
        def reader(image, **kwargs):
            calls.append(image.shape)
            if len(calls) == 1:
                return None, None
            y = 950
            return [([[x-30, y-10], [x+30, y-10], [x+30, y+10], [x-30, y+10]], value, .99)
                    for value, x in (("Accept", 440), ("Decline", 160))], None
        view = Recognizer(reader).inspect(Image.fromarray(frame))
        self.assertEqual(len(calls), 2)
        self.assertLess(calls[0][0], calls[1][0])
        self.assertEqual(view.targets["accept"], (440, 950))

    def test_match_and_cancel_are_not_confused_with_matchmaking(self):
        cv2.rectangle(self.frame, (30, 915), (285, 965), (225, 225, 225), -1)
        cv2.rectangle(self.frame, (310, 915), (575, 965), (205, 216, 75), -1)
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

    def test_world_uses_the_marked_point_with_any_or_no_dungeon_name(self):
        for name in (None, "Demonseal Gorge", "Another Dungeon"):
            with self.subTest(name=name):
                labels = [text("Explore", 430, 1070)]
                if name:
                    labels.append(text(name, 510, 280))
                self.assertEqual(classify(self.frame, labels).targets["dungeon"], (303, 374))

    def test_dungeon_title_and_chat_text_cannot_authorize_an_entrance_click(self):
        for labels in ([self.title], [self.title, text("Explore", 200, 950)],
                       [text("Explore", 430, 950)], [text("Explore", 430, 1070, .2)]):
            with self.subTest(labels=labels):
                self.assertEqual(classify(self.frame, labels).state, 'unknown')

    def test_entrance_matches_the_red_dot_and_stays_above_the_character_when_scaled(self):
        # Reference: client origin (12,17), 574x1040; dot at (303,372)
        # and the central character's head below y=490 in the supplied image.
        for scale in (.5, 1, 1.5):
            with self.subTest(scale=scale):
                width, height = round(574 * scale), round(1040 * scale)
                frame = np.zeros((height, width, 3), np.uint8)
                label = text('Explore', round(.77 * width), round(.97 * height))
                x, y = classify(frame, [label]).targets['dungeon']
                self.assertAlmostEqual(x / scale + 12, 303, delta=3)
                self.assertAlmostEqual(y / scale + 17, 372, delta=3)
                self.assertLess(y / scale + 17, 490 - 100)

    def test_common_controls_and_results_work_without_a_dungeon_heading(self):
        frame = self.frame.copy()
        cv2.rectangle(frame, (30, 915), (285, 975), (225, 225, 225), -1)
        cv2.rectangle(frame, (310, 915), (575, 975), (205, 216, 75), -1)
        for name in (None, 'Demonseal Gorge', 'Another Dungeon'):
            heading = [text(name, 300, 80)] if name else []
            with self.subTest(name=name):
                self.assertEqual(classify(frame, heading + [text('Team 2/4', 150, 940),
                                                            text('Match', 440, 940)]).state, 'menu')
                self.assertEqual(classify(frame, heading + [text('Decline', 150, 940),
                                                            text('Accept', 440, 940)]).state, 'accept')
                self.assertEqual(classify(results_image(), heading + [text('Drops', 70, 760)]).state,
                                 'results')

    def test_marked_entrance_point_is_translated_from_a_letterboxed_game(self):
        frame = np.zeros((1100, 1400, 3), dtype=np.uint8)
        frame[:, 400:1000] = 70
        def reader(image, **kwargs):
            if image.shape[0] != 1100:
                return None, None
            return [([[400, 1040], [460, 1040], [460, 1060], [400, 1060]], 'Explore', .99)], None
        view = Recognizer(reader).inspect(Image.fromarray(frame))
        self.assertEqual(view.targets['dungeon'], (703, 374))

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

    def test_exit_detection_accepts_different_chevron_stroke_widths(self):
        for stroke in (5, 7, 9, 12):
            with self.subTest(stroke=stroke):
                image = np.full((1100, 600, 3), (25, 52, 49), dtype=np.uint8)
                cv2.polylines(image, [np.array([(82, 1032), (64, 1050), (82, 1068)])],
                              False, (240, 240, 240), stroke, cv2.LINE_AA)
                self.assertIsNotNone(find_return(image))

    def test_results_detection_rejects_white_circle_in_exit_corner(self):
        image = np.full((1100, 600, 3), (25, 52, 49), dtype=np.uint8)
        cv2.circle(image, (75, 1050), 20, (240, 240, 240), -1)
        self.assertIsNone(find_return(image))

    def test_incoming_gold_indicators_are_not_click_targets(self):
        for liked in range(4):
            likes, ready = find_likes(results_image(liked=liked), 760)
            self.assertTrue(ready)
            self.assertEqual(len(likes), 3 - liked)

    def test_zero_detected_thumbs_without_click_history_never_allows_exit(self):
        frame = self.frame.copy()
        frame[180:280] = (205, 215, 100)
        view = classify(frame, [text("Drops", 70, 760)])
        self.assertEqual(view.state, "results")
        self.assertFalse(view.likes_ready)
        self.assertEqual(view.likes, [])
        self.assertEqual(list(view.targets), ['return'])

    def test_incoming_gold_counts_do_not_confirm_outgoing_likes(self):
        for liked in range(4):
            with self.subTest(liked=liked):
                view = results_fast(results_image(liked=liked))
                self.assertIsNotNone(view)
                self.assertEqual(view.likes_ready, liked < 3)
                self.assertEqual(len(view.likes), 3 - liked)
                self.assertIn("return", view.targets)

    def test_outgoing_buttons_disappearing_confirms_likes_with_any_incoming_count(self):
        original = Image.fromarray(results_image())
        points = [(100, 715), (360, 715), (500, 715)]
        evidence = {}
        remember_like_patches(original, points, evidence)
        self.assertFalse(clicked_likes_cleared(original, evidence, set(points)))
        for incoming in (0, 2, 3):
            with self.subTest(incoming=incoming):
                after = results_image(liked=incoming)
                for i, x in enumerate((100, 360, 500)):
                    if i >= incoming:
                        after[695:735, x-36:x+36] = (25, 52, 49)
                image = Image.fromarray(after)
                self.assertTrue(clicked_likes_cleared(image, evidence, set(points)))
                self.assertFalse(clicked_likes_cleared(image, evidence, set()))
                # An app without history must not use received likes as proof.
                self.assertFalse(clicked_likes_cleared(image, {}, set(points)))

    def test_a_remaining_white_button_blocks_exit_even_if_two_incoming_likes_show(self):
        points = [(100, 715), (360, 715), (500, 715)]
        evidence = {}
        remember_like_patches(Image.fromarray(results_image()), points, evidence)
        self.assertFalse(clicked_likes_cleared(Image.fromarray(results_image(liked=2)), evidence, set(points)))

    def test_results_icons_use_no_ocr_and_no_manual_templates(self):
        def forbidden_reader(*args, **kwargs):
            self.fail("Results icons should not run a full-window OCR pass")
        view = Recognizer(forbidden_reader).inspect(Image.fromarray(results_image()))
        self.assertEqual(view.state, "results")
        self.assertEqual(len(view.likes), 3)
        self.assertTrue(all(abs(x - 235) > 20 for x, _ in view.likes))

    def test_four_actual_thumbs_are_supported_without_clicking_fixed_avatar_positions(self):
        image = results_image()
        image[690:740, 200:270] = (25, 52, 49)
        cv2.rectangle(image, (213, 703), (257, 727), (225, 225, 225), -1)
        cv2.circle(image, (213, 715), 12, (225, 225, 225), -1)
        cv2.circle(image, (257, 715), 12, (225, 225, 225), -1)
        cv2.rectangle(image, (227, 709), (243, 721), (20, 20, 20), -1)
        view = results_fast(image)
        self.assertEqual(len(view.likes), 4)
        self.assertIn((235, 715), view.likes)

    def test_member_thumbs_are_found_when_the_row_moves_or_buttons_are_dim(self):
        for shift in (-85, 40):
            for brightness in (.7, 1):
                with self.subTest(shift=shift, brightness=brightness):
                    image = results_image()
                    row = image[690:740].copy()
                    image[690:740] = (25, 52, 49)
                    image[690+shift:740+shift] = row
                    image = (image.astype(np.float32) * brightness).astype(np.uint8)
                    view = classify(image, [self.title, text('Drops', 70, 760)])
                    self.assertTrue(view.likes_ready)
                    self.assertEqual(len(view.likes), 3)
                    self.assertTrue(all(abs(y - (715 + shift)) < 8 for _, y in view.likes))

    def test_like_clicks_do_not_depend_on_exit_arrow_recognition(self):
        image = results_image()
        image[1000:] = (25, 52, 49)
        view = classify(image, [self.title, text("Drops", 70, 760)])
        self.assertEqual(view.state, "results")
        self.assertTrue(view.likes_ready)
        self.assertEqual(len(view.likes), 3)
        self.assertEqual(view.targets["return"], (66, 1050))

    def test_rank_banner_and_divider_work_when_both_thumb_and_arrow_detectors_miss(self):
        image = results_image()
        image[650:750] = (25, 52, 49)
        image[1000:] = (25, 52, 49)
        image[180:280] = (205, 215, 100)
        def forbidden_reader(*args, **kwargs):
            self.fail("The results layout should be recognized without OCR")
        view = Recognizer(forbidden_reader).inspect(Image.fromarray(image))
        self.assertEqual(view.state, "results")
        self.assertFalse(view.likes_ready)
        self.assertEqual(view.likes, [])
        self.assertEqual(list(view.targets), ['return'])
        self.assertEqual(view.targets["return"], (66, 1050))

    def test_ocr_box_coordinates_are_translated_out_of_letterboxing(self):
        frame = np.zeros((1100, 1400, 3), dtype=np.uint8)
        frame[:, 400:1000] = 70
        cv2.rectangle(frame, (430, 925), (685, 975), (225, 225, 225), -1)
        cv2.rectangle(frame, (710, 925), (975, 975), (205, 216, 75), -1)
        labels = [("Demonseal Gorge - Hard", (300, 80)), ("Accept", (440, 950)), ("Decline", (160, 950))]
        def reader(image, **kwargs):
            return [([[x-30, y-10], [x+30, y-10], [x+30, y+10], [x-30, y+10]], value, .99)
                    for value, (x, y) in labels], None
        view = Recognizer(reader).inspect(Image.fromarray(frame))
        self.assertEqual(view.targets["accept"], (840, 950))


if __name__ == "__main__":
    unittest.main()
