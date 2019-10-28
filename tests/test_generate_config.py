###############################################################################
# Copyright (c) 2019, Lawrence Livermore National Security, LLC
# Produced at the Lawrence Livermore National Laboratory
# Written by Thomas Mendoza mendoza33@llnl.gov
# LLNL-CODE-795365
# All rights reserved
#
# This file is part of gitlab-runner-auth:
# https://github.com/LLNL/gitlab-runner-auth
#
# SPDX-License-Identifier: MIT
###############################################################################

import os
import re
import socket
import toml
import shutil
import json
import pytest
import stat
from pytest import fixture
from pathlib import Path
from tempfile import TemporaryDirectory
from gitlab_runner_config import (
    generate_tags,
    list_runners,
    runner_info,
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
    all_runner_info = (runner_info(base_url, access_token, r["id"])
                       for r in list_runners(base_url, access_token))
    for runner in all_runner_info:
        delete_runner(base_url, runner["token"])


def test_generate_tags():
    tags = generate_tags()
    hostname = socket.gethostname()
    assert hostname == tags[0]
    assert re.sub(r'\d', '', hostname) == tags[1]

    # test finding a resource manager
    with TemporaryDirectory() as td:
        managers = {
            "slurm": os.path.join(td, "salloc"),
            "lsf": os.path.join(td, "bsub"),
            "cobalt": os.path.join(td, "cqsub")
        }

        os.environ["PATH"] += os.pathsep + td

        def get_tags(exe):
            Path(exe).touch()
            os.chmod(exe, os.stat(exe).st_mode | stat.S_IEXEC)
            tags = generate_tags(runner_type="batch")
            os.unlink(exe)
            return tags

        assert all(manager in get_tags(exe)
                   for manager, exe in managers.items())


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


def test_configure_runner_stateless(base_url, admin_token):
    with TemporaryDirectory() as td:
        token_file = os.path.join(base_path, "tests/resources/admin-token")
        access_token_file = os.path.join(
            base_path,
            "tests/resources/access-token"
        )
        config_template = os.path.join(
            base_path,
            "tests/resources/config.template"
        )
        shutil.copy(token_file, td)
        shutil.copy(config_template, td)

        # fails without an access token
        with pytest.raises(SystemExit):
            configure_runner(td, base_url, stateless=True)

        shutil.copy(access_token_file, td)
        configure_runner(td, base_url, stateless=True)

        with open(os.path.join(td, "config.toml")) as fh:
            config = toml.load(fh)
            assert config
            assert len(config["runners"]) == 2
            assert all(r["token"] for r in config["runners"])

        # run a second time, we should get the config.toml back
        # and the same runner tokens
        os.unlink(os.path.join(td, "config.toml"))
        configure_runner(td, base_url, stateless=True)

        with open(os.path.join(td, "config.toml")) as fh:
            assert toml.load(fh) == config
            assert len(config["runners"]) == 2
            assert all(r["token"] for r in config["runners"])
