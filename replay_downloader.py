#!/usr/bin/env python3
# encoding: utf-8

# Licence: MPL 2.0
# Author: Martin Kourim <kourim@protonmail.com>

"""
Module for downloading files from http://replay.dzogchen.net.
It can download from both standard replay and mobile replay.
"""


import os
import re
import sys
import time
import logging
import collections
import configparser
from enum import Enum
from requests import session
from subprocess import Popen, PIPE


# file path, type, class that created the record, audio format, video format
Fileinfo = collections.namedtuple('Fileinfo', 'path type clname audio_f video_f')

# clname, audio_f and video_f are optional
Fileinfo.__new__.__defaults__ = ('', '', '')

# proc is an object returned by Popen, file_record is an instance of FileRecord
Procinfo = collections.namedtuple('Procinfo', 'proc file_record')


class EnvironmentSanityError(EnvironmentError):
    """
    Raise this when environment does not meet expectations.
    """


class Rtypes(Enum):
    """
    Protocols used for downloading the remote file.
    """
    RTMP = 0
    HTTP = 1


class Ftypes(Enum):
    """
    File types that we expect and can work with.
    """
    FLV = 0
    MP3 = 1
    AAC = 2
    MP4 = 3


# mapping of known file types to file extensions
file_ext_d = {
    Ftypes.FLV.name: 'flv',
    Ftypes.MP3.name: 'mp3',
    Ftypes.AAC.name: 'aac',
    Ftypes.MP4.name: 'mp4',
}


class MsgTypes(Enum):
    """
    Types of message queues.
    """
    active = 0
    finished = 1
    skipped = 2
    failed = 3
    errors = 4


class Config:
    """
    Configuration options.
    """
    class __Copts:
        pass

    def __init__(self, cfg_path: str=''):
        """
        Args:
            cfg_path (str): Path to config file.
        """
        # default values
        self.cfg = configparser.ConfigParser()
        self.cfg['DEFAULT'] = {'concurrency': '3',
                               'destination_dir': '',
                               'work_dir': ''}
        self.cfg['AUTH'] = {'login': '', 'password': ''}
        self.cfg['COMMANDS'] = {'rtmpdump': 'rtmpdump', 'ffmpeg': 'ffmpeg'}
        self.cfg['RTMP'] = {'replay_url': 'http://webcast.dzogchen.net/index.php?id=replay',
                            'login_url': 'http://webcast.dzogchen.net/login-exec.php',
                            'list_regex': r'so.addVariable\(\'file\',\'/([^\']*.mp3)\'\);',
                            'replay_rtmp': 'rtmp://78.129.190.44/replay',
                            'player_url': 'http://webcast.dzogchen.net/player.swf',
                            'referer': 'http://webcast.dzogchen.net/index.php?id=replay'}
        self.cfg['HTTP'] = {'replay_url': 'http://webcast.dzogchen.net/index.php?id=mobilereplay',
                            'login_url': 'http://webcast.dzogchen.net/login-exec.php',
                            'list_regex': r'<a href=\"(http:[^\"]*playlist.m3u8)\"'}

        # read config file and override default values
        if os.path.isfile(cfg_path):
            self.cfg.read(cfg_path)

        # create configuration structure with all config values so that it's
        # independent of specific source of configuration (e.g. ini file)
        self.DEFAULT = self.__Copts()
        self.DEFAULT.concurrency = self.cfg.getint('DEFAULT', 'concurrency')
        self.DEFAULT.destination_dir = self.cfg['DEFAULT']['destination_dir']
        self.DEFAULT.work_dir = self.cfg['DEFAULT']['work_dir']
        self.AUTH = self.__Copts()
        self.AUTH.login = self.cfg['AUTH']['login']
        self.AUTH.password = self.cfg['AUTH']['password']
        self.COMMANDS = self.__Copts()
        self.COMMANDS.rtmpdump = self.cfg['COMMANDS']['rtmpdump']
        self.COMMANDS.ffmpeg = self.cfg['COMMANDS']['ffmpeg']
        self.RTMP = self.__Copts()
        self.RTMP.replay_url = self.cfg['RTMP']['replay_url']
        self.RTMP.login_url = self.cfg['RTMP']['login_url']
        self.RTMP.list_regex = self.cfg['RTMP']['list_regex']
        self.RTMP.replay_rtmp = self.cfg['RTMP']['replay_rtmp']
        self.RTMP.player_url = self.cfg['RTMP']['player_url']
        self.RTMP.referer = self.cfg['RTMP']['referer']
        self.HTTP = self.__Copts()
        self.HTTP.replay_url = self.cfg['HTTP']['replay_url']
        self.HTTP.login_url = self.cfg['HTTP']['login_url']
        self.HTTP.list_regex = self.cfg['HTTP']['list_regex']


