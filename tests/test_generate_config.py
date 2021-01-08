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
)


base_path = os.getcwd()


@fixture
def executor_configs():
    configs = []
    url_tmpl = "https://example.com/{}"
    executor_tmpl = "{}-executor"
    for name in ["foo", "bar"]:
        configs.append(
            {"url": url_tmpl.format(name), "executor": executor_tmpl.format(name)}
        )
    return configs


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


class TestExecutorConfigs:
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
