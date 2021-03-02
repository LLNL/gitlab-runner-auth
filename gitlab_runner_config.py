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
import stat
import socket
import argparse
import toml
import logging
from pathlib import Path
from shutil import which

HOSTNAME = socket.gethostname()
LOGGER_NAME = "gitlab-runner-config"
logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s", level=logging.INFO)
logger = logging.getLogger(LOGGER_NAME)


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
    def __init__(self, config, executor):
        self.config = config
        self.executor = executor

    def empty(self):
        return len(self.executor.configs) == 0

    def to_dict(self):
        config = dict(self.config)
        config["runners"] = self.executor.configs
        return config


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


def load_executors(template_dir):
    executor_configs = []
    for executor_toml in template_dir.glob("*.toml"):
        with executor_toml.open() as et:
            executor_configs.append(toml.load(et))
    return Executor(executor_configs)


def create_runner(config, template_dir):
    config_copy = dict(config)
    del config_copy["client_configs"]
    return Runner(config_copy, load_executors(template_dir))


def owner_only_permissions(path):
    st = path.stat()
    return not (bool(st.st_mode & stat.S_IRWXG) or bool(st.st_mode & stat.S_IRWXO))


def valid_config(config_file, prefix, template_dir):
    if not config_file.is_file():
        logger.error("config.toml is needed for runner registration")
        return False
    if not all(owner_only_permissions(d) for d in [prefix, template_dir]):
        logger.error(
            "permissions on {prefix} or {template} are too permissive".format(
                prefix=prefix, template=template_dir
            )
        )
        return False
    return True


def generate_runner_config(prefix, instance):
    config_file = prefix / "config.toml"
    instance_config_file = prefix / "config.{}.toml".format(instance)
    executor_template_dir = prefix / instance

    if not valid_config(config_file, prefix, executor_template_dir):
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="On the fly runner config")
    parser.add_argument(
        "-p",
        "--prefix",
        default="/etc/gitlab-runner",
        help="""The runner config directory prefix""",
    )
    parser.add_argument(
        "--service-instance", default="main", help="""Instance name from systemd"""
    )
    args = parser.parse_args()
    generate_runner_config(Path(args.prefix), args.service_instance)
