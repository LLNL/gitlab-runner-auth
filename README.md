# Gitlab Runner Registration

This script is made to run in the `ExecStartPre` section of the `systemd`
service file for the Gitlab runner. This reduces the complexity of using the
standard runner registration process that would ordinarily clobber any
of our custom runner config.

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
