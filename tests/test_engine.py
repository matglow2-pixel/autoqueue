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

    def test_accepts_at_least_one_second_apart_and_does_not_repeat(self):
        e = Engine()
        a = e.step(views("accept", "accept"), 0)
        self.assertEqual(a.role, "leader")
        self.assertIsNone(e.step(views("accept", "accept"), .9))
        a = e.step(views("accept", "accept"), 1)
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

    def test_results_complete_in_order_and_wait_two_seconds_after_return(self):
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
        self.assertIsNone(e.step(waiting, 3))
        self.assertIsNone(e.step(waiting, 4.9))
        a = e.step(waiting, 5)
        self.assertEqual((a.role, a.kind), ("member", "like"))
        a = e.step(views("world", "results"), 6)
        self.assertEqual((a.role, a.kind), ("member", "return"))
        self.assertIsNone(e.step(views(), 7))
        self.assertEqual(e.runs, 1)
        self.assertEqual(e.step(views(), 8).kind, "dungeon")

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

    def test_results_wait_for_button_rendering_before_leaving(self):
        e = Engine()
        self.assertIsNone(e.step(views("results", "results"), 0))
        self.assertIsNone(e.step(views("results", "results"), 1.9))
        action = e.step(views("results", "results", [(100, 700)]), 2)
        self.assertEqual(action.kind, "like")


if __name__ == "__main__":
    unittest.main()
