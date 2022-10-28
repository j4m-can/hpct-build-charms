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

import lxc


class Builder:
    """Charms builder.

    Supports both auto and manual provisioned series. For manual
    provisioning, the `charmcraft.yaml` must specify an lxd image to
    use."""

    def __init__(self, configpath, workdir=None, charmsdir=None, series=None):
        self.configpath = configpath
        self.series = series

        self.config = yaml.safe_load(open(configpath))

        self.charmsdir = os.path.abspath(charmsdir if charmsdir else self.config["charmsdir"])
        self.workdir = os.path.abspath(workdir if workdir else self.config["workdir"])
        self.reposdir = f"{self.workdir}/repos"

    def build(self, name):
        repo = self.config["charms"][name]["repo"]
        branch = self.config["charms"][name].get("branch") or None
        charm_dir = self.get_charm_dir(name)

        for path in [self.charmsdir, self.reposdir]:
            if not os.path.exists(path):
                os.makedirs(path)

        print(f"building charm ({name}) series ({self.series}) ...")

        # clone/update repo
        print(f"looking for charm directory ({charm_dir})...")
        if not os.path.exists(charm_dir):
            print("cloning repo ...")
            args = ["git", "clone", repo]
            if branch:
                args.extend(["-b", branch])
            subprocess.run(args, cwd=self.reposdir)
        else:
            print("updating from repo ...")
            subprocess.run(["git", "pull"], cwd=charm_dir)

        # get base configuration
        based = self.get_series_base(self.series)

        # get charmcraft.yaml base index
        bases_index = self.get_charmcraft_bases_index(charm_dir, self.series)
        if self.series != None and bases_index == None:
            print(f"no base index for series ({self.series})")
            return

        try:
            # provision (if necessary)
            image = based.get("image")
            if not image:
                manual = False
                lxci = None
                print(f"automatic provisioning ...")
            else:
                manual = True
                print(f"manual provisioning ...")
                print("starting container ...")
                lxci = lxc.provision(based, charm_dir)
                if lxci == None:
                    raise Exception(f"failed to provision for image ({image})")

            # build
            maxtry = manual and 1 or 2
            for i in range(1, maxtry + 1):
                print(f"building ({i}/{maxtry}) ...")
                cmdargs = ["charmcraft", "-v", "pack"]
                if manual:
                    cmdargs.append("--destructive-mode")
                    cp = lxci.exec(
                        "--user",
                        str(os.getuid()),
                        "--cwd",
                        charm_dir,
                        "--",
                        *cmdargs,
                    )
                else:
                    if bases_index != None:
                        cmdargs.extend(["--bases-index", str(bases_index)])
                    cp = subprocess.run(cmdargs, cwd=charm_dir)

                # copy results
                if cp.returncode == 0:
                    if manual:
                        filenames = lxci.listdir(charm_dir)
                    else:
                        filenames = os.listdir(charm_dir)

                    for filename in filenames:
                        if filename.endswith(".charm"):
                            charmpath = f"{charm_dir}/{filename}"
                            print(f"copying ({filename}) ...")
                            if manual:
                                lxci.file_pull(charmpath, self.charmsdir)
                            else:
                                shutil.copy(charmpath, self.charmsdir)
                else:
                    print(f"error: charm ({name}) failed to build", file=sys.stderr)
        finally:
            if manual:
                print("stopping container ...")
                lxci.stop(force=True)

    def get_built_charm_names(self, pattern=None):
        for _, _, filenames in os.walk(self.charmsdir):
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

    def get_charm_dir(self, name):
        """Get charm directory (contains `charmcraft.yaml`)."""

        return f"{self.reposdir}/{name}"

    def get_charm_names(self, pattern=None):
        """Get names of all charms."""

        names = self.config["charms"].keys()
        if pattern:
            names = [name for name in names if fnmatch.fnmatch(name, pattern)]

        return sorted(names)

    def get_charmcraft_bases_index(self, charm_dir, series):
        """Get bases index for series from `charmcraft.yaml`."""

        d = yaml.safe_load(open(f"{charm_dir}/charmcraft.yaml"))

        for i, based in enumerate(d.get("bases")):
            _series = f"""{based.get("name")}-{based.get("channel")}"""
            if series == _series:
                return i

    def get_series_base(self, series):
        """Get series bases entry as dict."""

        name, channel = series.split("-", 1)
        for based in self.config.get("bases", []):
            if based.get("name") == name and based.get("channel") == channel:
                return based
        return {}

    def get_serieses(self):
        """Get all series (ok, "es" is not proper!)."""

        names = []
        for based in self.config.get("bases", []):
            names.append(f"""{based["name"]}-{based["channel"]}""")
        return names


def print_usage():
    progname = os.path.basename(sys.argv[0])

    print(
        f"""\
usage: {progname} build [-c <config>] [-w workdir] [-C <charmsdir>] [-s <name>] [<name|pattern> [...]]
       {progname} list [-c <config>] [-s <name>] [<pattern> [...]]
       {progname} list-built [-c <config>] [-s <name>] [<pattern> [...]]
       {progname} list-missing [-c <config>] [-s <name>] [<pattern> [...]]
       {progname} list-series [-c <config>]
       {progname} -h|--help

Build charms by name or pattern.

Commands:
build           Build charm(s).
list            List all charms.
list-built      List built charms.
list-missing    List missing charms.
list-series     List all supported series.

Options:
-c <path>       Configuration file path. Default is
                "charms-builder.yaml".
-C <path>       Charms directory path. Default is "charms".
-s <name>       Series to build for.
-w <path>       Working directory. Default is current directory."""
    )


if __name__ == "__main__":
    try:
        charmsdir = "charms"
        cmd = None
        config = None
        configpath = "charms-builder.yaml"
        names = []
        series = None
        workdir = "."

        args = sys.argv[1:]
        cmd = args.pop(0)

        while args:
            arg = args.pop(0)
            if arg in ["-h", "--help"]:
                print_usage()
                sys.exit(0)
            elif arg == "-c":
                configpath = args.pop(0)
            elif arg == "-C":
                charmsdir = args.pop(0)
            elif arg == "-s":
                series = args.pop(0)
            elif arg == "-w":
                workdir = args.pop(0)
            else:
                names.append(arg)

        if not configpath:
            print("error: missing config path", file=sys.stderr)
            sys.exit(1)
    except SystemExit:
        raise
    except:
        print("error: bad/missing argument", file=sys.stderr)
        sys.exit(1)

    try:
        b = Builder(configpath, workdir, charmsdir, series)

        if cmd == "build":
            _names = []
            for name in names:
                _names.extend(b.get_charm_names(name))

            for _name in _names:
                b.build(_name)

        if cmd == "list":
            print("\n".join(b.get_charm_names(names)))
            sys.exit(0)

        if cmd == "list-built":
            print("\n".join(b.get_built_charm_names(names)))
            sys.exit(0)

        if cmd == "list-missing":
            all_names = set(b.get_charm_names(names))
            built_names = b.get_built_charm_names(names)
            print("\n".join(sorted(all_names.difference(built_names))))
            sys.exit(0)

        if cmd == "list-series":
            serieses = b.get_serieses()
            print("\n".join(sorted(serieses)))
    except:
        raise
