#!/usr/bin/env python3

"""Builder to coordinate the building (using charmcraft) of one or
more charms according to a YAML configuration.
"""

import fnmatch
import os
import os.path
import shutil
import subprocess
import sys
import yaml


class Builder:
    def __init__(self, configpath, workdir=None, charmsdir=None):
        self.configpath = configpath
        self.workdir = workdir
        self.charmsdir = charmsdir

        self.config = yaml.safe_load(open(configpath))
        if workdir:
            self.config["workdir"] = workdir
        if charmsdir:
            self.config["charmsdir"] = charmsdir

    def build(self, name):
        charmsdir = self.config["charmsdir"]
        repo = self.config["charms"][name]["repo"]
        branch = self.config["charms"][name].get("branch") or None
        workdir = self.config["workdir"]
        builddir = f"{workdir}/{name}"

        if not os.path.exists(charmsdir):
            try:
                os.makedirs(charmsdir)
            except:
                pass

        print(f"building charm ({name})")

        print(f"looking for working directory ({builddir})...")
        if not os.path.exists(builddir):
            print("cloning repo ...")
            args = ["git", "clone", repo]
            if branch:
                args.extend(["-b", branch])
            subprocess.run(args, cwd=workdir)
        else:
            print("updating from repo ...")
            subprocess.run(["git", "pull"], cwd=builddir)

        maxtry = 2
        for i in range(1, maxtry + 1):
            print(f"building ({i}/{maxtry}) ...")
            subprocess.run(["charmcraft", "-v", "pack"], cwd=builddir)

            charmpath = f"{builddir}/{name}_ubuntu-22.04-amd64.charm"
            if os.path.exists(charmpath):
                print("copying ...")
                shutil.copy(charmpath, charmsdir)
                break
        else:
            print(f"error: charm ({name}) failed to build")

    def get_built_charm_names(self, pattern=None):
        charmsdir = self.config["charmsdir"]
        for _, _, filenames in os.walk(charmsdir):
            pass
        names = []
        for filename in filenames:
            if "_" in filename:
                names.append(filename[: filename.index("_")])
            else:
                names.append(filename)
        if pattern:
            names = [name for name in names if fnmatch.fnmatch(name, pattern)]
        return sorted(names)

    def get_charm_names(self, pattern=None):
        names = self.config["charms"].keys()
        if pattern:
            names = [name for name in names if fnmatch.fnmatch(name, pattern)]
        return sorted(names)


def print_usage():
    progname = os.path.basename(sys.argv[0])

    print(
        f"""\
usage: {progname} -c <config> [-w workdir] [-C <charmsdir>] [<name|pattern> [...]]
       {progname} -c <config> -l [<pattern> [...]]
       {progname} -c <config> --missing [<pattern> [...]]
       {progname} -h|--help

Build charms by name or pattern.

Options:
-c <path>       Configuration file path.
-C <path>       Charms directory path.
-l              List all known names.
-w <path>       Working directory.
--built         List names of built charms.
--missing       List names for which there is no build."""
    )


if __name__ == "__main__":
    try:
        charmsdir = None
        cmd = "build"
        config = None
        configpath = None
        names = []
        workdir = None

        args = sys.argv[1:]
        while args:
            arg = args.pop(0)
            if arg in ["-h", "--help"]:
                print_usage()
                sys.exit(0)
            elif arg == "-c":
                configpath = args.pop(0)
            elif arg == "-C":
                charmsdir = args.pop(0)
            elif arg == "-l":
                cmd = "list"
            elif arg == "--built":
                cmd = "list-built"
            elif arg == "--missing":
                cmd = "list-missing"
            elif arg == "-w":
                workdir = args.pop(0)
            else:
                names.append(arg)

        if not configpath:
            print("error: missing config path")
            sys.exit(1)
    except SystemExit:
        raise
    except:
        print("error: bad/missing argument")
        sys.exit(1)

    try:
        b = Builder(configpath, workdir, charmsdir)

        if cmd == "list":
            print("\n".join(b.get_charm_names()))
            sys.exit(0)

        if cmd == "list-built":
            print("\n".join(b.get_built_charm_names()))
            sys.exit(0)

        if cmd == "list-missing":
            all_names = set(b.get_charm_names())
            built_names = b.get_built_charm_names()
            print("\n".join(sorted(all_names.difference(built_names))))
            sys.exit(0)

        if cmd == "build":
            for name in names:
                _names = b.get_charm_names(name)
                for _name in _names:
                    b.build(_name)
    except:
        raise