class ProcScheduler:
    """
    Run processes in parallel via schedulable object.
    Callable object for work pipeline.
    """
    def __init__(self, schedulable_obj):
        """
        The schedulable_obj has 'spawn' and 'finished_handler' methods
        and 'to_do' stack.
        """
        self.avail_slots = 3
        self.running_procs = []
        self.obj = schedulable_obj
        self.to_do = self.obj.to_do
        self.spawn_callback = self.obj.spawn
        self.finish_callback = self.obj.finished_handler

    def _spawn(self) -> bool:
        """
        Run the 'spawn' method of the schedulable_obj for every item
        in the 'to_do' stack. Run up-to 'avail_slots' processes in parallel.
        """
        len_todo = len(self.to_do)
        while (self.avail_slots > 0) and (len_todo > 0):
            procinfo = self.spawn_callback(self.to_do.pop())
            len_todo -= 1
            if procinfo is not None:
                self.running_procs.append(procinfo)
                self.avail_slots -= 1

        # return True if there is nothing left to do
        return(len_todo == 0)

    def _check_running_procs(self) -> bool:
        """
        Check all running processes and call the 'finished_handler'
        method of the schedulable_obj on those that are finished.
        """
        for procinfo in self.running_procs:
            retcode = procinfo.proc.poll()
            if retcode is not None:
                self.running_procs.remove(procinfo)
                self.avail_slots += 1
                self.finish_callback(procinfo)

        # return True if all running processes are finished
        return(len(self.running_procs) == 0)

    def __call__(self) -> bool:
        """
        Return True if there's nothing to do at the moment.
        """
        return all((self._spawn(), self._check_running_procs()))


class Work():
    """
    Maintain list of scheduled actions.
    """
    def __init__(self):
        self.pipeline = []

    def __str__(self):
        return str(self.pipeline)

    def add(self, action):
        """
        Add work (callable object) to pipeline.
        """
        self.pipeline.append(action)


class MsgList:
    """
    Queue of messages with timestamp.
    """
    def __init__(self, text=''):
        self.msglist = []
        self.tstamp = 0  # last time the messages were displayed
        self.text = text

    def __str__(self):
        return '{}, {}, {}'.format(self.msglist, self.text, self.tstamp)

    def __len__(self):
        return len(self.msglist)

    def __getitem__(self, position):
        return self.msglist[position]

    def update_tstamp(self):
        self.tstamp = time.time()

    def add(self, message: str):
        self.msglist.append((message, time.time()))

    def get_new(self):
        """
        New messages iterator.
        """
        # get messages that were not displayed (requested) yet
        for msg in self.msglist:
            if msg[1] >= self.tstamp:
                yield msg[0]
        self.update_tstamp()


