import archspec.cpu
from shutil import which
def capture_tags(instance, executor_type, env=None, tag_schema=None):
    # append system architecture data gathered by archspec to tags
    arch_info = archspec.cpu.host()
    properties = {
        "architecture": arch_info.name,
        "micro-architecture": [],
        "custom": []
    }

    for i in arch_info.ancestors:
        properties["micro-architecture"].append(i.name)
    # if executor is batch, gather some more system info for tags
    if executor_type == "batch":
        if which("bsub"):
            properties["scheduler"] = "lsf"
        elif which("salloc"):
            properties["scheduler"] = "slurm"
        elif which("cqsub"):
            properties["scheduler"] = "cobalt"
    if env:
        if tag_schema:
            for e in env:
                #"tag schema" is to be applied here
                if e in tag_schema["properties"]["os"]["enum"]:
                    properties["os"] = e
                elif e in arch_info.ancestors:
                    pass;
                elif e in tag_schema['properties']['architecture']['enum']:
                    properties["architecture"] = e
                else:
                # if we don't recognize the tag, prepend name 
                    properties["custom"] += tag_schema['custom-name']+"_"+e
    return properties
