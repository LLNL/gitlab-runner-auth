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
import json
import stat
from unittest.mock import MagicMock
from httmock import HTTMock, urlmatch, response
from pytest import fixture
from pathlib import Path
from tempfile import TemporaryDirectory
from gitlab_runner_config import (
    Runner,
    Executor,
    GitLabClientManager,
    generate_tags,
    owner_only_permissions,
    load_executors,
    create_runner,
)


base_path = os.getcwd()


@fixture
def executor_configs():
    configs = []
    url_tmpl = "http://localhost/{}"
    executor_tmpl = "{}-executor"
    for desc in ["foo", "bar"]:
        configs.append(
            {
                "description": "runner-{}".format(desc),
                "url": url_tmpl.format(desc),
                "executor": executor_tmpl.format(desc),
            }
        )
    return configs


@fixture
def client_configs():
    configs = []
    url_tmpl = "http://localhost/{}"
    for server in ["foo", "bar"]:
        configs.append(
            {
                "registration_token": server,
                "url": url_tmpl.format(server),
                "personal_access_token": server,
            }
        )
    return configs


@fixture
def runner_config(client_configs):
    return {"name": "foo", "client_configs": client_configs}


@fixture
def executor_tomls_dir(executor_configs):
    td = TemporaryDirectory()
    for config in executor_configs:
        with open(td.name / Path(config["description"] + ".toml"), "w") as f:
            toml.dump(config, f)
    yield Path(td.name)
    td.cleanup()


@fixture
def executor(executor_configs):
    yield Executor(executor_configs)


@fixture
def url_matchers():
    runners = [{"id": 1}, {"id": 2}]

    @urlmatch(path=r".*\/api\/v4\/runners$", method="get")
    def runner_list_resp(url, request):
        headers = {"content-type": "application/json"}
        content = json.dumps(runners)
        return response(200, content, headers, None, 5, request)

    @urlmatch(path=r".*\/api\/v4\/runners\/\d+$", method="get")
    def runner_detail_resp(url, request):
        runner_id = url.path.split("/")[-1]
        headers = {"content-type": "application/json"}
        content = json.dumps(
            {
                "id": runner_id,
                "token": "token",
                "description": "runner-{}".format(runner_id),
            }
        )
        return response(200, content, headers, None, 5, request)

    @urlmatch(path=r".*\/api\/v4\/runners\/\d+$", method="delete")
    def runner_delete_resp(url, request):
        runner_id = url.path.split("/")[-1]
        headers = {"content-type": "application/json"}
        content = json.dumps(
            {
                "id": runner_id,
                "token": "token",
                "description": "runner-{}".format(runner_id),
            }
        )
        return response(204, content, headers, None, 5, request)

    @urlmatch(path=r".*\/api\/v4\/runners$", method="post")
    def runner_registration_resp(url, request):
        headers = {"content-type": "application/json"}
        # TODO id from request
        content = json.dumps(
            {
                "id": 3,
                "token": "token",
                "description": "runner-{}".format(3),
            }
        )
        return response(201, content, headers, None, 5, request)

    return (
        runner_list_resp,
        runner_detail_resp,
        runner_delete_resp,
        runner_registration_resp,
    )


def test_generate_tags():
    tags = generate_tags()
    hostname = socket.gethostname()
    assert hostname in tags
    assert re.sub(r"\d", "", hostname) in tags

    # test finding a resource manager
    with TemporaryDirectory() as td:
        managers = {
            "slurm": os.path.join(td, "salloc"),
            "lsf": os.path.join(td, "bsub"),
            "cobalt": os.path.join(td, "cqsub"),
        }

        os.environ["PATH"] += os.pathsep + td

        def get_tags(exe):
            Path(exe).touch()
            os.chmod(exe, os.stat(exe).st_mode | stat.S_IEXEC)
            tags = generate_tags(executor_type="batch")
            os.unlink(exe)
            return tags

        assert all(manager in get_tags(exe) for manager, exe in managers.items())


def test_owner_only_permissions():
    with TemporaryDirectory() as td:
        d = Path(td)
        os.chmod(d, 0o700)
        assert owner_only_permissions(d)

        os.chmod(d, 0o750)
        assert not owner_only_permissions(d)

        os.chmod(d, 0o705)
        assert not owner_only_permissions(d)

        os.chmod(d, 0o755)
        assert not owner_only_permissions(d)


class TestExecutor:
    def test_normalize(self, executor):
        executor.normalize()
        assert all(c.get("description") for c in executor.configs)
        assert all(c.get("tags") for c in executor.configs)

    def test_missing_token(self, executor):
        url = executor.configs[0]["url"]
        assert len(executor.missing_token(url)) == 1
        for e in executor.missing_token(url):
            e["token"] = "token"
        assert len(executor.missing_token(url)) == 0

    def test_missing_required_config(self, executor):
        assert len(executor.missing_required_config()) == len(executor.configs)

    def test_load_executors(self, executor_configs, executor_tomls_dir):
        executor = load_executors(executor_tomls_dir)
        assert len(executor.configs) == len(executor_configs)

    def test_load_executors_no_files(self, executor_tomls_dir):
        with TemporaryDirectory() as td:
            executor = load_executors(Path(td))
            assert len(executor.configs) == 0

    def test_load_executors_extra_file(self, executor_configs, executor_tomls_dir):
        with open(executor_tomls_dir / "bat", "w") as fh:
            fh.write("bat")

        # loaded executors should only consider .toml files
        executor = load_executors(executor_tomls_dir)
        assert len(executor.configs) == len(executor_configs)


class TestRunner:
    def test_create(self, runner_config, executor_tomls_dir):
        runner = create_runner(runner_config, executor_tomls_dir)
        assert runner_config.get("client_configs") is not None
        assert runner.config is not None
        assert runner.executor is not None

    def test_empty(self, runner_config):
        runner = Runner(runner_config, Executor([]))
        assert runner.empty()

    def test_to_dict(self, runner_config, executor_tomls_dir):
        runner = create_runner(runner_config, executor_tomls_dir)
        runner_dict = runner.to_dict()
        assert type(runner_dict.get("runners")) == list
        assert toml.dumps(runner_dict)


class TestGitLabClientManager:
    def setup_method(self, method):
        self.runner = MagicMock()

    def test_init(self, client_configs):
        client_manager = GitLabClientManager(client_configs)
        assert client_manager.clients
        assert client_manager.registration_tokens

    def test_sync_runner_state(self, client_configs, url_matchers):
        client_manager = GitLabClientManager(client_configs)

        with HTTMock(*url_matchers):
            client_manager.sync_runner_state(self.runner)
            self.runner.executor.add_token.assert_called()

    def test_sync_runner_state_delete(self, client_configs, url_matchers):
        client_manager = GitLabClientManager(client_configs)
        self.runner.executor.add_token.side_effect = KeyError("Missing key!")
        with HTTMock(*url_matchers):
            client_manager.sync_runner_state(self.runner)
            self.runner.executor.add_token.assert_called()

    def test_sync_runner_state_missing(self, client_configs, url_matchers):
        client_manager = GitLabClientManager(client_configs)
        self.runner.executor.missing_token.return_value = [
            {"description": "bat", "tags": ["bat", "bam"]}
        ]

        with HTTMock(*url_matchers):
            client_manager.sync_runner_state(self.runner)
            self.runner.executor.missing_token.assert_called()
            for config in client_configs:
                self.runner.executor.missing_token.assert_any_call(config["url"])
            self.runner.executor.add_token.assert_called()
