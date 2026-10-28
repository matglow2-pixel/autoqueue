import unittest

from autoqueue.engine import Engine, SafetyStop, View


def views(leader="world", member="world", leader_likes=(), member_likes=()):
    return {"leader": View(leader, list(leader_likes)),
            "member": View(member, list(member_likes))}


class EngineTests(unittest.TestCase):
    def test_only_leader_opens_and_matches(self):
        e = Engine()
        a = e.step(views(), 0)
        self.assertEqual((a.role, a.kind), ("leader", "dungeon"))
        self.assertIsNone(e.step(views(), 1))
        a = e.step(views("menu"), 2)
        self.assertEqual((a.role, a.kind), ("leader", "match"))
        self.assertIsNone(e.step(views("queue", "queue"), 3))

    def test_accepts_half_a_second_apart_and_does_not_repeat(self):
        e = Engine()
        a = e.step(views("accept", "accept"), 0)
        self.assertEqual(a.role, "leader")
        self.assertIsNone(e.step(views("accept", "accept"), .49))
        a = e.step(views("accept", "accept"), .5)
        self.assertEqual(a.role, "member")
        self.assertIsNone(e.step(views("accept", "accept"), 5))

    def test_declined_match_rearms_accepts_after_prompt_disappears(self):
        e = Engine()
        e.step(views("accept", "accept"), 0)
        e.step(views("accept", "accept"), 1)
        e.step(views("queue", "queue"), 2)
        e.step(views("queue", "queue"), 5)
        self.assertEqual(e.step(views("accept", "accept"), 6).role, "leader")
        self.assertEqual(e.step(views("accept", "accept"), 7).role, "member")

    def test_no_rapid_reclick_for_transient_prompt_loss(self):
        e = Engine()
        e.step(views("accept", "accept"), 0)
        e.step(views("unknown", "accept"), 1)
        self.assertIsNone(e.step(views("accept", "accept"), 2))

    def test_fast_decline_and_rematch_rearms_on_confirmed_queue(self):
        e = Engine()
        e.step(views("accept", "accept"), 0)
        e.step(views("accept", "accept"), 1)
        e.step(views("queue", "queue"), 1.2)
        self.assertEqual(e.step(views("accept", "accept"), 2).role, "leader")
        self.assertEqual(e.step(views("accept", "accept"), 3).role, "member")

    def test_results_handoff_immediately_after_confirmed_return(self):
        e = Engine()
        like = (100, 700)
        both = views("results", "results", [like], [like])
        self.assertIsNone(e.step(both, -2))
        a = e.step(both, 0)
        self.assertEqual((a.role, a.kind), ("leader", "like"))
        self.assertIsNone(e.step(both, 1))  # A click must visibly change the button.
        a = e.step(views("results", "results", [], [like]), 2)
        self.assertEqual((a.role, a.kind), ("leader", "return"))
        waiting = views("world", "results", [], [like])
        a = e.step(waiting, 3)
        self.assertEqual((a.role, a.kind), ("member", "like"))
        a = e.step(views("world", "results"), 4)
        self.assertEqual((a.role, a.kind), ("member", "return"))
        self.assertIsNone(e.step(views(), 5))
        self.assertEqual(e.runs, 1)
        self.assertEqual(e.step(views(), 5.02).kind, "dungeon")

    def test_waits_for_leader_when_member_finishes_first(self):
        self.assertIsNone(Engine().step(views("unknown", "results", [], [(100, 700)]), 0))

    def test_stuck_click_pauses_instead_of_spamming(self):
        e = Engine()
        e.step(views(), 0)
        with self.assertRaises(SafetyStop):
            e.step(views(), 10)

    def test_failed_like_does_not_blindly_leave(self):
        e = Engine()
        v = views("results", "results", [(100, 700)])
        e.step(v, -2)
        e.step(v, 0)
        with self.assertRaises(SafetyStop):
            e.step(v, 4)

    def test_pause_preserves_pending_deadline(self):
        e = Engine()
        e.step(views(), 0)
        e.rebase_after_pause(100)
        self.assertIsNone(e.step(views(), 105))
        with self.assertRaises(SafetyStop):
            e.step(views(), 110)

    def test_unknown_combat_screens_produce_no_actions(self):
        e = Engine()
        for t in (0, 5, 1000):
            self.assertIsNone(e.step(views("unknown", "unknown"), t))
        self.assertIsNone(e.step(views("world", "unknown"), 1001))

    def test_three_likes_before_return(self):
        e = Engine()
        likes = [(100, 700), (300, 700), (500, 700)]
        e.step(views("results", "results", likes), -2)
        for t in range(3):
            action = e.step(views("results", "results", likes), t)
            self.assertEqual(action.kind, "like")
            likes.remove(action.point)
        self.assertEqual(e.step(views("results", "results"), 3).kind, "return")

    def test_results_wait_only_until_buttons_are_readable(self):
        e = Engine()
        unreadable = views("results", "results")
        unreadable["leader"].likes_ready = False
        self.assertIsNone(e.step(unreadable, 0))
        action = e.step(views("results", "results", [(100, 700)]), .02)
        self.assertEqual(action.kind, "like")

    def test_match_click_has_no_fixed_delay_after_dungeon_opens(self):
        e = Engine()
        self.assertEqual(e.step(views(), 0).kind, "dungeon")
        self.assertEqual(e.step(views("menu"), .02).kind, "match")

    def test_unreadable_queue_has_no_timeout_and_late_accept_still_works(self):
        e = Engine()
        self.assertEqual(e.step(views("menu"), 0).kind, "match")
        self.assertIsNone(e.pending[1])
        for now in (15, 30, 60, 120, 3600):
            self.assertIsNone(e.step(views("unknown", "unknown"), now))
        self.assertEqual(e.step(views("accept", "accept"), 3601).role, "leader")
        self.assertIsNone(e.step(views("accept", "accept"), 3601.49))
        self.assertEqual(e.step(views("accept", "accept"), 3601.5).role, "member")

    def test_confirmed_queue_has_no_wait_limit(self):
        e = Engine()
        e.step(views("menu"), 0)
        for now in (1, 60, 3600, 86400):
            self.assertIsNone(e.step(views("queue", "queue"), now))
        self.assertEqual(e.step(views("accept", "accept"), 86401).kind, "accept")

    def test_accept_preempts_an_unrelated_expired_confirmation(self):
        e = Engine()
        e.step(views(), 0)
        self.assertEqual(e.step(views("accept", "accept"), 30).role, "leader")
        self.assertIsNone(e.pending)
        self.assertEqual(e.step(views("accept", "accept"), 30.5).role, "member")

    def test_match_retries_require_the_actual_menu_to_remain_visible(self):
        e = Engine()
        e.step(views("menu"), 0)
        self.assertIsNone(e.step(views("menu"), 1))
        self.assertEqual(e.step(views("menu"), 2).kind, "match")
        self.assertEqual(e.step(views("menu"), 4).kind, "match")
        # Even after retries, unknown/queued screens never cause a timer pause.
        self.assertIsNone(e.step(views("unknown", "unknown"), 60))
        with self.assertRaises(SafetyStop):
            e.step(views("menu"), 61)

    def test_resume_renews_expired_confirmation_instead_of_repausing(self):
        e = Engine()
        e.step(views(), 0)
        with self.assertRaises(SafetyStop):
            e.step(views(), 10)
        e.on_resume(11)
        self.assertIsNone(e.step(views(), 11))
        self.assertEqual(e.step(views("menu"), 12).kind, "match")

    def test_missing_like_detection_does_not_exit_fresh_results(self):
        e = Engine()
        v = views("results", "results")
        v["leader"].likes_ready = False
        self.assertIsNone(e.step(v, 0))
        self.assertIsNone(e.step(v, 5))

    def test_can_exit_after_all_three_like_buttons_disappear(self):
        e = Engine()
        likes = [(100, 700), (300, 700), (500, 700)]
        e.step(views("results", "results", likes), -2)
        for t in range(3):
            action = e.step(views("results", "results", likes), t)
            likes.remove(action.point)
        v = views("results", "results")
        v["leader"].likes_ready = False
        v["leader"].targets["return"] = (70, 1050)
        self.assertEqual(e.step(v, 3).kind, "return")


if __name__ == "__main__":
    unittest.main()
