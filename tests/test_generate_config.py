import os
import socket
import toml
import shutil
import json
import pytest
import urllib.request
from urllib.request import Request
from urllib.parse import urlencode, urljoin
from urllib.error import HTTPError
from pytest import fixture
from tempfile import TemporaryDirectory
from gitlab_runner_config import (
    generate_tags,
    list_all_repos,
    repo_info,
    valid_runner_token,
    register_runner,
    delete_runner,
    update_runner_config,
    configure_runner,
)


base_path = os.getcwd()


@fixture(scope="session")
def base_url():
    return "http://localhost:8080/api/v4/"


@fixture(scope="session")
def admin_token():
    with open(os.path.join(base_path, "tests/resources/admin-token")) as fh:
        return fh.read()


@fixture(scope="session")
def access_token():
    with open(os.path.join(base_path, "tests/resources/access-token")) as fh:
        return fh.read()


@fixture(scope="module")
def runner_data(base_url, admin_token, access_token):
    data = register_runner(base_url, admin_token, "test", generate_tags())
    yield data
    all_repo_info = (repo_info(base_url, access_token, r["id"])
                     for r in list_all_repos(base_url, access_token))
    for repo in all_repo_info:
        delete_runner(base_url, repo["token"])


def test_generate_tags():
    os.environ["SYS_TYPE"] = "test"
    tags = generate_tags()
    assert socket.gethostname() == tags[0]
    assert "test" in tags


def test_valid_runner_token(base_url, runner_data):
    assert valid_runner_token(base_url, runner_data["token"])


def test_update_runner_config(runner_data):
    with TemporaryDirectory() as td:
        config_file = os.path.join(td, "config.toml")
        config_template = os.path.join(
            base_path, "tests/resources/config.template"
        )
        data = {
            "shell": runner_data,
            "batch": runner_data,
        }
        update_runner_config(config_template, config_file, data)

        with open(config_file) as fh:
            runner_config = toml.load(fh)
            assert all(r["token"] == runner_data["token"]
                       for r in runner_config["runners"])

# end to end


def test_configure_runner(base_url, admin_token):
    with TemporaryDirectory() as td:
        access_token_file = os.path.join(
            base_path,
            "tests/resources/access-token"
        )
        token_file = os.path.join(base_path, "tests/resources/admin-token")
        config_template = os.path.join(
            base_path,
            "tests/resources/config.template"
        )
        shutil.copy(access_token_file, td)
        shutil.copy(token_file, td)
        shutil.copy(config_template, td)

        configure_runner(td, base_url)

        with open(os.path.join(td, "config.toml")) as fh:
            assert toml.load(fh)

        # running twice with a config file in existence will traverse another
        # code path
        configure_runner(td, base_url)

        with open(os.path.join(td, "config.toml")) as fh:
            assert toml.load(fh)

        # originally configured with shell and batch runners, lets make
        # sure that data is in `runner-data.json`
        with open(os.path.join(td, "runner-data.json")) as fh:
            runner_data = json.load(fh)
            assert all(r_type in runner_data for r_type in ["shell", "batch"])

        # should configure stateless as well off of existing runners
        configure_runner(td, base_url, stateless=True)

        with open(os.path.join(td, "config.toml")) as fh:
            assert toml.load(fh)
