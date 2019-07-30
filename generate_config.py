#!/bin/python3

import os
import sys
import socket
import argparse
import json
import urllib.request
from urllib.request import Request
from urllib.parse import urlencode, urljoin
from urllib.error import HTTPError


def generate_tags():
    """The set of tags for a host

    Minimally, this is the system hostname, but should include things like OS,
    architecture, GPU availability, etc.

    These tags are specified by runner configs and used by CI specs to run jobs
    on the appropriate host.
    """

    # TODO: how to generate system tags?
    return [socket.gethostname()]


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


def register_new_runner(base_url, admin_token, runner_type, tags):
    """Registers a runner and returns its info"""

    try:
        # the first tag is always the hostname
        url = urljoin(base_url, "runners")
        data = urlencode({
            "token": admin_token,
            "description": tags[0] + "-" + runner_type,
            "tag_list": ",".join(tags),
        })

        request = Request(url, data=data.encode(), method="POST")
        response = urllib.request.urlopen(request)
        if response.getcode() == 201:
            return json.loads(response.read())
        else:
            print("Registration for {runner_type} failed".format(runner_type))
            sys.exit(1)
    except HTTPError as e:
        print(
            "Error registering runner {runner} with tags {tags}: {reason}"
            .format(runner=runner_type, tags=",".join(tags), reason=e.reason)
        )
        sys.exit(1)


def delete_existing_runner(base_url, runner_token, runner_id):
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
            print("Deleting runner with id {} failed".format(runner_id))
            sys.exit(1)
    except HTTPError as e:
        print(
            "Error deleting runner with id {id}: {reason}"
            .format(id=runner_id, reason=e.reason)
        )
        sys.exit(1)


def update_runner_config(config_template, config_file, internal_config):
    """Using data from config.json, write the config.toml used by the runner"""

    with open(config_template) as th, open(config_file, 'w') as ch:
        template = th.read()
        config = template.format(
            hostname=socket.gethostname(),
            shell_token=internal_config["shell"]["token"],
            batch_token=internal_config["batch"]["token"]
        )
        ch.write(config)


def configure_runner(prefix, api_url):
    """Takes a config template and inputs runner specific variables

    Within the prefix, there must exist a runner admin token for registering
    runners and deleting them.

    This script will be run as part of the ExecStartPre script in the systemd
    service file for the Gitlab runners. The net effect is that restarting
    a runner will reconcile any authentication issues.

    When a host is first set to house a runner, both a shell and batch runner
    will be created, their config (an id and token) will be written to a
    json file.

    Subsequent script runs will check the validity of the existing tokens in
    config and update them by deleting the current runner and re-registering
    one for this host (both shell and batch).

    In either case, if there are changes to these tokens, they will then be
    written to the config.toml file that the runner binary uses to  connect to
    Gitlab.
    """

    tags = generate_tags()
    data_file = os.path.join(prefix, "data.json")
    config_file = os.path.join(prefix, "config.toml")
    config_template = os.path.join(prefix, "config.template")
    admin_token = os.path.join(prefix, "admin-token")

    # read in both tokens we'll need for API access
    with open(admin_token) as fh:
        admin_token = fh.read()

    try:
        # ensure tokens are still valid, otherwise, delete the runner and
        # register it again
        with open(data_file, "r") as fh:
            changed = False
            runner_config = json.loads(fh.read())
            for runner_type, data in runner_config.items():
                if not valid_runner_token(api_url, data["token"]):
                    delete_existing_runner(api_url, data["token"], data["id"])
                    runner_config[runner_type] = register_new_runner(
                        api_url, admin_token, runner_type, tags
                    )
                    changed = True
            if changed:
                with open(data_file, "w") as fh:
                    fh.write(
                        json.dumps(runner_config, sort_keys=True, indent=4)
                    )
                    update_runner_config(
                        config_template,
                        config_file,
                        runner_config
                    )
    except FileNotFoundError:
        # register new runner and write config
        runner_config = {t: register_new_runner(api_url, admin_token, t, tags)
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
    args = parser.parse_args()
    configure_runner(args.prefix, args.api_url)
