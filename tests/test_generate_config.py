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
    Runner,
    Executor,
    generate_tags,
    owner_only_permissions,
    load_executors,
    create_runner,
)


base_path = os.getcwd()


@fixture
def runner_config():
    return {
        "name": "foo",
        "client_configs": ["bar", "baz"]
    }


@fixture
def executor_configs():
    configs = []
    url_tmpl = "https://example.com/{}"
    executor_tmpl = "{}-executor"
    for name in ["foo", "bar"]:
        configs.append(
            {"name": name, "url": url_tmpl.format(name), "executor": executor_tmpl.format(name)}
        )
    return configs


@fixture
def executor_tomls_dir(executor_configs):
    td = TemporaryDirectory()
    for config in executor_configs:
        with open(td.name / Path(config["name"] + ".toml"), 'w') as f:
            toml.dump(config, f)
    yield Path(td.name)
    td.cleanup()


@fixture
def executor(executor_configs):
    yield Executor(executor_configs)


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
        assert all(c.get("name") for c in executor.configs)
        assert all(c.get("tags") for c in executor.configs)

    def test_missing_token(self, executor):
        assert len(executor.missing_token()) == len(executor.configs)
        for e in executor.missing_token():
            e["token"] = "token"
        assert len(executor.missing_token()) == 0

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
