# charms-builder

`charms-builder` builds one or more charms, using `charmcraft`,
according to a configuration file. `charms-builder` clones/pulls from
a repo and builds for selected series.

`charms-buidler` also supports building charms for series that are not
supported by `charmcraft` out-of-the-box. This is done by manually
provisioning a container and performing some setup, then running
`charmcraft` in destructive mode inside the container.

## Usage

`charms-builder` takes a command and arguments. The most used command
`build` which will be described here. The others are self-explanatory.

### Configuration

The configuration file uses the yaml format looks like:

```
workdir: <dir>

charmsdir: <dir>

bases:
  - name: <name>
    channel: <channel>
  - name: <name>
    channel: <channel>
    image: <imgname>
  ...

charms:
  <name>:
    repo: <url>
    branch: <branch>|<tag>
  ...
```

`workdir` is the working/scratch directory. `charmsdir` is where the
built charms are copied to. These can be overridden at run time.

`bases` is the set of bases that the collection of charms may be built
for. It looks like the `charmcraft` `bases` section using the brief
specification. The `image` setting specifies an image that is used for
manual provisioning, i.e., when `charmcraft` does not provide one out-of-the-box, or to override the one provided by `charmcraft`. If
`image` is not set, then the default is to depend on `charmcraft`.

`charms` identifies the charms by name and specifies a repository for
each. The `branch` setting is optional.

### Building

Note: A series setting is *always* required.

To build all charms (using defaults and `charms-builder.yaml`
configuration file):

```
charms-builder build
```

To explicitly specify the current directory as the working directory
and charms directory:

```
charms-builder build -c <config> -w . -C charms
```

To build one or more charms by name:

```
charms-builder build charm-one
```

```
charms-builder build charm-one charm-two charm-three
```

To build charms by (glob-style) name pattern:

```
charms-builder build 'charm-t*'
```

## Manual Provisioning

`charmcraft` can be used for building charms on other, non-Ubuntu,
systems. This is typically done on the local machine with the
`--destructive-mode` setting. For `charms-builder` this, too, is done
with the `--destructive-mode` setting but in a specially provisioned
container.

Note: The image is mostly untouched and can be reused.

### Requirements

The following are necessary:

1. `snapd` installed
1. `charmcraft` installed
1. LXD image for the desired series (must have a functional
`charmcraft` installed and any necessary support tools for it to
work).

### Setup

Procedure:

1. Get image name.
1. Get charm directory (where `charmcraft.yaml` is located).
1. Launch LXD image with a unique instance name to an ephemeral
container with `raw.idmap` setting for user uid and gid
1. Pass through build directory/filesystem (containing charm
directory), readonly
1. (container) setup overlay
   1. (container) Create temporary directories for overlays (`upper`,
   `work`, `merge`) in a tmpfs-based filesytem
   1. (container) Mount overlay for build directory/filesystem
   1. (container) Bind mount overlay for build directory/filesystem
1. (container) Create user and group entries (matching uid, gid, etc).

### Running the Build

With the container set up, the destructive mode build can be run
inside the container. The results are then copied to local directory.

### Teardown

When the build is complete, a simple `stop` of the container is
necessary. This how LXC deals with ephemeral instances.

This process can be repeated as many times as wanted, and
concurrently, too.
