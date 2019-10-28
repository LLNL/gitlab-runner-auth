#!/bin/python3

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
import urllib.request
from string import Formatter
from urllib.request import Request
from urllib.parse import urlencode, urljoin
from urllib.error import HTTPError
from json import JSONDecodeError


def generate_tags(runner_type=""):
    """The set of tags for a host

    Minimally, this is the system hostname, but should include things like OS,
    architecture, GPU availability, etc.

    These tags are specified by runner configs and used by CI specs to run jobs
    on the appropriate host.
    """

    # the hostname is _required_ to make this script work, everything else
    # is extra (as far as this script is concerned)
    hostname = socket.gethostname()

    # also tag with the generic cluster name by removing any trailing numbers
    tags = [hostname, re.sub(r'\d', '', hostname)]
    if runner_type == "batch":
        def which(cmd):
            all_paths = (os.path.join(path, cmd) for path in
                         os.environ["PATH"].split(os.pathsep))

            return any(
                os.access(path, os.X_OK) and os.path.isfile(path)
                for path in all_paths
            )

        if which("bsub"):
            tags.append("lsf")
        elif which("salloc"):
            tags.append("slurm")
        elif which("cqsub"):
            tags.append("cobalt")
    return tags


def list_runners(base_url, access_token, filters=None):
    try:
        query = ""
        if filters:
            query = "?" + urlencode(filters)

        url = urljoin(base_url, "runners/all" + query)
        request = Request(url, headers={"PRIVATE-TOKEN": access_token})
        return json.load(urllib.request.urlopen(request))
    except JSONDecodeError:
        print("Failed parsing request data JSON")
        sys.exit(1)
    except HTTPError as e:
        print("Error listing Gitlab repos: {reason}".format(reason=e.reason))
        sys.exit(1)


def runner_info(base_url, access_token, repo_id):
    try:
        url = urljoin(base_url, "runners/" + str(repo_id))
        request = Request(url, headers={"PRIVATE-TOKEN": access_token})
        return json.load(urllib.request.urlopen(request))
    except JSONDecodeError:
        print("Failed parsing request data JSON")
        sys.exit(1)
    except HTTPError as e:
        print("Error while requesting repo info for repo {repo}: {reason}"
              .format(repo=repo_id, reason=e.reason))
        sys.exit(1)


def valid_runner_token(base_url, token):
    """Test whether or not a runner token is valid"""

    try:
        url = urljoin(base_url, "runners/verify")
        data = urlencode({"token": token})

        request = Request(url, data=data.encode(), method="POST")
        urllib.request.urlopen(request)
        return True
    except HTTPError as e:
        if e.code == 403:
            return False
        else:
            print("Error while validating token: {}".format(e.reason))
            sys.exit(1)


def register_runner(base_url, admin_token, runner_type, tags):
    """Registers a runner and returns its info"""

    try:
        # the first tag is always the hostname
        url = urljoin(base_url, "runners")
        data = urlencode({
            "token": admin_token,
            "description": tags[0] + "-" + runner_type,
            "tag_list": ",".join(tags + [runner_type]),
        })

        request = Request(url, data=data.encode(), method="POST")
        response = urllib.request.urlopen(request)
        if response.getcode() == 201:
            return json.load(response)
        else:
            print("Registration for {runner_type} failed".format(runner_type))
            sys.exit(1)
    except HTTPError as e:
        print(
            "Error registering runner {runner} with tags {tags}: {reason}"
            .format(runner=runner_type, tags=",".join(tags), reason=e.reason)
        )
        sys.exit(1)


def delete_runner(base_url, runner_token):
    """Delete an existing runner"""

    try:
        url = urljoin(base_url, "runners")
        data = urlencode({
            "token": runner_token,
        })

        request = Request(url, data=data.encode(), method="DELETE")
        response = urllib.request.urlopen(request)
        if response.getcode() == 204:
            return True
        else:
            print("Deleting runner with id failed")
            sys.exit(1)
    except HTTPError as e:
        print(
            "Error deleting runner: {reason}"
            .format(reason=e.reason)
        )
        sys.exit(1)


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
    template_kwargs.update({runner: data["token"] for runner, data
                            in internal_config.items()})

    with open(config_template) as th, open(config_file, 'w') as ch:
        template = th.read()
        config = template.format(**template_kwargs)
        ch.write(config)


