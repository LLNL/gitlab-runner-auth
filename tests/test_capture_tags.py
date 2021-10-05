import pytest
import os
import json
import socket
import stat
import archspec.cpu
from pathlib import Path
from tempfile import TemporaryDirectory
from capture_tags import capture_tags
from jsonschema import validate, ValidationError
from gitlab_runner_config import flatten_values


def test_flatten_dict():
    properties = {
        "hostname": socket.gethostname(),
        "executor_type": "batch",
        "instance": "instance",
        "env": ["1", "2", "3"],
    }
    tags = flatten_values(properties)
    assert tags == [socket.gethostname(), "batch", "instance", "1", "2", "3"]


def test_tag_capture_no_schema():
    arch_info = archspec.cpu.host()
    properties = capture_tags("main", "batch")
    assert properties["architecture"] == arch_info.name
    assert properties["custom"] == []
    with TemporaryDirectory() as td:
        managers = {
            "slurm": os.path.join(td, "salloc"),
            "lsf": os.path.join(td, "bsub"),
            "cobalt": os.path.join(td, "cqsub"),
        }

        os.environ["PATH"] += os.pathsep + td

        def get_tags(exe):
            Path(exe).touch()
            os.chmod(exe, os.stat(exe).st_mode | stat.S_IEXEC)
            tags = capture_tags("main", executor_type="batch")
            os.unlink(exe)
            return flatten_values(tags)

        assert all(manager in get_tags(exe) for manager, exe in managers.items())


def test_tag_capture_schema():
    properties = {
        "hostname": socket.gethostname(),
        "executor_type": "batch",
        "instance": "instance",
        "env": [],
    }
    env = ["mytag", "debian"]
    with open("tag_schema.json") as fh:
        schema = json.load(fh)
    properties.update(capture_tags("main", "batch", env=env, tag_schema=schema))
    validate(properties, schema)
    assert properties["custom"] == ["custom_mytag"]
    assert properties["os"] == "debian"
