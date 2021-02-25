import json
import pytest
from gitlab_runner_config import GitLabClient
from gitlab_runner_config import generate_tags
from unittest.mock import Mock
from urllib.error import HTTPError


@pytest.fixture
def requester():
    return Mock()


@pytest.fixture
def gitlab(requester):
    gitlab = GitLabClient("https://gitlab.example.com", "abcdef", "123456")
    gitlab._request = requester
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
    requester.return_value = MockResponse("[{}]", 200)

    assert gitlab.list_runners() == [{}]
    requester.assert_called_once()


def test_list_runners_error(requester, gitlab):
    requester.return_value = MockResponse("[{}]", 500)
    requester.side_effect = HTTPError(
        "https://gitlab.example.com", 500, None, None, None
    )
    try:
        gitlab.list_runners()
        assert False
    except RuntimeError as e:
        assert "Error listing Gitlab repos" in str(e)


def test_list_runners_parse_error(requester, gitlab):
    requester.return_value = MockResponse("[{}", 200)
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
    requester.return_value = MockResponse(runner_data, 200)
    assert gitlab.list_runners() == json.loads(runner_data)
    requester.assert_called_once()


def test_list_runners_filtered(requester, gitlab):
    filters = {"scope": "shared", "tag_list": ",".join(["host1"])}
    requester.return_value = MockResponse("[{}]", 200)
    gitlab.list_runners(filters)
    requester.assert_called_once()
    # TODO: mock with filtered list


def test_valid_runner_token_empty(requester, gitlab):
    requester.return_value = MockResponse("[{}]", 403)
    requester.side_effect = HTTPError(
        "https://gitlab.example.com", 403, None, None, None
    )
    assert not gitlab.valid_runner_token("")
    requester.assert_called_once()


def test_valid_runner_token_valid(requester, gitlab):
    requester.return_value = MockResponse("[{}]", 200)
    assert gitlab.valid_runner_token("abcdef123456")
    requester.assert_called_once()


def test_runner_info(requester, gitlab):
    runner_data = '{ "active": true, "architecture": null, "description": "test-1", "id": 5}'
    requester.return_value = MockResponse(runner_data, 200,)
    assert gitlab.runner_info(5) == json.loads(runner_data)
    requester.assert_called_once()


def test_register_runner(requester, gitlab):
    registration_data = '{"id": "12345", "token": "6337ff"}'
    requester.return_value = MockResponse(registration_data, 201)
    assert gitlab.register_runner("batch", generate_tags("batch"))
    requester.assert_called_once()


def test_register_runner_failure(requester, gitlab):
    requester.return_value = MockResponse("", 403)
    assert not gitlab.register_runner("batch", generate_tags("batch"))
    requester.assert_called_once()


def test_delete_runner(requester, gitlab):
    requester.return_value = MockResponse("", 204)
    assert gitlab.delete_runner("abc123")
    requester.assert_called_once()


def test_delete_runner_failure(requester, gitlab):
    requester.return_value = MockResponse("", 403)
    assert not gitlab.delete_runner("abc123")
    requester.assert_called_once()
