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
import logging
import stat
from shutil import which
from urllib.request import Request
from urllib.parse import urlencode, urljoin
from urllib.error import HTTPError
from json import JSONDecodeError

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


class UrlRequester:
    def request(self, request):
        return urllib.request.urlopen(request)


class GitLabClient:
    base_url = ""
    admin_token = ""
    access_token = ""
    requester = UrlRequester()

    def __init__(self, url, admin_token, access_token):
        self.base_url = url
        self.admin_token = admin_token
        self.access_token = access_token

    def list_runners_request(self, query):
        url = urljoin(self.base_url, "runners/all" + query)
        request = Request(url, headers={"PRIVATE-TOKEN": self.access_token})
        return json.load(self.requester.request(request))

    def list_runners(self, filters=None):
        try:
            query = ""
            if filters:
                query = "?" + urlencode(filters)

            return self.list_runners_request(query)
        except JSONDecodeError as e:
            raise RuntimeError("Failed parsing request data JSON") from e
        except HTTPError as e:
            raise RuntimeError(
                "Error listing Gitlab repos: {reason}".format(reason=e.reason)
            ) from e

    def runner_info(self, repo_id):
        try:
            url = urljoin(self.base_url, "runners/" + str(repo_id))
            request = Request(url, headers={"PRIVATE-TOKEN": self.access_token})
            return json.load(self.requester.request(request))
        except JSONDecodeError as e:
            raise RuntimeError("Failed parsing request data JSON") from e
        except HTTPError as e:
            cause = "Error while requesting repo info for repo {repo}: {reason}".format(
                repo=repo_id, reason=e.reason
            )
            raise RuntimeError(cause) from e

    def valid_runner_token_request(self, data):
        url = urljoin(self.base_url, "runners/verify")
        request = Request(url, data=data.encode(), method="POST")
        self.requester.request(request)

    def valid_runner_token(self, token):
        """Test whether or not a runner token is valid"""

        try:
            data = urlencode({"token": token})
            self.valid_runner_token_request(data)
            return True
        except HTTPError as e:
            if e.code == 403:
                return False
            else:
                raise RuntimeError("Error while validating token: {}".format(e.reason))

    def register_runner_request(self, data):
        url = urljoin(self.base_url, "runners")
        request = Request(url, data=data.encode(), method="POST")
        response = self.requester.request(request)
        if response.getcode() == 201:
            return json.load(response)
        else:
            return None

    def register_runner(self, runner_type, tags):
        """Registers a runner and returns its info"""
        try:
            data = urlencode(
                {
                    "token": self.admin_token,
                    "description": tags[0] + "-" + runner_type,
                    "tag_list": ",".join(tags + [runner_type]),
                }
            )

            runner_data = self.register_runner_request(data)
            if runner_data == None:
                raise RuntimeError(
                    "Registration for {runner} failed".format(runner=runner_type)
                )
            return runner_data
        except HTTPError as e:
            cause = (
                "Error registering runner {runner} with tags {tags}: {reason}".format(
                    runner=runner_type, tags=",".join(tags), reason=e.reason
                )
            )
            raise RuntimeError(cause) from e

    def update_runner_token(self, token, runner_type):
        if not token or not self.valid_runner_token(token):
            # no refresh endpoint...delete and re-register
            if token:
                self.delete_runner(token)
            return self.register_runner(
                runner_type, generate_tags(runner_type=runner_type)
            )
        else:
            return None

    def delete_runner_request(self, data):
        url = urljoin(self.base_url, "runners")
        request = Request(url, data=data.encode(), method="DELETE")
        return self.requester.request(request)

    def delete_runner(self, runner_token):
        """Delete an existing runner"""

        try:
            data = urlencode(
                {
                    "token": runner_token,
                }
            )

            response = self.delete_runner_request(data)
            if response.getcode() == 204:
                return True
            else:
                raise RuntimeError("Deleting runner failed")
        except HTTPError as e:
            raise RuntimeError(
                "Error deleting runner: {reason}".format(reason=e.reason)
            ) from e

    def list_gitlab_tags(self):
        filters = {"scope": "shared", "tag_list": ",".join([socket.gethostname()])}
        runners = [self.runner_info(r["id"]) for r in self.list_runners(filters)]
        return set(tag for r in runners for tag in r["tag_list"])

    def update_runner(self, runner_type, token=""):
        gitlab_tags = self.list_gitlab_tags()
        if runner_type not in gitlab_tags:
            # no config template tags in common with Gitlab, register runners
            # for all the tags pulled from the template.
            return self.register_runner(
                runner_type,
                generate_tags(runner_type=runner_type),
            )
        else:
            return self.update_runner_token(token, runner_type)


def create_client(data, clients):
    url = data.get("url", "")
    if url in clients:
        return clients[url]

    # TODO: tokens in the runner configs for multiple gitlab urls, separate?
    admin_token = data.get("admin_token", "")
    access_token = data.get("access_token", "")
    # removing admin/access tokens for future writing out to config.toml
    del data["admin_token"]
    del data["access_token"]

    clients[url] = GitLabClient(url, admin_token, access_token)
    return clients[url]


def read_runner(templates, path, clients):
    """Reads a runner file and generates runner configurations"""
    data_file = os.path.join(templates, path)
    runners = {}
    with open(data_file, "r") as fh:
        runner_config = json.load(fh)
        for runner_type, data in runner_config.items():
            data = data or {}
            name = data.get("name", "")
            if name in runners:
                print("Duplicate runner found for {name}")
                sys.exit(1)

            client = create_client(data, clients)
            runner_type = data.get("executor", "")
            token = data.get("token", "")
            runners[name] = client.update_runner(runner_type, token)
    return runners


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


def update_runner_config(config_template, config_file, internal_config):
    """Using data from config.json, write the config.toml used by the runner

    Nominally, this method will provide a dictionary of keyword arguments to
    format of the form:

    {
        "<runner_type>": "<runner_token>",
        ...,
    }

    The config.toml must specify named template args like:

    [[runners]]
      token = "{runner_type}"
      ...

    and _not_ use positional arguments.
    """

    template_kwargs = {
        "hostname": socket.gethostname(),
    }
    template_kwargs.update(
        {runner: data["token"] for runner, data in internal_config.items()}
    )

    with open(config_template) as th, open(config_file, "w") as ch:
        template = th.read()
        config = template.format(**template_kwargs)
        ch.write(config)


def owner_only_permissions(path):
    st = path.stat()
    return not (bool(st.st_mode & stat.S_IRWXG) and bool(st.st_mode & stat.S_IRWXU))


def configure_runners(prefix, instance):
    """Processes a directory of runners"""

    # cache of gitlab clients
    clients = {}

    runners = {}

    if not all(owner_only_permissions(d) for d in [prefix, instance]):
        logger.error(
            "check permissions on {prefix} or {instance}, too permissive, exiting".format(
                prefix=prefix, instance=instance
            )
        )
        sys.exit(1)

    for filename in os.listdir(instance):
        if filename.endswith(".toml"):
            runners.update(read_runner(instance, filename, clients))

    config_file = os.path.join(prefix, "config.toml")
    config_template = os.path.join(prefix, "config.template")
    update_runner_config(config_template, config_file, runners)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="On the fly runner config")
    parser.add_argument(
        "-p",
        "--prefix",
        default="/etc/gitlab-runner",
        help="The runner config directory prefix",
    )
    parser.add_argument(
        "-i",
        "--instance",
        default="/etc/gitlab-runner/main",
        help="The config template directory for this instance under the configuration directory ",
    )
    args = parser.parse_args()
    configure_runners(args.prefix, args.instance)
