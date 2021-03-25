# Gitlab Runner Auth

## Overview

This script is run via `ExecStartPre` in the `systemd` service file for Gitlab
runners. The net effect is that restarting a runner will register missing
executors, restore existing executor authentication state, remove non-configured
executors and finally write out a valid `config.toml` file on a per-host basis.

## Setup

```bash
/prefix/runner/
├── config.template.{executors_folder}.toml
└── executors_folder
```

The `config.template.{executors_folder}.toml` contains the same `gitlab-runner`
config, as [specified in GitLab's documentation](https://docs.gitlab.com/runner/configuration/advanced-configuration.html).
In addition, a special property `client_configs` must be specified as an array
of hashes with information on connecting to the GitLab instance you're
registering the runner with. This looks like:

```toml
# /prefix/main/config.template.main.toml
client_configs = [
  {
    url = "https://gitlab.example.com",
    registration_token = "{registration_token}",
    personal_access_token = "{personal_access_token}"
  }
]
```

The `url` property will be used to match `executors` in the `executors_folder`
during the sync process.

The `executors_folder` houses any number of `executor` configurations in `toml`
format. A shell runner that will be configured using the above example client
would look like:

```toml
# /prefix/main/shell.toml
url = "https://gitlab.example.com"
executor = "shell"
```

## Deploy

This script packages with all necessary dependencies using [zipapp](https://docs.python.org/3/library/zipapp.html).
Packaging can be done using the included `package` script. This produces an
executable zip called `register-runner`

To enable the script for use with systemd:

```bash
...
[Service]
ExecStartPre=/path/to/register-runner --prefix /etc/gitlab-runner
ExecStart=/path/to/gitlab-runner --config /etc/gitlab-runner/config.main.toml...
...
```

When starting or restarting the runner, the script will handle syncing the local
executor state in `main` with the target GitLab instance(s) specified in
`config.template.main.toml`.

## Testing

Testing is done using `pytest` with requirements specified in `dev-requirements.txt`

## Release

This code is released under the MIT License.
For more details see the LICENSE File.

SPDX-License-Identifier: MIT

LLNL-CODE-795365