class Msgs:
    """
    Print available messages.
    """
    # list of symbols used for displaying progress
    syms = ['.', '+', '*', '#']
    slen = len(syms)

    @staticmethod
    def print_dummy():
        pass

    def get_msglists_with_key(self, key: str):
        """
        Generator of message queues identified by 'key'.
        """
        return (msglist for msglist in _OUT[key]) if key in _OUT else iter(())

    def _print_new(self, key: str, out=sys.stdout):
        for msglist in self.get_msglists_with_key(key):
            for msg in msglist.get_new():
                print('{} {}'.format(msglist.text, msg).strip(), file=out)

    def print_errors(self):
        """
        Print new error messages.
        """
        self._print_new(MsgTypes.errors, sys.stderr)

    def print(self):
        """
        Print new error messages and messages indicating progress.
        """
        self.print_errors()
        self._print_new(MsgTypes.active)

    def print_dots(self):
        """
        Display progress using symbols instead of text messages.
        """
        def _print(sym, msglist):
            for msg in msglist.get_new():
                print(sym, end='')
                sys.stdout.flush()

        for i in self.get_msglists_with_key(MsgTypes.failed):
            _print('F', i)

        for num, li in enumerate(self.get_msglists_with_key(MsgTypes.active)):
            _print(self.syms[num % self.slen], li)

        for i in self.get_msglists_with_key(MsgTypes.skipped):
            _print('S', i)

    def print_summary(self):
        """
        Print summary of the final outcome.
        """
        def _print(key):
            for li in self.get_msglists_with_key(key):
                num = len(li)
                if num > 0:
                    print('{} {} file(s):'.format(li.text, num))
                    for f in li:
                        print('  {}'.format(f[0]))

        print('')

        _print(MsgTypes.finished)
        _print(MsgTypes.failed)
        _print(MsgTypes.skipped)


class FileRecord:
    """
    Record complete history of file transformations.
    """
    def __init__(self, file_info: Fileinfo):
        self.rec = [file_info]

    def __str__(self):
        return str(self.rec)

    def __getitem__(self, position) -> Fileinfo:
        return self.rec[position]

    def add(self, file_info: Fileinfo):
        self.rec.append(file_info)

    def delete(self):
        try:
            self.rec.pop()
        except AttributeError:
            pass


