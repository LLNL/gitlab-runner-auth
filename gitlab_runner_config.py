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
import importlib
import sys
import stat
import socket
import argparse
import toml
import logging
import gitlab
import json
from jsonschema import validate, ValidationError
from pathlib import Path
from shutil import which
from gitlab.exceptions import (
    GitlabAuthenticationError,
    GitlabConnectionError,
    GitlabHttpError,
)

HOSTNAME = socket.gethostname()
LOGGER_NAME = "gitlab-runner-config"
logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s", level=logging.INFO)
logger = logging.getLogger(LOGGER_NAME)


def identifying_tags(instance):
    identifiers = set([HOSTNAME, re.sub(r"\d", "", HOSTNAME), "managed"])
    if instance in identifiers:
        raise ValueError("instance name cannot be {}".format(identifiers))
    identifiers.add(instance)
    return list(identifiers)


def flatten_values(d):
    """recursively collect dictionary values into a list"""

    if isinstance(d, list):
        combined = []
        for item in d:
            combined += flatten_values(item)
        return combined
    elif isinstance(d, dict):
        combined = []
        for item in d.values():
            combined += flatten_values(item)
        return combined
    else:
        return [d]


def generate_tags(instance, executor_type="", env=None, tag_schema=None):
    """The set of tags for a host

    Minimally, this is the system hostname, but should include things like OS,
    architecture, GPU availability, etc.

    These tags are specified by runner configs and used by CI specs to run jobs
    on the appropriate host.
    """
    properties = {
        "hostname": HOSTNAME,
        "executor_type": executor_type,
        "instance": instance,
        "env": [],
    }
    if env:
        properties["env"] += [os.environ[e] for e in env if e in os.environ]

    try:
        properties.update(
            tagcap.capture_tags(instance, executor_type, env=env, tag_schema=tag_schema)
        )
    except NameError:
        logger.info("Custom Tag Capture method not provided")
    try:
        if tag_schema:
            validate(instance=properties, schema=tag_schema)
        return flatten_values(properties)
    except ValidationError as e:
        logger.error(e)
        # re-raise to handle somewhere higher up. We should fail startup if we can't tag things according to the schema
        raise e


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
    def __init__(self, instance, configs, tag_schema=None):
        self.by_description = {}
        self.instance = instance
        self.configs = configs
        self.tag_schema = tag_schema
        self.normalize()

    def normalize(self):
        for c in self.configs:
            executor = c["executor"]
            c["tags"] = generate_tags(
                self.instance,
                executor_type=executor,
                env=c.get("env_tags"),
                tag_schema=self.tag_schema,
            )
            c["description"] = "{host} {instance} {executor} Runner".format(
                host=HOSTNAME, instance=self.instance, executor=executor
            )
        self.by_description = {c["description"]: c for c in self.configs}

    def add_token(self, executor, token):
        self.by_description[executor]["token"] = token

    def missing_token(self, url):
        return [c for c in self.configs if c["url"] == url and not c.get("token")]

    def missing_required_config(self):
        def required_keys(c):
            return all(
                [
                    c.get("description"),
                    c.get("token"),
                    c.get("url"),
                    c.get("executor"),
                    c.get("tags"),
                ]
            )

        return [c for c in self.configs if not required_keys(c)]


class SyncException(Exception):
    pass


