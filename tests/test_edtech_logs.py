from edtech_logs import LearnerDeadline, deadline_decision


def test_unsubmitted_learner_past_due_is_reported_overdue():
    deadline = LearnerDeadline("learner-7", "storefront-basics", "2026-10-23", False)

    assert deadline_decision(deadline, "2026-10-24") == "overdue"


def test_submitted_learner_is_complete_even_after_due_date():
    deadline = LearnerDeadline("learner-7", "storefront-basics", "2026-10-23", True)

    assert deadline_decision(deadline, "2026-10-24") == "complete"
