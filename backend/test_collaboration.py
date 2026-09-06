"""协作翻译服务单元测试（ROADMAP V5.2）。"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.collaboration import (
    MAX_REVISIONS_PER_ROOM,
    CollaborationError,
    CollaborationService,
)


class CollaborationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = CollaborationService()

    def test_create_room_owner_is_member(self) -> None:
        room = self.service.create_room("owner-session", "团队会议")
        self.assertEqual(room.owner_session_id, "owner-session")
        self.assertEqual(room.title, "团队会议")
        self.assertEqual(len(room.members), 1)
        self.assertTrue(room.members[0].is_owner)
        self.assertTrue(room.room_id)

    def test_create_room_empty_owner_rejected(self) -> None:
        with self.assertRaises(CollaborationError):
            self.service.create_room("  ")

    def test_get_room_not_found(self) -> None:
        self.assertIsNone(self.service.get_room("missing"))

    def test_join_room(self) -> None:
        room = self.service.create_room("owner", "会议")
        joined = self.service.join_room(room.room_id, "member-1", "小明")
        self.assertEqual(len(joined.members), 2)
        self.assertEqual(joined.members[1].name, "小明")

    def test_join_room_idempotent(self) -> None:
        room = self.service.create_room("owner", "会议")
        self.service.join_room(room.room_id, "member-1", "小明")
        joined = self.service.join_room(room.room_id, "member-1", "小明")
        self.assertEqual(len(joined.members), 2)

    def test_join_missing_room_rejected(self) -> None:
        with self.assertRaises(CollaborationError):
            self.service.join_room("missing", "member-1")

    def test_leave_member(self) -> None:
        room = self.service.create_room("owner", "会议")
        self.service.join_room(room.room_id, "member-1", "小明")
        self.assertTrue(self.service.leave_room(room.room_id, "member-1"))
        updated = self.service.get_room(room.room_id)
        self.assertIsNotNone(updated)
        if updated is not None:
            self.assertEqual(len(updated.members), 1)

    def test_leave_owner_destroys_room(self) -> None:
        room = self.service.create_room("owner", "会议")
        self.service.join_room(room.room_id, "member-1", "小明")
        self.assertTrue(self.service.leave_room(room.room_id, "owner"))
        self.assertIsNone(self.service.get_room(room.room_id))

    def test_submit_revision(self) -> None:
        room = self.service.create_room("owner", "会议")
        self.service.join_room(room.room_id, "member-1", "小明")
        revision = self.service.submit_revision(
            room.room_id,
            "member-1",
            "seg_1",
            "新的译文",
            source_text="original",
        )
        self.assertEqual(revision.member_name, "小明")
        self.assertEqual(revision.new_text, "新的译文")
        self.assertEqual(revision.source_text, "original")

    def test_submit_revision_member_not_in_room(self) -> None:
        room = self.service.create_room("owner", "会议")
        with self.assertRaises(CollaborationError):
            self.service.submit_revision(room.room_id, "outsider", "seg_1", "译文")

    def test_submit_revision_empty_text_rejected(self) -> None:
        room = self.service.create_room("owner", "会议")
        with self.assertRaises(CollaborationError):
            self.service.submit_revision(room.room_id, "owner", "seg_1", "  ")

    def test_revisions_capped(self) -> None:
        room = self.service.create_room("owner", "会议")
        for index in range(MAX_REVISIONS_PER_ROOM + 10):
            self.service.submit_revision(
                room.room_id,
                "owner",
                f"seg_{index}",
                f"译文 {index}",
            )
        updated = self.service.get_room(room.room_id)
        self.assertIsNotNone(updated)
        if updated is not None:
            self.assertEqual(len(updated.revisions), MAX_REVISIONS_PER_ROOM)

    def test_clear_revisions_only_owner(self) -> None:
        room = self.service.create_room("owner", "会议")
        self.service.join_room(room.room_id, "member-1", "小明")
        self.service.submit_revision(room.room_id, "member-1", "seg_1", "译文")
        with self.assertRaises(CollaborationError):
            self.service.clear_revisions(room.room_id, "member-1")
        cleared = self.service.clear_revisions(room.room_id, "owner")
        self.assertEqual(cleared, 1)

    def test_destroy_room_only_owner(self) -> None:
        room = self.service.create_room("owner", "会议")
        self.service.join_room(room.room_id, "member-1", "小明")
        with self.assertRaises(CollaborationError):
            self.service.destroy_room(room.room_id, "member-1")
        self.assertTrue(self.service.destroy_room(room.room_id, "owner"))
        self.assertIsNone(self.service.get_room(room.room_id))

    def test_list_rooms_excludes_revisions(self) -> None:
        room = self.service.create_room("owner", "会议")
        self.service.submit_revision(room.room_id, "owner", "seg_1", "译文")
        rooms = self.service.list_rooms()
        self.assertEqual(len(rooms), 1)
        self.assertNotIn("revisions", rooms[0])
        self.assertEqual(rooms[0]["member_count"], 1)

    def test_room_id_randomized(self) -> None:
        first = self.service.create_room("a", "一")
        second = self.service.create_room("b", "二")
        self.assertNotEqual(first.room_id, second.room_id)
        self.assertGreater(len(first.room_id), 8)


if __name__ == "__main__":
    unittest.main()
