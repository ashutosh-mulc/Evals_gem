import pytest

from common.message import Message


def _make(eval_id="q12345", msg_type="REQUEST", status="WORK", sender="agent_tester"):
    return Message(eval_id=eval_id, msg_type=msg_type, status=status, payload="{}", sender=sender)


def test_valid_message_round_trips_through_get_json():
    msg = _make()
    data = msg.get_json()

    assert data["eval_id"] == "q12345"
    assert data["msg_type"] == "REQUEST"
    assert data["status"] == "WORK"
    assert data["sender"] == "agent_tester"
    assert data["payload"] == "{}"
    assert "msg_id" in data and data["msg_id"]


def test_empty_eval_id_is_allowed_for_coordinator_control_messages():
    msg = _make(eval_id="", sender="coordinator")
    assert msg.eval_id == ""


@pytest.mark.parametrize("bad_eval_id", ["q1", "q123456789", "1"])
def test_eval_id_must_be_empty_or_six_characters(bad_eval_id):
    with pytest.raises(AssertionError):
        _make(eval_id=bad_eval_id)


def test_unknown_msg_type_rejected():
    with pytest.raises(AssertionError):
        _make(msg_type="BOGUS")


def test_unknown_status_rejected():
    with pytest.raises(AssertionError):
        _make(status="BOGUS")


def test_unknown_sender_rejected():
    with pytest.raises(AssertionError):
        _make(sender="mystery_process")


def test_check_response_accepts_matching_response():
    msg = _make(sender="agent_tester")
    response = {
        "msg_id": msg.msg_id,
        "msg_type": "RESPONSE",
        "sender": "coordinator",
        "status": "WAIT",
        "payload": "",
        "eval_id": "",
    }
    # Should not raise
    Message.check_response(msg.msg_id, "coordinator", response)


@pytest.mark.parametrize(
    "bad_field,bad_value",
    [("msg_type", "REQUEST"), ("msg_id", "wrong-id"), ("sender", "agent_tester")],
)
def test_check_response_rejects_mismatched_fields(bad_field, bad_value):
    msg = _make(sender="agent_tester")
    response = {
        "msg_id": msg.msg_id,
        "msg_type": "RESPONSE",
        "sender": "coordinator",
        "status": "WAIT",
        "payload": "",
        "eval_id": "",
    }
    response[bad_field] = bad_value

    with pytest.raises(AssertionError):
        Message.check_response(msg.msg_id, "coordinator", response)