class Download:
    """
    Download specified files. Schedulable object for 'ProcScheduler'.
    """

    part_ext = '.part'

    def __init__(self, conf: Config, to_do: list):
        # check if necassary tools are available
        is_tool(conf.COMMANDS.rtmpdump)
        is_tool(conf.COMMANDS.ffmpeg)

        self.conf = conf
        self.out = {MsgTypes.active: MsgList('Downloading'),
                    MsgTypes.finished: MsgList('Downloaded'),
                    MsgTypes.skipped: MsgList('Skipped download of'),
                    MsgTypes.failed: MsgList('Failed to download'),
                    MsgTypes.errors: MsgList()}
        out_add(self.out)
        self.destination = ''
        self.finished_ready = []
        self.to_do = to_do

    @staticmethod
    def parse_todownload_list(downloads_list: list) -> list:
        """
        Parse the list of files to download and store useful metadata.
        """
        retlist = []
        for i in downloads_list:
            line = i.strip()
            if not line:
                continue
            elif line.startswith('#'):
                continue
            elif line.startswith('http://'):
                retlist.append(FileRecord(Fileinfo(line, Rtypes.HTTP)))
            else:
                retlist.append(FileRecord(Fileinfo('rtmp://' + line, Rtypes.RTMP)))

        return retlist

    def set_destdir(self, destdir: str):
        """
        Set directory where the downloaded files will be saved.
        """
        if destdir == '':
            return

        destdir = os.path.expanduser(destdir)
        try:
            os.makedirs(destdir)
            self.destination = destdir
        except OSError:
            if not os.path.isdir(destdir):
                raise

    def spawn(self, file_record: FileRecord) -> Procinfo:
        """
        Run command for downloading the file in the background
        and record corresponding metadata.
        """
        remote_file_name = file_record[-1].path
        download_type = file_record[-1].type

        if download_type is Rtypes.RTMP:
            # add destination, strip 'rtmp://', strip extension, append '.flv'
            res_file = os.path.join(self.destination,
                                    remove_ext(remote_file_name[7:]) + '.flv')
            res_type = Ftypes.FLV
            audio_format = Ftypes.MP3
            command = [self.conf.COMMANDS.rtmpdump, '--hashes', '--live',
                       '--rtmp', self.conf.RTMP.replay_rtmp + '/' +
                       remote_file_name, '--pageUrl',
                       self.conf.RTMP.referer, '--swfUrl',
                       self.conf.RTMP.replay_url, '--swfVfy',
                       self.conf.RTMP.player_url, '--flv', res_file + self.part_ext]
        elif download_type is Rtypes.HTTP:
            # extract file name from URI
            fname = re.search(r'mp4:([^\/]*)\/', remote_file_name)
            res_file = os.path.join(self.destination, fname.group(1))
            res_type = Ftypes.MP4
            audio_format = Ftypes.AAC
            command = [self.conf.COMMANDS.ffmpeg, '-i',
                       remote_file_name, '-c', 'copy', res_file + self.part_ext]
        else:
            self.out[MsgTypes.errors].add(
                'Error: download failed, unsupported download type for {}'
                .format(remote_file_name))
            self.out[MsgTypes.failed].add(remote_file_name)
            return None
        cur_fileinfo = Fileinfo(res_file, res_type, clname=type(self).__name__,
                                audio_f=audio_format)

        if os.path.isfile(res_file):
            self.out[MsgTypes.errors].add(
                'WARNING: skipping download, file exists: {}'.format(res_file))
            self.out[MsgTypes.skipped].add(res_file)
            file_record.add(cur_fileinfo)
            self.finished_ready.append(file_record)
            return None
        else:
            # run the command
            p = Popen(command, stdout=PIPE, stderr=PIPE)
            # add the file name to 'active' message queue
            self.out[MsgTypes.active].add(res_file)
            # update file history
            file_record.add(cur_fileinfo)
            return Procinfo(p, file_record)

    def finished_handler(self, procinfo: Procinfo) -> int:
        """
        Actions performed when download is finished.
        """
        proc = procinfo.proc
        filepath = procinfo.file_record[-1].path
        filetype = procinfo.file_record[-1].type
        retcode = proc.poll()

        # get stdout and stderr of the command
        (out, err) = proc.communicate()
        if out:
            logit('[download] stdout for {}:'.format(filepath))
            logit(out.decode('utf-8'))
        if err:
            logit('[download] stderr for {}:'.format(filepath), logging.error)
            logit(err.decode('utf-8'), logging.error)

        # If rtmpdump finishes with following message:
        # "Download may be incomplete (downloaded about 99.50%), try resuming"
        # it means that download was ok even though the return value was non-zero
        if (retcode == 2) and (filetype == Ftypes.FLV):
            for each_line in err.decode('utf-8').splitlines():
                m = re.search(r'\(downloaded about 99\.[0-9]+%\),', each_line)
                if m:
                    retcode = 0
                    break

        # check if download was successful
        if retcode == 0:
            try:
                # file.part should exist, rename it to strip the '.part'
                os.rename(filepath + self.part_ext, filepath)
                logit('[rename] {0}.{1} to {0}'.format(filepath, self.part_ext))
                self.out[MsgTypes.finished].add(filepath)
                # file is ready for further processing by next action in 'pipeline'
                self.finished_ready.append(procinfo.file_record)
            except FileNotFoundError as e:
                logit('[rename] failed: {}'.format(e), logging.error)
                retcode = 1
        if retcode != 0:
            self.out[MsgTypes.failed].add(filepath)
            self.out[MsgTypes.errors].add(
                'Error downloading {}: {}'.format(filepath, err.decode('utf-8')))
            # remove last entry from file_record
            proc.file_record.delete()

        return retcode