class GitLabClientManager:
    def __init__(self, instance, client_configs):
        self.clients = {}
        self.registration_tokens = {}
        self.instance = instance
        for client_config in client_configs:
            url = client_config["url"]
            self.registration_tokens[url] = client_config["registration_token"]
            self.clients[url] = gitlab.Gitlab(
                url,
                private_token=client_config["personal_access_token"],
            )

    def sync_runner_state(self, runner):
        try:
            for url, client in self.clients.items():
                for r in client.runners.all(
                    tag_list=",".join(identifying_tags(self.instance))
                ):
                    info = client.runners.get(r.id)
                    try:
                        logger.info(
                            "restoring info for {runner}".format(
                                runner=info.description
                            )
                        )
                        runner.executor.add_token(info.description, info.token)
                    except KeyError:
                        # this runner's executor config was removed, it's state should
                        # be deleted from GitLab
                        logger.info(
                            "removing {runner} runner with missing executor config".format(
                                runner=info.description
                            )
                        )
                        client.runners.delete(r.id)

                # executors missing tokens need to be registered
                for missing in runner.executor.missing_token(url):
                    logger.info(
                        "registering {runner}".format(runner=missing["description"])
                    )
                    registration_token = self.registration_tokens[url]
                    info = client.runners.create(
                        {
                            "description": missing["description"],
                            "token": registration_token,
                            "tag_list": ",".join(missing["tags"]),
                            "run_untagged": False,
                        }
                    )
                    runner.executor.add_token(missing["description"], info.token)
        except GitlabAuthenticationError as e:
            raise SyncException(
                "Failed authenticating to GitLab: {reason}".format(reason=e)
            )
        except GitlabConnectionError as e:
            raise SyncException(
                "Unable to connect to GitLab: {reason}".format(reason=e)
            )
        except GitlabHttpError as e:
            raise SyncException(
                "HTTP Error communicating with GitLab: {reason}".format(reason=e)
            )


def load_executors(instance, template_dir, tag_schema=None):
    executor_configs = []
    for executor_toml in template_dir.glob("*.toml"):
        with executor_toml.open() as et:
            executor_configs.append(toml.load(et))
    return Executor(instance, executor_configs, tag_schema)


def create_runner(config, instance, template_dir, tag_schema=None):
    config_copy = dict(config)
    del config_copy["client_configs"]
    return Runner(config_copy, load_executors(instance, template_dir, tag_schema))


def owner_only_permissions(path):
    st = path.stat()
    return not (bool(st.st_mode & stat.S_IRWXG) or bool(st.st_mode & stat.S_IRWXO))


def secure_permissions(prefix, template_dir):
    if not all(owner_only_permissions(d) for d in [prefix, template_dir]):
        return False
    return True


def generate_runner_config(prefix, instance, tag_schema=None):
    instance_config_file = prefix / "config.{}.toml".format(instance)
    instance_config_template_file = prefix / "config.template.{}.toml".format(instance)
    executor_template_dir = prefix / instance

    logger.info(
        "starting config generation using template {template}".format(
            template=instance_config_template_file
        )
    )
    try:
        if not secure_permissions(prefix, executor_template_dir):
            logger.error(
                "permissions on {prefix} or {templates} are too permissive".format(
                    prefix=prefix, templates=executor_template_dir
                )
            )
            sys.exit(1)
        config = toml.loads(instance_config_template_file.read_text())

    except FileNotFoundError as e:
        logger.error(e)
        sys.exit(1)

    runner = create_runner(config, instance, executor_template_dir, tag_schema)
    logger.info(
        "loaded executors from {templates}".format(templates=executor_template_dir)
    )
    client_manager = GitLabClientManager(instance, config["client_configs"])
    try:
        logger.info("syncing state with GitLab(s)")
        client_manager.sync_runner_state(runner)
    except SyncException as e:
        logger.error(e)
        sys.exit(1)

    logger.info("writing config to {config}".format(config=instance_config_file))
    instance_config_file.write_text(toml.dumps(runner.to_dict()))

    logger.info(
        "finished configuring runner for instance {instance}".format(instance=instance)
    )


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
    parser.add_argument(
        "--tag-schema",
        default=None,
        help="""Schema to be applied for tagging executors""",
    )
    parser.add_argument(
        "--capture-tags",
        default="capture_tags",
        help="""Script to capture/generate runner tags""",
    )
    args = parser.parse_args()

    # Assume no schema, but if given a valid file path load it in
    schema = None
    if args.tag_schema and Path(args.tag_schema).is_file():
        with open(args.tag_schema) as fh:
            schema = json.load(fh)
    else:
        logger.info("No schema loaded")

    try:
        tagcap = importlib.import_module(args.capture_tags)
    except ModuleNotFoundError:
        logger.info("Tag capture script could not be read.")
    generate_runner_config(Path(args.prefix), args.service_instance, schema)
