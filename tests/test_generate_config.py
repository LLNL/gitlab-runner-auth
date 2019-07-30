import os
import socket
import toml
import pytest
from pytest import fixture
from tempfile import TemporaryDirectory
from generate_config import (
    generate_tags,
    valid_runner_token,
    register_new_runner,
    delete_existing_runner,
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


@fixture(scope="module")
def runner_data(base_url, admin_token):
    data = register_new_runner(base_url, admin_token, "test", generate_tags())
    yield data
    delete_existing_runner(base_url, data["token"], data["id"])


def test_generate_tags():
    tags = generate_tags()
    assert socket.gethostname() == tags[0]


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
            runner_config = toml.loads(fh.read())
            assert all(r["token"] == runner_data["token"]
                       for r in runner_config["runners"])
