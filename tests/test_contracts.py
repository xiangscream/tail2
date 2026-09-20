import unittest
from tail2_mvp.contracts import Box, Candidate, Observation, EvidenceState, selection_request, dispatch_outcome


class Contracts(unittest.TestCase):
    def obs(self, **changes):
        data = dict(observation_id="frame1", stream_session="s1", camera_epoch=2, width=640,
                    height=480, received_mono=10.0,
                    candidates=(Candidate("p1", "human", Box(.1,.2,.4,.9), "test"),), mapping_verified=True)
        data.update(changes)
        return Observation(**data)

    def select(self, obs, **changes):
        data = dict(stream_session="s1", camera_epoch=2, now_mono=10.1, max_age_s=1)
        data.update(changes)
        return selection_request(obs, "p1", **data)

    def test_invalid_boxes(self):
        for b in [(0,0,0,1), (0,0,1,0), (0,0,2,1), (float("nan"),0,1,1), (True,0,1,1)]:
            with self.subTest(b=b), self.assertRaises(ValueError):
                Box(*b)

    def test_mirror(self):
        box=Box(.1,.2,.4,.9).mirrored_x()
        self.assertAlmostEqual(box.x1,.6); self.assertAlmostEqual(box.x2,.9)

    def test_selection(self):
        r=self.select(self.obs())
        self.assertEqual(r["op"],"target.select"); self.assertEqual(r["args"]["class"],"human")
        self.assertEqual(r["observation_id"],"frame1")

    def test_uncalibrated(self):
        with self.assertRaises(ValueError): self.select(self.obs(mapping_verified=False))

    def test_stale_or_future(self):
        for t in (9,12):
            with self.assertRaises(ValueError): self.select(self.obs(),now_mono=t)

    def test_session_epoch(self):
        for d in ({"stream_session":"different"},{"camera_epoch":3}):
            with self.assertRaises(ValueError): self.select(self.obs(),**d)

    def test_candidate_identity(self):
        with self.assertRaises(ValueError): self.select(self.obs(candidates=()))
        c=Candidate("p1","human",Box(.1,.1,.9,.9),"test")
        with self.assertRaises(ValueError): self.obs(candidates=(c,c))

    def test_evidence_is_separate(self):
        e=EvidenceState(); e.request("framing","full_body")
        self.assertEqual(e.sdk_reported,{})
        e.report({"mode":"full_body"},"typed_getter",12)
        self.assertIsNone(e.visual_check)
        e.verify_visual("frame2","unsatisfied")
        self.assertEqual(e.visual_check["verdict"],"unsatisfied")
        e.request("framing","half_body"); self.assertIsNone(e.visual_check)

    def test_ack_not_completion(self):
        self.assertEqual(dispatch_outcome({"ok":True}),"accepted_unverified")
        self.assertEqual(dispatch_outcome({"ok":False}),"rejected")
        self.assertEqual(dispatch_outcome({"transport_error":"timeout"}),"indeterminate")