class ExtractAudio:
    """
    Extract audio from specified files. Schedulable object for 'ProcScheduler'.
    """

    part_ext = '.part'

    def __init__(self, conf: Config, to_do: list):
        # check if 'ffmpeg' is available
        is_tool(conf.COMMANDS.ffmpeg)

        self.conf = conf
        self.out = {MsgTypes.active: MsgList('Extracting audio'),
                    MsgTypes.finished: MsgList('Audio extracting resulted in'),
                    MsgTypes.skipped: MsgList('Skipped extracting audio of'),
                    MsgTypes.failed: MsgList('Failed to extract audio'),
                    MsgTypes.errors: MsgList()}
        out_add(self.out)
        self.destination = ''
        self.finished_ready = []
        self.to_do = to_do

    def set_destdir(self, destdir: str):
        """
        Set directory where the extracted audio files will be saved.
        """
        if destdir == '':
            return

        destdir = os.path.expanduser(destdir)
        try:
            os.makedirs(destdir)
        except OSError:
            if not os.path.isdir(destdir):
                raise
        self.destination = destdir

    def spawn(self, file_record: list) -> Procinfo:
        """
        Run command for extracting the audio in the background
        and record corresponding metadata.
        """
        local_file_name = file_record[-1].path
        file_type = file_record[-1].type
        audio_format = file_record[-1].audio_f
        if audio_format == '':
            self.out[MsgTypes.errors].add(
                'Error: failed to extract, audio format info not passed for {}'
                .format(local_file_name))
            self.out[MsgTypes.failed].add(local_file_name)
            return None

        if file_type == audio_format:
            # nothing to do, passing for further processing
            # by next action in 'pipeline'
            self.finished_ready.append(file_record)
            return None

        fname = '{}.{}'.format(remove_ext(local_file_name),
                               file_ext_d[audio_format.name])
        res_file = os.path.join(self.destination, fname)
        cur_fileinfo = Fileinfo(res_file, audio_format, clname=type(self).__name__,
                                audio_f=audio_format)
        if os.path.isfile(res_file):
            self.out[MsgTypes.errors].add(
                'WARNING: skipping extracting, file exists: {}'.format(res_file))
            self.out[MsgTypes.skipped].add(res_file)
            file_record.add(cur_fileinfo)
            self.finished_ready.append(file_record)
            return None
        else:
            # run the command
            p = Popen([self.conf.COMMANDS.ffmpeg, '-i',
                      local_file_name, '-vn', '-acodec', 'copy', res_file + self.part_ext],
                      stdout=PIPE, stderr=PIPE)
            # add the file name to 'active' message queue
            self.out[MsgTypes.active].add(res_file)
            # update file history
            file_record.add(cur_fileinfo)
            return Procinfo(p, file_record)

    def finished_handler(self, procinfo: Procinfo) -> int:
        """
        Actions performed when extracting is finished.
        """
        proc = procinfo.proc
        filepath = procinfo.file_record[-1].path
        retcode = proc.poll()

        # get stdout and stderr of the command
        (out, err) = proc.communicate()
        if out:
            logit('[extracting] stdout for {}:'.format(filepath))
            logit(out.decode('utf-8'))
        if err:
            logit('[extracting] stderr for {}'.format(filepath), logging.error)
            logit(err.decode('utf-8'), logging.error)

        # check if extracting was successful
        if retcode == 0:
            try:
                # file.part should exist, rename it to strip the '.part'
                os.rename(filepath + self.part_ext, filepath)
                logit('[rename] {0}.{1} to {0}'.format(filepath, self.part_ext))
                self.out[MsgTypes.finished].add(filepath)
                # file is ready for further processing by next action in 'pipeline'
                self.finished_ready.append(procinfo.file_record)
            except FileNotFoundError as e:
                logit('[rename] failed: {}'.format(e), logging.error)
                retcode = 1
        if retcode != 0:
            try:
                os.remove(filepath + self.part_ext)
                logit('[delete] {}'.format(filepath + self.part_ext), logging.error)
            except FileNotFoundError as e:
                self.out[MsgTypes.errors].add(str(e))
            self.out[MsgTypes.failed].add(filepath)
            self.out[MsgTypes.errors].add(
                'Error extracting {}: {}'.format(filepath, err.decode('utf-8')))
            # remove last entry from file_record
            proc.file_record.delete()

        return retcode