def configure_runner(prefix, api_url, stateless=False):
    """Takes a config template and substitutes runner tokens"""

    runner_config = {}
    config_file = os.path.join(prefix, "config.toml")
    config_template = os.path.join(prefix, "config.template")

    # ensure trailing '/' for urljoin
    if api_url[:-1] != '/':
        api_url += '/'

    with open(os.path.join(prefix, "admin-token")) as fh:
        admin_token = fh.read()

    if stateless:
        with open(config_template) as fh:
            template = fh.read()
        try:
            with open(os.path.join(prefix, "access-token")) as fh:
                access_token = fh.read()
        except FileNotFoundError:
            print("A personal access token is required for stateless mode")
            sys.exit(1)
        filters = {
            "scope": "shared",
            "tag_list": ','.join([socket.gethostname()])
        }
        runner_types = set(token[1] for token in Formatter().parse(template)
                           if token[1] != "hostname" and token[1] is not None)
        runners = [runner_info(api_url, access_token, r["id"]) for r
                   in list_runners(api_url, access_token, filters=filters)]
        gitlab_tags = set(tag for r in runners for tag in r["tag_list"])
        if len(runner_types & gitlab_tags) == 0:
            # no config template tags in common with Gitlab, register runners
            # for all the tags pulled from the template.
            for runner_type in iter(runner_types):
                runner_config[runner_type] = register_runner(
                    api_url,
                    admin_token,
                    runner_type,
                    generate_tags(runner_type=runner_type)
                )
        else:
            for runner in runners:
                try:
                    runner_type = (runner_types
                                   & set(runner["tag_list"])).pop()
                    runner_config[runner_type] = runner
                except KeyError:
                    # we may have picked up a runner which doesn't match our
                    # host, skip it
                    pass
    else:
        try:
            # ensure tokens are still valid, otherwise, delete the runner and
            # register it again
            data_file = os.path.join(prefix, "runner-data.json")
            with open(data_file, "r") as fh:
                changed = False
                runner_config = json.load(fh)
                for runner_type, data in runner_config.items():
                    data = data or {}
                    token = data.get("token", "")
                    if not token or not valid_runner_token(api_url, token):
                        # no refresh endpoint...delete and re-register
                        if token:
                            delete_runner(api_url, token)
                        runner_config[runner_type] = register_runner(
                            api_url,
                            admin_token,
                            runner_type,
                            runner_type=runner_type
                        )
                        changed = True
                if changed:
                    with open(data_file, "w") as fh:
                        fh.write(
                            json.dumps(runner_config, sort_keys=True, indent=4)
                        )
        except FileNotFoundError:
            # defaults to creating both a shell and batch runner
            runner_config = {t: register_runner(
                                    api_url,
                                    admin_token,
                                    t,
                                    generate_tags(runner_type=t)
                                )
                             for t in ["shell", "batch"]}
            with open(data_file, "w") as fh:
                fh.write(
                    json.dumps(runner_config, sort_keys=True, indent=4)
                )

    update_runner_config(
        config_template,
        config_file,
        runner_config
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="On the fly runner config")
    parser.add_argument(
        "-p",
        "--prefix",
        default="/etc/gitlab-runner",
        help="""The runner config directory prefix"""
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8080/api/v4",
        help="""Gitlab API URL"""
    )
    parser.add_argument(
        "--stateless",
        action="store_true",
        help="""If used, disables writing runner-data.json and must query
        Gitlab directly for state.
        """
    )
    args = parser.parse_args()
    configure_runner(args.prefix, args.api_url, stateless=args.stateless)
