import queue
import threading
import unittest
from unittest.mock import patch

from PIL import Image

from autoqueue.engine import Action, View, SafetyStop
from autoqueue.runner import Control, Runner, action_point, cleanup_points


def results_view():
    return View('results', targets={
        'like_1': (100, 715), 'like_2': (250, 715), 'like_3': (400, 715),
        'like_4': (520, 715), 'return': (66, 1050)})


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
    def test_match_click_commits_without_a_matchmaking_deadline(self):
        class MenuOCR:
            def inspect(self, image, role="default"):
                return View('menu', targets={'match': (450, 950)}) if role == 'leader' else View('world')
        class MatchWindow(FakeWindow):
            def click(self, point, **kwargs):
                self.clicks.append(point)
                runner.control.stop()
                return True
        windows = {'leader': MatchWindow(), 'member': FakeWindow()}
        runner = Runner(windows, queue.SimpleQueue(), recognizer_factory=MenuOCR)
        runner.start()
        runner.join(3)
        try:
            self.assertFalse(runner.is_alive())
            self.assertEqual(windows['leader'].clicks, [(450, 950)])
            self.assertEqual(runner.engine.pending[0].kind, 'match')
            self.assertIsNone(runner.engine.pending[1])
        finally:
            runner.control.stop()
            runner.join(2)

    def test_lost_focus_does_not_commit_an_unsent_game_click(self):
        order = []
        class WorldOCR:
            def inspect(self, image, role="default"):
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
            def inspect(self, image, role="default"):
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
        self.assertIsNone(cleanup_points(View('world')))
        self.assertIsNone(cleanup_points(View('results', likes_ready=False)))
        self.assertEqual(cleanup_points(results_view()),
                         ((100, 715), (250, 715), (400, 715), (520, 715), (66, 1050)))

    def test_cleanup_clicks_all_detected_icons_then_exit_without_more_ocr(self):
        windows = {'leader': FakeWindow(), 'member': FakeWindow()}
        runner = Runner(windows, queue.SimpleQueue(), like_delay=lambda: 0)
        runner.sizes['member'] = (600, 1100)
        runner.observe = lambda role: View('results', targets={'return': (66, 1050)})
        view = results_view()
        self.assertTrue(runner.cleanup('member', view))
        self.assertEqual(windows['member'].clicks, list(cleanup_points(view)))
        self.assertEqual(windows['leader'].clicks, [])
        self.assertTrue(runner.cleanup('member', view))
        self.assertEqual(len(windows['member'].clicks), 5)

    def test_cleanup_stop_interrupts_before_exit(self):
        class StoppingWindow(FakeWindow):
            def click(self, point, **kwargs):
                self.clicks.append(point)
                if len(self.clicks) == 2:
                    runner.control.stop()
                return True
        window = StoppingWindow()
        runner = Runner({'leader': FakeWindow(), 'member': window}, queue.SimpleQueue(), like_delay=lambda: 0)
        runner.sizes['member'] = (600, 1100)
        self.assertFalse(runner.cleanup('member', results_view()))
        self.assertEqual(window.clicks, [(100, 715), (250, 715)])

    def test_cleanup_retains_progress_when_focus_is_lost(self):
        class InterruptedWindow(FakeWindow):
            failed = False
            def click(self, point, **kwargs):
                if len(self.clicks) == 2 and not self.failed:
                    self.failed = True
                    return False
                self.clicks.append(point)
                return True
        window = InterruptedWindow()
        runner = Runner({'leader': FakeWindow(), 'member': window}, queue.SimpleQueue(), like_delay=lambda: 0)
        runner.sizes['member'] = (600, 1100)
        self.assertFalse(runner.cleanup('member', results_view()))
        # Already-liked icons can disappear from a later screenshot. Continue
        # the original authorized sequence without double-clicking prior icons.
        changed_view = View('results', targets={'like_1': (400, 715), 'return': (66, 1050)})
        runner.observe = lambda role: View('results', targets={'return': (66, 1050)})
        self.assertTrue(runner.cleanup('member', changed_view))
        self.assertEqual(window.clicks, list(cleanup_points(results_view())))

    def test_complete_cleanup_order_is_member_then_leader_with_five_second_requeue_wait(self):
        states = {'leader': 'results', 'member': 'results'}
        clicks = []
        reads = []
        trace = []
        exit_times = {}
        remaining = {r: list(cleanup_points(results_view())[:-1]) for r in states}
        class ResultsOCR:
            def inspect(self, image, role='default'):
                reads.append(role)
                trace.append(('read', role))
                if states[role] != 'results':
                    return View('world')
                targets = {f'like_{i+1}': p for i, p in enumerate(remaining[role])}
                targets['return'] = (66, 1050)
                return View('results', likes=remaining[role].copy(), targets=targets)
        class ResultsWindow(FakeWindow):
            def __init__(self, role):
                super().__init__()
                self.role = role

            def click(self, point, **kwargs):
                clicks.append((self.role, point))
                trace.append(('click', self.role, point))
                if point in remaining[self.role]:
                    remaining[self.role].remove(point)
                if point == (66, 1050):
                    states[self.role] = 'world'
                    exit_times[self.role] = runner.control.now()
                    if self.role == 'leader':
                        runner.control.stop()
                return True
        windows = {r: ResultsWindow(r) for r in states}
        runner = Runner(windows, queue.SimpleQueue(), recognizer_factory=ResultsOCR, like_delay=lambda: 0)
        runner.start()
        runner.join(3)
        try:
            self.assertFalse(runner.is_alive())
            points = cleanup_points(results_view())
            self.assertEqual(clicks, [('member', p) for p in points] + [('leader', p) for p in points])
            for role in states:
                indices = [i for i, event in enumerate(trace) if event[0] == 'click'
                           and event[1] == role and event[2] != (66, 1050)]
                self.assertEqual(indices[-1] - indices[0], 3)  # No OCR between four likes.
            self.assertGreaterEqual(runner.engine.requeue_at, exit_times['leader'] + 5)
        finally:
            runner.control.stop()
            runner.join(2)

    def test_random_pause_between_each_like_is_in_requested_range(self):
        runner = Runner({'leader': FakeWindow(), 'member': FakeWindow()}, queue.SimpleQueue())
        runner.sizes['member'] = (600, 1100)
        runner.observe = lambda role: View('results', targets={'return': (66, 1050)})
        with patch('autoqueue.runner.random.uniform', return_value=.35) as random_delay:
            with patch.object(runner.control.stopped, 'wait', return_value=False) as wait:
                self.assertTrue(runner.cleanup('member', results_view()))
        self.assertEqual(random_delay.call_count, 3)
        self.assertTrue(all(c.args == (.2, .5) for c in random_delay.call_args_list))
        self.assertEqual([c.args[0] for c in wait.call_args_list], [.35, .35, .35, .01])

    def test_zero_uncertain_scan_never_sends_exit(self):
        window = FakeWindow()
        runner = Runner({'leader': FakeWindow(), 'member': window}, queue.SimpleQueue(), like_delay=lambda: 0)
        unknown = View('results', targets={'return': (66, 1050)}, likes_ready=False)
        self.assertFalse(runner.cleanup('member', unknown))
        self.assertEqual(window.clicks, [])

    def test_unconfirmed_zero_after_like_batch_still_does_not_exit(self):
        window = FakeWindow()
        runner = Runner({'leader': FakeWindow(), 'member': window}, queue.SimpleQueue(), like_delay=lambda: 0)
        runner.sizes['member'] = (600, 1100)
        runner.observe = lambda role: View('results', targets={'return': (66, 1050)}, likes_ready=False)
        with patch.object(runner.control, 'now', return_value=0):
            self.assertFalse(runner.cleanup('member', results_view()))
        with patch.object(runner.control, 'now', return_value=1.1):
            with patch.object(runner, 'save_diagnostic') as save:
                with self.assertRaisesRegex(SafetyStop, 'results kept open'):
                    runner.cleanup('member', results_view())
                save.assert_called_once_with('member')
        self.assertNotIn((66, 1050), window.clicks)

    def test_still_visible_thumbs_are_retried_before_exit(self):
        windows = {'leader': FakeWindow(), 'member': FakeWindow()}
        runner = Runner(windows, queue.SimpleQueue(), like_delay=lambda: 0)
        runner.sizes['member'] = (600, 1100)
        original = results_view()
        retry = View('results', likes=[(100, 715), (400, 715)],
                     targets={'like_1': (100, 715), 'like_2': (400, 715), 'return': (66, 1050)})
        runner.observe = lambda role: retry
        with patch.object(runner.control, 'now', return_value=0):
            self.assertFalse(runner.cleanup('member', original))
        self.assertNotIn((66, 1050), windows['member'].clicks)
        with patch.object(runner.control, 'now', return_value=.31):
            self.assertFalse(runner.cleanup('member', original))
        runner.observe = lambda role: View('results', targets={'return': (66, 1050)})
        self.assertTrue(runner.cleanup('member', retry))
        self.assertEqual(windows['member'].clicks,
                         list(cleanup_points(original)[:-1]) + [(100, 715), (400, 715), (66, 1050)])


if __name__ == '__main__':
    unittest.main()