class Cleanup:
    """
    Delete all intermediate files. Callable object for work pipeline.
    """

    part_ext = '.part'

    def __init__(self, to_do: list):
        self.out = {MsgTypes.finished: MsgList('Deleted')}
        out_add(self.out)
        self.finished_ready = []
        self.to_do = to_do

    def __call__(self) -> bool:
        """
        Go through every file record and delete all existing files
        except the last one.
        """
        length = len(self.to_do)
        for r in range(length):
            file_record = self.to_do.pop()
            for p in file_record[:-1]:
                try:
                    os.remove(p.path)
                    logit('[cleanup] {}'.format(p.path))
                    self.out[MsgTypes.finished].add(p.path)
                    os.remove(p.path + self.part_ext)
                    logit('[cleanup] {}'.format(p.path + self.part_ext))
                    self.out[MsgTypes.finished].add(p.path + self.part_ext)
                except FileNotFoundError:
                    pass
            # pass for further processing
            self.finished_ready.append(file_record)
        return True


# path to the log file
LOGFILE = None

# dictionary of message queues (active, skipped, etc.)
_OUT = {}


def out_add(out: dict):
    """
    Add message queue to dictionary.
    """
    for key in out:
        # add message queue to dictionary;
        # create the key if it doesn't exist yet
        _OUT.setdefault(key, []).append(out[key])


def remove_ext(filename: str):
    """
    Remove file extension if it really looks like file extension
    (not just something after the dot).
    """
    fname, fext = os.path.splitext(filename)
    return fname if len(fext) == 4 else fname + fext


def log_init(logfile: str):
    """
    Initialize logging.
    """
    if not logfile:
        return

    try:
        logging.basicConfig(filename=logfile, level=logging.DEBUG)
        global LOGFILE
        LOGFILE = logfile
    except EnvironmentError as e:
        print(str(e), file=sys.stderr)


def logit(message: str, method=logging.info):
    """
    Log message.
    """
    if not LOGFILE:
        return

    try:
        for each_line in message.splitlines():
            method(each_line)
    except EnvironmentError as e:
        print(str(e), file=sys.stderr)


def get_replay_list(replay_type: int, conf: Config, outfile: str, append=False):
    """
    Get list of remote files (streams) available for download.
    """
    def _get_session(desc):
        if (conf.AUTH.login == '') or (conf.AUTH.password == ''):
            raise ValueError('Login or password are not configured')

        payload = {
            'login': conf.AUTH.login,
            'password': conf.AUTH.password
        }

        # get available files (streams) from classic replay...
        if replay_type == Rtypes.RTMP:
            conf_section = conf.RTMP
        # ...or from mobile replay
        elif replay_type == Rtypes.HTTP:
            conf_section = conf.HTTP
        else:
            raise ValueError('Unrecognized replay type')

        with session() as c:
            c.post(conf_section.login_url, data=payload)
            response = c.get(conf_section.replay_url)
            for each_line in response.text.splitlines():
                m = re.search(conf_section.list_regex, each_line)
                if m:
                    print(m.group(1), file=desc)

    # output to file or to stdout?
    if outfile == '-':
        _get_session(sys.stdout)
    else:
        with open(outfile, 'a' if append else 'w') as f:
            _get_session(f)


def get_list_from_file(list_file: str) -> list:
    """
    Return list of lines in file.
    """
    try:
        with open(list_file) as f:
            return f.read().splitlines()
    except EnvironmentError as e:
        print(str(e), file=sys.stderr)


def is_tool(name) -> bool:
    """
    Check if it's possible to run the tool.
    """
    try:
        with open(os.devnull, 'w') as devnull:
            Popen([name], stdout=devnull, stderr=devnull)
    except OSError as e:
        raise EnvironmentSanityError(
            "Cannot {} the '{}' command".format(
                'find' if e.errno == os.errno.ENOENT else 'run', name))
    return True


