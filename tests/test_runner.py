import queue
import threading
import unittest
from unittest.mock import patch

from PIL import Image

from autoqueue.engine import Action, View
from autoqueue.runner import Control, Runner, action_point


class FakeWindow:
    def __init__(self):
        self.clicks = []

    def capture(self):
        return Image.new('RGB', (600, 1100))

    def focus(self, allowed):
        if not allowed():
            raise RuntimeError('Stopped before focus')

    def click(self, point, **kwargs):
        self.clicks.append(point)


class RunnerTests(unittest.TestCase):
    def test_lost_focus_does_not_commit_an_unsent_game_click(self):
        order = []
        class WorldOCR:
            def inspect(self, image):
                order.append('read')
                return View('world', targets={'dungeon': (300, 380)})
        class FocusWindow(FakeWindow):
            def focus(self, allowed):
                super().focus(allowed)
                order.append('focus')

            def click(self, point, **kwargs):
                order.append('click')
                self.clicks.append(point)
                if len(self.clicks) == 1:
                    return False  # Desktop focus changed before sending input.
                runner.control.stop()
                return True
        windows = {'leader': FocusWindow(), 'member': FakeWindow()}
        runner = Runner(windows, queue.SimpleQueue(), recognizer_factory=WorldOCR)
        runner.start()
        runner.join(3)
        try:
            self.assertFalse(runner.is_alive())
            self.assertEqual(windows['leader'].clicks, [(300, 380), (300, 380)])
            self.assertEqual(order[:5], ['read', 'read', 'focus', 'read', 'click'])
            self.assertEqual(runner.engine.pending[0].kind, 'dungeon')
        finally:
            runner.control.stop()
            runner.join(2)

    def test_stop_during_slow_ocr_cancels_planned_mouse_input(self):
        entered, release = threading.Event(), threading.Event()
        class SlowOCR:
            def inspect(self, image):
                entered.set()
                if not release.wait(2):
                    raise RuntimeError('Test OCR timed out')
                return View('world', targets={'dungeon': (300, 380)})
        windows = {'leader': FakeWindow(), 'member': FakeWindow()}
        runner = Runner(windows, queue.SimpleQueue(), recognizer_factory=SlowOCR)
        runner.start()
        try:
            self.assertTrue(entered.wait(2))
            runner.control.stop()
        finally:
            release.set()
            runner.join(3)
        self.assertFalse(runner.is_alive())
        self.assertFalse(windows['leader'].clicks)
        self.assertFalse(windows['member'].clicks)

    def test_paused_clock_excludes_time_spent_paused(self):
        control = Control()
        with patch('autoqueue.runner.time.monotonic', return_value=10):
            self.assertEqual(control.now(), 10)
            control.pause()
        with patch('autoqueue.runner.time.monotonic', return_value=100):
            self.assertEqual(control.now(), 10)
            control.resume()
            self.assertEqual(control.now(), 10)
        with patch('autoqueue.runner.time.monotonic', return_value=101):
            self.assertEqual(control.now(), 11)

    def test_fresh_screen_must_still_authorize_the_planned_action(self):
        action = Action('leader', 'match')
        self.assertIsNone(action_point(action, View('queue')))
        self.assertIsNone(action_point(action, View('menu')))
        self.assertEqual(action_point(action, View('menu', targets={'match': (450, 950)})), (450, 950))
        exit_action = Action('leader', 'return')
        self.assertIsNone(action_point(exit_action, View('results', [(100, 700)], {'return': (70, 1050)})))
        self.assertIsNone(action_point(exit_action, View('results', [], {'return': (70, 1050)}, False)))
        self.assertEqual(action_point(exit_action, View('results', [], {'return': (70, 1050)}, False), all_liked=True), (70, 1050))


if __name__ == '__main__':
    unittest.main()
