#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Licence: MPL 2.0
# Author: Martin Kourim <kourim@protonmail.com>

"""
Module for downloading files from http://replay.dzogchen.net.
It can download from both standard replay and mobile replay.
"""


import argparse
import sys

from replay_downloader import (
    cleanup,
    config,
    download,
    extract_audio,
    log,
    mappings,
    msgs,
    perform,
    utils
)

# for compatibility with older python
try:
    FileNotFoundError
except NameError:
    # pylint: disable=redefined-builtin
    FileNotFoundError = OSError


def cmd_arguments():
    """Command line options."""
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config-file', metavar='FILE',
                        help='configuration file')
    parser.add_argument('-l', '--get-avail', metavar='FILE',
                        help='get list of remote files')
    parser.add_argument('-k', '--get-avail-mobile', metavar='FILE',
                        help='get list of remote files from mobile replay')
    parser.add_argument('-a', '--append', action='store_true',
                        help='append new list of remote files to existing file')
    parser.add_argument('-g', '--get-list', metavar='FILE',
                        help='download all files on list')
    parser.add_argument('-f', '--download-file', metavar='REMOTE_FILE_NAME',
                        help='download remote file')
    parser.add_argument('-p', '--concurrent', metavar='NUM', type=int,
                        help='number of concurrent downloads', default='-1')
    parser.add_argument('-d', '--destination', metavar='DIR',
                        help='directory where final outcome will be saved',
                        default='')
    parser.add_argument('-w', '--work-dir', metavar='DIR',
                        help='directory for intermediate files (current directory by default)',
                        default='')
    parser.add_argument('-m', '--logfile', metavar='FILE',
                        help='log file')
    parser.add_argument('-b', '--brief', help='less verbose output',
                        action='store_true')
    parser.add_argument('-q', '--quiet', help='even less verbose output',
                        action='store_true')
    parser.add_argument('--cleanup',
                        help='delete intermediate files',
                        action='store_true')
    return parser


def get_avail_list(cmd_parser, cfg):
    """Gets list of available recordings and exit."""
    args = cmd_parser.parse_args()
    if args.get_avail:
        download.get_replay_list(mappings.Rtypes.RTMP, cfg, args.get_avail, args.append)
        sys.exit(mappings.ExitCodes.SUCCESS)
    elif args.get_avail_mobile:
        download.get_replay_list(mappings.Rtypes.HTTP, cfg, args.get_avail_mobile, args.append)
        sys.exit(mappings.ExitCodes.SUCCESS)
    elif args.append:
        cmd_parser.print_help()
        print('\n-a (--append) allowed only in combination with '
              '-l (--get-avail) and -k (--get-avail-mobile)', file=sys.stderr)
        sys.exit(mappings.ExitCodes.CONFIG)


def get_list_to_download(args):
    """Returns list of files to download."""
    # list of files to download was specified
    if args.get_list:
        try:
            to_download_list = utils.get_list_from_file(args.get_list)
        except EnvironmentError as emsg:
            print(str(emsg), file=sys.stderr)
            sys.exit(mappings.ExitCodes.CONFIG)
    # single file to download was specified
    elif args.download_file:
        to_download_list = [args.download_file]
    return to_download_list


def get_retval(messages):
    """Determines return value."""
    retval = mappings.ExitCodes.SUCCESS
    for msglist in messages.get_msglists_with_key(mappings.MsgTypes.failed):
        if msglist:
            retval = mappings.ExitCodes.FAIL
            break
    if retval == mappings.ExitCodes.SUCCESS:
        for msglist in messages.get_msglists_with_key(mappings.MsgTypes.skipped):
            if msglist:
                retval = mappings.ExitCodes.INCOMPLETE
                break
    return retval


def main():
    """Run this when launched from command line."""
    cmd_parser = cmd_arguments()
    args = cmd_parser.parse_args()

    # no option was passed to the program
    if len(sys.argv) <= 1:
        cmd_parser.print_help()
        sys.exit(mappings.ExitCodes.CONFIG)

    try:
        cfg = config.get_config_file(args.config_file)
    except EnvironmentError as cfge:
        print('Error: {}'.format(cfge), file=sys.stderr)
        sys.exit(mappings.ExitCodes.CONFIG)

    get_avail_list(cmd_parser, cfg)
    log.log_init(args.logfile)
    messages, msg_handler = msgs.setup_messages(args)

    # instantiate work pipeline
    work = perform.Work()

    # number of concurrent processes
    avail_slots = args.concurrent if args.concurrent > 0 else cfg.RUN.concurrency

    # directory where final outcome will be saved
    dest_dir = args.destination if args.destination else cfg.RUN.destination_dir

    # directory for intermediate files
    workdir = args.work_dir if args.work_dir else cfg.RUN.work_dir

    #
    # Create the work pipeline. When one step of the pipeline is finished
    # with processing one item from it's stack, the outcome is passed to next
    # step on the pipeline.
    # Work is finished when all steps in the pipeline are finished.
    #

    # get processed list of files to download
    to_download = download.Download.parse_todownload_list(get_list_to_download(args))

    # download setup
    downloads = download.Download(cfg, to_download, destination=workdir)
    scheduler = perform.ProcScheduler(downloads, avail_slots)
    work.add(scheduler)

    # extract audio setup
    extracting = extract_audio.ExtractAudio(cfg, downloads.finished_ready, destination=dest_dir)
    scheduler = perform.ProcScheduler(extracting, avail_slots)
    work.add(scheduler)

    if args.cleanup:
        # cleanup setup
        work.add(cleanup.Cleanup(extracting.finished_ready))

    perform.check_required_tools(work)
    perform.do_the_work(work, msg_handler)

    if not args.quiet:
        messages.print_summary()

    sys.exit(get_retval(messages))


if __name__ == '__main__':
    main()
