#!/usr/bin/env python3

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
import sys
import socket
import argparse
import json
import toml
import urllib.request
from shutil import which
from string import Formatter
from urllib.request import Request
from urllib.parse import urlencode, urljoin
from urllib.error import HTTPError
from json import JSONDecodeError

HOSTNAME = socket.gethostname()


def host_tags():
    return [HOSTNAME, re.sub(r"\d", "", HOSTNAME)]


def generate_tags(executor_type=""):
    """The set of tags for a host

    Minimally, this is the system hostname, but should include things like OS,
    architecture, GPU availability, etc.

    These tags are specified by runner configs and used by CI specs to run jobs
    on the appropriate host.
    """

    tags = host_tags()
    if executor_type == "batch":
        if which("bsub"):
            tags.append("lsf")
        elif which("salloc"):
            tags.append("slurm")
        elif which("cqsub"):
            tags.append("cobalt")
    return tags


class Runner:
    def __init__(self, config, executor_configs):
        self.config = config
        self.executor_configs = executor_configs

    def to_toml(self):
        config = dict(self.config)
        config["runners"] = self.executor_configs
        return toml.dump(config)


class Executor:
    def __init__(self, configs):
        self.configs = configs
        self.normalize()

    def normalize(self):
        for c in self.configs:
            executor = c["executor"]
            c["tags"] = generate_tags(executor_type=executor)
            c["name"] = "{host} {executor} Runner".format(
                host=HOSTNAME, executor=executor
            )

    def missing_token(self):
        return [c for c in self.configs if not c.get("token")]

    def missing_required_config(self):
        def required_keys(c):
            return all(
                [
                    c.get("name"),
                    c.get("token"),
                    c.get("url"),
                    c.get("executor"),
                    c.get("tags"),
                ]
            )

        return [c for c in self.configs if not required_keys(c)]


def generate_runner_config(prefix, url):
    pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="On the fly runner config")
    parser.add_argument(
        "-p",
        "--prefix",
        default="/etc/gitlab-runner",
        help="""The runner config directory prefix""",
    )
    parser.add_argument(
        "--api-url", default="http://localhost:8080/api/v4", help="""Gitlab API URL"""
    )
    args = parser.parse_args()
    generate_runner_config(args.prefix, args.api_url)
