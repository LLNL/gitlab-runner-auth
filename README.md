# Gitlab Runner Registration

This script is made to run in the `ExecStartPre` section of the `systemd`
service file for the Gitlab runner. This reduces the complexity of using the
standard runner registration process that would ordinarily clobber any
of our custom runner config.