if __name__ == '__main__':
    import argparse

    retval = 0

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
    parser.add_argument('-n', '--no-cleanup',
                        help='don\'t delete intermediate files',
                        action='store_true')
    args = parser.parse_args()

    # no option was passed to the program
    if not len(sys.argv) > 1:
        parser.print_help()
        sys.exit(1)

    # config file specified on command line
    if args.config_file:
        cflist = (args.config_file)
    else:
        # otherwise find config file in default locations
        cflist = ('replay_downloader.ini',
                  os.path.expanduser('~/.config/replay_downloader/replay_downloader.ini'))

    config_file = ''
    for cf in cflist:
        try:
            with open(cf):
                config_file = cf
                break
        except EnvironmentError:
            pass

    if config_file == '':
        if args.config_file:
            print("Error: cannot open config file '{}'".format(args.config_file),
                  file=sys.stderr)
        else:
            print('Error: no config file found.', file=sys.stderr)
        sys.exit(1)

    conf = Config(config_file)

    if args.get_avail:
        get_replay_list(Rtypes.RTMP, conf, args.get_avail, args.append)
        sys.exit(retval)
    elif args.get_avail_mobile:
        get_replay_list(Rtypes.HTTP, conf, args.get_avail_mobile, args.append)
        sys.exit(retval)
    elif args.append:
        parser.print_help()
        print('\n-a (--append) allowed only in combination with ' +
              '-l (--get-avail) and -k (--get-avail-mobile)', file=sys.stderr)
        sys.exit(1)

    # instantiate "messages" and choose how its output will be presented
    msg = Msgs()
    if args.brief:
        msg_handler = msg.print_dots
    elif args.quiet:
        msg_handler = msg.print_dummy
    else:
        msg_handler = msg.print

    # instantiate work pipeline
    work = Work()

    log_init(args.logfile)

    # list of files to download was specified
    if args.get_list:
        downloads_list = get_list_from_file(args.get_list)
    # single file to download was specified
    elif args.download_file:
        downloads_list = [args.download_file]

    # number of concurrent processes
    avail_slots = args.concurrent if args.concurrent > 0 \
        else conf.DEFAULT.concurrency

    # directory where final outcome will be saved
    destdir = args.destination if args.destination \
        else conf.DEFAULT.destination_dir

    # directory for intermediate files
    workdir = args.work_dir if args.work_dir \
        else conf.DEFAULT.work_dir

    #
    # Create the work pipeline. When one step of the pipeline is finished
    # with processing one item from it's stack, the outcome is passed to next
    # step on the pipeline.
    # Work is finished when all steps in the pipeline are finished.
    #

    # get list of files to download
    to_download = Download.parse_todownload_list(downloads_list)

    try:
        downloads = Download(conf, to_download)
        extracting = ExtractAudio(conf, downloads.finished_ready)
    except EnvironmentSanityError as enve:
        print('Error: {}'.format(enve), file=sys.stderr)
        sys.exit(1)

    # download setup
    downloads.set_destdir(workdir)
    downloads_scheduler = ProcScheduler(downloads)
    downloads_scheduler.avail_slots = avail_slots
    work.add(downloads_scheduler)

    # extract audio setup
    extracting.set_destdir(destdir)
    extracting_scheduler = ProcScheduler(extracting)
    extracting_scheduler.avail_slots = avail_slots
    work.add(extracting_scheduler)

    if not args.no_cleanup:
        # cleanup setup
        cleanup = Cleanup(extracting.finished_ready)
        work.add(cleanup)

    try:
        done = False

        # loop until there's no work left to do
        while not done:
            done = True
            for s in work.pipeline:
                t = s()
                if not t:
                    done = False

            # print messages produced during this iterration
            msg_handler()
            time.sleep(0.5)

        if not args.quiet:
            msg.print_summary()

        # determine return value
        if retval == 0:
            for m in msg.get_msglists_with_key(MsgTypes.failed):
                if len(m) > 0:
                    retval = 1
                    break
        if retval == 0:
            for m in msg.get_msglists_with_key(MsgTypes.skipped):
                if len(m) > 0:
                    retval = 2
                    break
    except KeyboardInterrupt:
        print(' Interrupting running processes...')
        retval = 1
        for l in work.pipeline:
            # kill all processes running in the background
            if not hasattr(l, 'running_procs'):
                continue
            for procinfo in l.running_procs:
                proc = procinfo.proc
                if proc.poll() is None:
                    proc.kill()

    sys.exit(retval)
