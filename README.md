# Gitlab Runner Auth

## Overview

This script is meant to be run as part of the `ExecStartPre` script in the
`systemd` service file for Gitlab runners. The net effect is that
restarting a runner will reconcile any authentication issues.

### Stateful

When this script runs, it will look for a `runner-data.json` file and register
a new runner for every key in that file. If `runner-data.json` does not exist,
the script will try registering a shell and batch runner by default.

Subsequent script runs will check the validity of the existing tokens in
said json file and update them by deleting the current runner and
re-registering them.

### Stateless

If running with the `--stateless` flag, this script will _not_ write a
`runner-data.json` file. Instead, it will query Gitlab for runners tagged with
the host's hostname. If it finds none, it will create new ones for every runner
"type" it finds in the `config.toml` file. Otherwise, it will use runner info
retrieved from Gitlab to create the `config.toml` from template.

In either case, if there are changes to the runners/tokens, they will then be
rewritten to the `config.toml` file that the runner binary uses (on systemd
start) to connect to Gitlab.

## Setup

```bash
/prefix/runner/
├── access-token
├── admin-token
├── config.template
└── runner-data.json
```

This script expects a set of files in a (configurable) prefix:
* `access-token`: the token used to query the Gitlab api in general, and only
  necessary if using this script in `--stateless` mode
* `admin-token`: the token used to register new runners
* `config.template`: the template for your config.toml file
  * Uses python format string syntax expecting named template variables only
  * Variable names correspond to runner type keys in `runner-data.json`
* `runner-data.json`: holds info retrieved from
  [registering a new runner](https://docs.gitlab.com/ee/api/runners.html#register-a-new-runner),
  which are dicts of the form `{"id": id, "token": token}`. This file will
  _not_ be written if running with the `--stateless` flag.

As mentioned, by default, this script will register both a shell and batch
runner, but if you want to specify more or less using `runner-data.json`, the
file will need to be in the form:

```json
{
  "<runner_type0>": {},
  "<runner_type1>": {}
}
```

and each runner type key mapping to a token will be provided to your
`config.template`. In addition, the system `hostname` will also be provided
to `config.template` to assist in naming runners.

To call `gitlab_runner_auth.py` in the `systemd` service file:

```bash
...
[Service]
ExecStartPre=/path/to/gitlab_runner_auth.py --api-url https://gitlab.example.com --prefix /path/to/runner/prefix --stateless
ExecStart=/path/to/gitlab-runner --config /path/to/runner/prefix/config.toml...
...
```

In effect, this ensures that, before a runner starts, its `config.toml` is
up-to-date and has valid credentials (fails otherwise).

## Testing

To run the included tests, one must first start a Gitlab docker container as
follows:

```bash
docker run \
  --detach \
  --publish 8080:80 \
  --name gitlab-test \
  gitlab/gitlab-ce:latest
```

Visit the newly running gitlab at `http://localhost:8080` and do the first time
setup. With that out of the way, you'll need to get the admin runner token
and copy that into the file `tests/resources/admin-token`.

Make sure you've installed the dev dependencies in `dev-requirements.txt`.

From there, simply run `pytest`.

## Release

This code is released under the MIT License.
For more details see the LICENSE File.

SPDX-License-Identifier: MIT

LLNL-CODE-795365
