from gitlab_runner_config import GitLabClient
from gitlab_runner_config import generate_tags
import pytest
from unittest.mock import Mock
from urllib.error import HTTPError


@pytest.fixture
def requester():
    requester = Mock()
    return requester


@pytest.fixture
def gitlab(requester):
    gitlab = GitLabClient("https://gitlab.example.com", "abcdef", "123456")
    gitlab.requester = requester
    return gitlab


class MockResponse:
    def __init__(self, data, code):
        self.data = data
        self.code = code

    def getcode(self):
        return self.code

    def read(self, amt=0):
        return self.data


def test_list_runners_empty(requester, gitlab):
    requester.request.return_value = MockResponse("[{}]", 200)
    ret = gitlab.list_runners()
    requester.request.assert_called_once()
    assert (
        requester.request.call_args.args[0].get_full_url()
        == "https://gitlab.example.com/runners/all"
    )
    exp = [{}]
    assert ret == exp


def test_list_runners_error(requester, gitlab):
    requester.request.return_value = MockResponse("[{}]", 500)
    requester.request.side_effect = HTTPError(
        "https://gitlab.example.com", 500, None, None, None
    )
    try:
        gitlab.list_runners()
        assert False
    except RuntimeError as e:
        assert "Error listing Gitlab repos" in str(e)


def test_list_runners_parse_error(requester, gitlab):
    requester.request.return_value = MockResponse("[{}", 200)
    try:
        gitlab.list_runners()
        assert False
    except RuntimeError as e:
        assert "Failed parsing request" in str(e)


def test_list_runners(requester, gitlab):
    runner_data = """[
        {
            "active": true,
            "description": "test-1",
            "id": 6,
            "is_shared": false,
            "ip_address": "127.0.0.1",
            "name": null,
            "online": true,
            "status": "online"
        },
        {
            "active": true,
            "description": "test-2",
            "id": 8,
            "ip_address": "127.0.0.1",
            "is_shared": false,
            "name": null,
            "online": false,
            "status": "offline"
        }
    ]"""
    requester.request.return_value = MockResponse(runner_data, 200)
    ret = gitlab.list_runners()
    requester.request.assert_called_once()
    assert (
        requester.request.call_args.args[0].get_full_url()
        == "https://gitlab.example.com/runners/all"
    )
    exp = [
        {
            "active": True,
            "description": "test-1",
            "id": 6,
            "is_shared": False,
            "ip_address": "127.0.0.1",
            "name": None,
            "online": True,
            "status": "online",
        },
        {
            "active": True,
            "description": "test-2",
            "id": 8,
            "ip_address": "127.0.0.1",
            "is_shared": False,
            "name": None,
            "online": False,
            "status": "offline",
        },
    ]
    assert ret == exp


def test_list_runners_filtered(requester, gitlab):
    filters = {"scope": "shared", "tag_list": ",".join(["host1"])}
    requester.request.return_value = MockResponse("[{}]", 200)
    gitlab.list_runners(filters)
    requester.request.assert_called_once()
    assert (
        requester.request.call_args.args[0].get_full_url()
        == "https://gitlab.example.com/runners/all?scope=shared&tag_list=host1"
    )


def test_valid_runner_token_empty(requester, gitlab):
    requester.request.return_value = MockResponse("[{}]", 403)
    requester.request.side_effect = HTTPError(
        "https://gitlab.example.com", 403, None, None, None
    )
    ret = gitlab.valid_runner_token("")
    requester.request.assert_called_once()
    assert (
        requester.request.call_args.args[0].get_full_url()
        == "https://gitlab.example.com/runners/verify"
    )
    assert not ret


def test_valid_runner_token_valid(requester, gitlab):
    requester.request.return_value = MockResponse("[{}]", 200)
    ret = gitlab.valid_runner_token("abcdef123456")
    requester.request.assert_called_once()
    assert (
        requester.request.call_args.args[0].get_full_url()
        == "https://gitlab.example.com/runners/verify"
    )
    assert ret


def test_runner_info(requester, gitlab):
    requester.request.return_value = MockResponse(
        '{\
        "active": true,\
        "architecture": null,\
        "description": "test-1",\
        "id": 5}',
        200,
    )
    ret = gitlab.runner_info(5)
    requester.request.assert_called_once()
    assert (
        requester.request.call_args.args[0].get_full_url()
        == "https://gitlab.example.com/runners/5"
    )
    exp = {"active": True, "architecture": None, "description": "test-1", "id": 5}
    assert ret == exp


def test_register_runner(requester, gitlab):
    requester.request.return_value = MockResponse(
        '{\
        "id": "12345",\
        "token": "6337ff"\
        }',
        201,
    )
    ret = gitlab.register_runner("batch", generate_tags("batch"))
    requester.request.assert_called_once()
    assert (
        requester.request.call_args.args[0].get_full_url()
        == "https://gitlab.example.com/runners"
    )
    exp = {"id": "12345", "token": "6337ff"}
    assert ret == exp


def test_register_runner_failure(requester, gitlab):
    requester.request.return_value = MockResponse("", 403)
    try:
        gitlab.register_runner("batch", generate_tags("batch"))
        assert False
    except RuntimeError as e:
        assert "Registration for batch failed" in str(e)
    requester.request.assert_called_once()
    assert (
        requester.request.call_args.args[0].get_full_url()
        == "https://gitlab.example.com/runners"
    )


def test_delete_runner(requester, gitlab):
    requester.request.return_value = MockResponse("", 204)
    gitlab.delete_runner("abc123")
    requester.request.assert_called_once()
    assert (
        requester.request.call_args.args[0].get_full_url()
        == "https://gitlab.example.com/runners"
    )


def test_delete_runner_failure(requester, gitlab):
    requester.request.return_value = MockResponse("", 403)
    try:
        gitlab.delete_runner("abc123")
        assert False
    except RuntimeError as e:
        assert "Deleting runner failed" in str(e)
    requester.request.assert_called_once()
    assert (
        requester.request.call_args.args[0].get_full_url()
        == "https://gitlab.example.com/runners"
    )
