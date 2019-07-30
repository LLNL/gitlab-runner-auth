# Gitlab Runner Registration

## Overview

This script will be run as part of the `ExecStartPre` script in the `systemd`
service file for the Gitlab runners. The net effect is that restarting
a runner will reconcile any authentication issues.

When a host is first set to house a runner, both a shell and batch runner
will be created, their config (an id and token) will be written to a
json file.

Subsequent script runs will check the validity of the existing tokens in
said json file and update them by deleting the current runner and
re-registering them (both shell and batch).

In either case, if there are changes to the batch or shell tokens, they will
then be rewritten to the config.toml file that the runner binary uses to 
connect to Gitlab.

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
