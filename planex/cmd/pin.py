"""
planex-pin: generate pin files pointing at local repos
in xenserver-specs/repos/ to override the spec/lnk
"""
from __future__ import print_function

import argparse
import json
import os
import sys

from planex.cmd.args import common_base_parser
from planex.link import Link
from planex.spec import GitBlob, GitArchive, GitPatchqueue, Archive
import planex.spec

RPM_DEFINES = [("dist", "pinned"),
               ("_topdir", "."),
               ("_sourcedir", "%_topdir/SOURCES/%name")]


def load_spec_and_lnk(repo_path, package_name):
    """
    Return the Spec object for
    repo_path/SPECS/package_name updated by the current link.
    Exception("package not present") otherwise.
    """
    partial_file_path = "%s/SPECS/%s" % (repo_path, package_name)

    specname = "%s.spec" % partial_file_path
    if not os.path.isfile(specname):
        sys.exit(
            "Spec file for {} not present in {}/SPECS".format(
                package_name, repo_path))

    linkname = "%s.lnk" % partial_file_path
    link = Link(linkname) if os.path.isfile(linkname) else None
    spec = planex.spec.load(specname, link=link, defines=RPM_DEFINES)

    return spec


def repo_or_path(arg):
    """
    Heuristic. Parse URL:commitish into (URL, commitish) and anything else into
    (URL, None)
    """
    if arg.startswith("ssh://"):
        split = arg.split("#")
        if len(split) > 2 or not split:
            raise ValueError(
                "Expected URL or ssh://URL#commitish but got {}".format(arg))
        if len(split) == 1:
            return (arg, None)
        return tuple(split)

    return (arg, None)

# pylint: disable=too-many-branches


def get_pin_content(args, spec):
    """
    Generate the pinfile content for a Spec.
    """
    pinfile = {"SchemaVersion": "3"}

    if args.source is not None:
        url, commitish = repo_or_path(args.source)
        pinfile["Source0"] = {"URL": url}
        if commitish is not None:
            pinfile["Source0"]["commitish"] = commitish
        return pinfile

    for name, source in spec.resources_dict().items():

        if args.patchqueue is not None and "PatchQueue" in name:
            continue
        if "Patch" in name and "PatchQueue" not in name:
            continue

        pinfile[name] = {"URL": source.url}
        if isinstance(source, (GitBlob, GitArchive, GitPatchqueue)):
            pinfile[name]["commititsh"] = source.commitish
        if isinstance(source, Archive):
            pinfile[name]["prefix"] = source.prefix

    if args.patchqueue is not None:
        url, commitish = repo_or_path(args.patchqueue)
        pinfile["PatchQueue0"] = {"URL": url}
        if commitish is not None:
            pinfile["PatchQueue0"]["commitish"] = commitish

        # Note that in all our current link files, when both a PQ
        # and an Archive are present, these point to the same tarball.
        # This, by default, planex-pin will overwrite the Archive0 with
        # the same content as PatchQueue0
        pinfile["Archive0"] = pinfile["PatchQueue0"]

    return pinfile


def parse_args_or_exit(argv=None):
    """
    Parse command line options
    """

    parser = argparse.ArgumentParser(
        description="Create a .pin file for PACKAGE. "
                    "Needs to run from the root of a spec repository. "
                    "Note that when URL is an ssh url to a git repository, "
                    "planex will first look for a repository with the "
                    "same name cloned in the $CWD/repos folder.",
        parents=[common_base_parser()])
    parser.add_argument("package", metavar="PACKAGE", help="package name")

    write = parser.add_mutually_exclusive_group()
    write.add_argument("-w", "--write", action="store_true",
                       help="Write pin file in PINS/PACKAGE.pin. "
                            "It overwrites the file if present.")
    write.add_argument("-o", "--output", default=None,
                       help="Path of the pinfile to write. "
                            "It overwrites the file if present.")

    overrs = parser.add_mutually_exclusive_group()
    overrs.add_argument("--source-override", dest="source", default=None,
                        help="Path to a tarball or url of a git "
                             "repository in the form ssh://GitURL#commitish. "
                             "When used the pin will get rid of any "
                             "pre-existing source, archive or patchqueue "
                             "and use the provided path as Source0.")
    overrs.add_argument("--patchqueue-override", dest="patchqueue",
                        default=None,
                        help="Path to a tarball or url of a git "
                             "repository in the form ssh://GitURL#commitish. "
                             "When used the pin will get rid of any "
                             "pre-existing patchqueue and use the provided "
                             "path as PatchQueue0.")

    return parser.parse_args(argv)


def main(argv=None):
    """
    Entry point
    """

    args = parse_args_or_exit(argv)

    package_name = args.package
    xs_path = os.getcwd()
    spec = load_spec_and_lnk(xs_path, package_name)
    pin = get_pin_content(args, spec)

    print(json.dumps(pin, indent=2, sort_keys=True))

    output = args.output
    if args.write:
        output = "PINS/{}.pin".format(package_name)

    if output is not None:
        path = os.path.dirname(output)
        if os.path.exists(path):
            with open(output, "w") as out:
                json.dump(pin, out, indent=2, sort_keys=True)
        else:
            sys.exit("Error: path {} does not exist.".format(path))
