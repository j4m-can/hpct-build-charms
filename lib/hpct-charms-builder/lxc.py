#!/usr/bin/env python3
#
#

import grp
import os
import pwd
import subprocess
import time
import traceback


class LxcInstance:
    """Minimal support for provisioning and working with an Lxc
    instance."""

    def __init__(self, inst_name, **kwargs):
        self.inst_name = inst_name
        self.capture = kwargs.get("capture", False)

    def add_group(self, name, gid):
        return self.exec("--", "groupadd", "-g", str(gid), name)

    def add_user(self, homepath, name, uid, gid, shell):
        self.exec(
            "--",
            "useradd",
            "-d",
            homepath,
            "-g",
            str(gid),
            "-m",
            "-s",
            shell,
            "-u",
            str(uid),
            name,
        )

    def config(self, op, *args, **kwargs):
        capture = kwargs.get("capture", self.capture)
        return subprocess.run(
            ["lxc", "config", op, self.inst_name, *args],
            capture_output=capture,
            text=True,
        )

    def config_device(self, op, *args, **kwargs):
        capture = kwargs.get("capture", self.capture)
        return subprocess.run(
            ["lxc", "config", "device", op, self.inst_name, *args],
            capture_output=capture,
            text=True,
        )

    def exec(self, *args, **kwargs):
        capture = kwargs.get("capture", self.capture)
        cp = subprocess.run(
            ["lxc", "exec", self.inst_name, *args],
            capture_output=capture,
            text=True,
        )
        return cp

    def file(self, op, *args, **kwargs):
        capture = kwargs.get("capture", self.capture)
        return subprocess.run(
            ["lxc", "file", op, *args],
            capture_output=capture,
            text=True,
        )

    def file_pull(self, src, dst, *args, **kwargs):
        capture = kwargs.get("capture", self.capture)
        return subprocess.run(
            ["lxc", "file", "pull", f"{self.inst_name}/{src}", dst, *args],
            capture_output=capture,
            text=True,
        )

    def file_push(self, src, dst, *args, **kwargs):
        capture = kwargs.get("capture", self.capture)
        return subprocess.run(
            ["lxc", "file", "push", src, f"{self.inst_name}/{dst}", *args],
            capture_output=capture,
            text=True,
        )

    def launch(self, image_name, *args, **kwargs):
        capture = kwargs.get("capture", self.capture)
        return subprocess.run(
            ["lxc", "launch", image_name, self.inst_name, *args],
            capture_output=capture,
            text=True,
        )

    def listdir(self, path):
        cp = subprocess.run(
            ["lxc", "exec", self.inst_name, "--", "ls", "-1", path], capture_output=True, text=True
        )

        if cp.returncode == 0:
            return [s for s in cp.stdout.split("\n") if s != ""]
        else:
            return []

    def stop(self, **kwargs):
        capture = kwargs.get("capture", self.capture)
        force = kwargs.get("force", False)
        cmdargs = ["lxc", "stop", self.inst_name]
        if force:
            cmdargs.append("-f")
        return subprocess.run(cmdargs, capture_output=capture, text=True)


def provision(based, charm_dir):
    """Provision an lxc instance for the specified base and mount the
    needed charm directory inside (read only), suitable for building a
    charm in destructive mode.
    """

    def setup_overlay(tag, src, dst):
        # overlay directories
        overlay_base_dir = f"/dev/shm/{tag}-overlay"
        upperdir = f"{overlay_base_dir}/upper"
        workdir = f"{overlay_base_dir}/work"
        mergedir = f"{overlay_base_dir}/merge"

        # create directories
        lxci.exec("--", "mkdir", "-p", upperdir, capture=False)
        lxci.exec("--", "mkdir", "-p", workdir, capture=False)
        lxci.exec("--", "mkdir", "-p", mergedir, capture=False)

        # mount overlay
        lxci.exec(
            "--",
            "mount",
            "-t",
            "overlay",
            "overlay",
            "-o",
            f"lowerdir={src},upperdir={upperdir},workdir={workdir}",
            mergedir,
            capture=False,
        )

        # bind overlay
        lxci.exec("--", "mount", "--bind", mergedir, src, capture=False)

    try:
        # get mount point of charm_dir
        cp = subprocess.run(["df", "--output=target", charm_dir], capture_output=True, text=True)
        if cp.returncode == 1:
            return

        lines = [s for s in cp.stdout.split("\n") if s != ""]
        mount_path = lines[-1]

        inst_id = int(time.time() * 100) % 10000000
        inst_name = f"charms-builder-{inst_id}"
        image_name = based.get("image")

        lxci = LxcInstance(inst_name)

        # launch ephermeral instance with image
        cp = lxci.launch(
            image_name, "-e", "-c", f"raw.idmap=both {os.getuid()} {os.getgid()}", capture=False
        )

        # pass through charm directory/filesystem
        lxci.config_device(
            "add",
            "charmfs",
            "disk",
            f"source={mount_path}",
            f"path={mount_path}",
            "readonly=true",
            capture=False,
        )
        # overlays
        # setup_overlay("etc", "/etc", "/etc")
        setup_overlay("charmfs", mount_path, mount_path)

        # add group and user
        pw = pwd.getpwuid(os.getuid())
        gr = grp.getgrgid(os.getgid())

        lxci.add_group(gr.gr_name, pw.pw_gid)
        lxci.add_user(pw.pw_dir, pw.pw_name, pw.pw_uid, pw.pw_gid, pw.pw_shell)

        return lxci
    except:
        # back out/clean up
        traceback.print_exc()
        lxci.stop()
