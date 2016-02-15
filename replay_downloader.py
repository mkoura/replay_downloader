#!/usr/bin/env python3
# encoding: utf-8

# Licence: MPL 2.0
# Author: Martin Kourim <misc.kourim@gmail.com>


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


Fileinfo = collections.namedtuple('Fileinfo', 'path type')
Procinfo = collections.namedtuple('Procinfo', 'proc_o path type')


class Rtypes(Enum):
    RTMP = 0
    HTTP = 1


class Ftypes(Enum):
    FLV = 0
    MP3 = 1
    AAC = 2
    MP4 = 3


class MsgTypes(Enum):
    active = 0
    finished = 1
    skipped = 2
    failed = 3
    errors = 4


class Config:
    class __Copts:
        pass

    def __init__(self, cfg_path: str=''):
        self.cfg = configparser.ConfigParser()
        self.cfg['DEFAULT'] = {'concurrency': '3'}
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

        if os.path.isfile(cfg_path):
            self.cfg.read(cfg_path)

        self.DEFAULT = self.__Copts()
        self.DEFAULT.concurrency = self.cfg.getint('DEFAULT', 'concurrency')
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


class Scheduler:
    def __init__(self, schedulable_obj):
        self.avail_slots = 3
        self.running_procs = []
        self.obj = schedulable_obj
        self.to_do = self.obj.to_do
        self.spawn_callback = self.obj.spawn
        self.finish_callback = self.obj.finished_handler

    def _spawn(self) -> bool:
        while ((self.avail_slots != 0) and (len(self.to_do) != 0)):
            procinfo = self.spawn_callback(self.to_do.pop())
            if procinfo is not None:
                self.running_procs.append(procinfo)
                self.avail_slots -= 1

        return(len(self.to_do) == 0)

    def _check_running_procs(self) -> bool:
        for procinfo in self.running_procs:
            retcode = procinfo.proc_o.proc.poll()
            if retcode is not None:
                self.running_procs.remove(procinfo)
                self.avail_slots += 1
                self.finish_callback(procinfo)

        return(len(self.running_procs) == 0)

    def __call__(self) -> bool:
        s = self._spawn()
        c = self._check_running_procs()
        return(s and c)

    def get_scheduled_obj(self):
        return self.obj


class Schedulers():
    def __init__(self):
        self.pipeline = []
        self.scheduled_objs = []
        self.on_update_hooks = []

    def add(self, scheduler: Scheduler):
        self.pipeline.append(scheduler)
        self.scheduled_objs.append(scheduler.get_scheduled_obj())
        for h in self.on_update_hooks:
            h(self)


class MsgList:
    def __init__(self, text=''):
        self.msglist = []
        self.tstamp = 0
        self.text = text

    def update_tstamp(self):
        self.tstamp = time.time()

    def add(self, message: str):
        self.msglist.append((message, time.time()))

    def clear(self):
        del self.msglist[:]

    def get_new(self) -> list:
        retlist = [msg[0] for msg in self.msglist if msg[1] >= self.tstamp]
        self.update_tstamp()
        return retlist


class Msgs:
    syms = ['.', '+', '*', '#']
    slen = len(syms)

    def __init__(self):
        self._outlist = []
        self._scheduled_outlist = []
        self._combined_outlist = []

    @staticmethod
    def print_dummy():
        pass

    def add_to_outlist(self, new_msglist: MsgList):
        self._outlist.append(new_msglist)
        del self._combined_outlist[:]
        self._combined_outlist.extend(self._outlist)
        self._combined_outlist.extend(self._scheduled_outlist)

    def schedulers_update_hook(self, schedulers: Schedulers):
        self._scheduled_outlist = [l.out for l in schedulers.scheduled_objs
                                   if hasattr(l, 'out')]
        del self._combined_outlist[:]
        self._combined_outlist.extend(self._outlist)
        self._combined_outlist.extend(self._scheduled_outlist)

    def get_outlist(self):
        return self._combined_outlist

    def get_msglists_with_key(self, key: str):
        return [d[key] for d in self._combined_outlist if key in d]

    def _print_new(self, key: str, out=sys.stdout):
        for msglist in self.get_msglists_with_key(key):
            for msg in msglist.get_new():
                print("" + msglist.text + " " + msg, file=out)

    def print_errors(self):
        self._print_new(MsgTypes.errors, sys.stderr)

    def print(self):
        self.print_errors()
        self._print_new(MsgTypes.active)

    def print_dots(self):
        def _print(sym, msglist):
            for msg in msglist.get_new():
                print(sym, end="")
                sys.stdout.flush()

        for i in self.get_msglists_with_key(MsgTypes.failed):
            _print('F', i)

        for num, li in enumerate(self.get_msglists_with_key(MsgTypes.active)):
            _print(self.syms[num % self.slen], li)

        for i in self.get_msglists_with_key(MsgTypes.skipped):
            _print('S', i)

    def print_summary(self):
        def _print(key):
            for li in self.get_msglists_with_key(key):
                num = len(li.msglist)
                if (num > 0):
                    print("" + li.text + " " + str(num) + " file(s):")
                    for f in li.msglist:
                        print("    " + f[0])

        print("")

        _print(MsgTypes.finished)
        _print(MsgTypes.failed)
        _print(MsgTypes.skipped)


class Proc:
    def __init__(self, proc):
        self.proc = proc


class Download:
    def __init__(self, conf: Config, to_do: list):
        self.conf = conf
        self.out = {MsgTypes.active: MsgList("Downloading"),
                    MsgTypes.finished: MsgList("Downloaded"),
                    MsgTypes.skipped: MsgList("Skipped download of"),
                    MsgTypes.failed: MsgList("Failed to download"),
                    MsgTypes.errors: MsgList()}
        self.destination = ''
        self.finished_ready = []
        self.to_do = to_do

    @staticmethod
    def parse_todownload_list(downloads_list: list) -> list:
        retlist = []
        for i in downloads_list:
            line = i.strip()
            if not line:
                continue
            elif line.startswith('#'):
                continue
            elif line.startswith("http://"):
                retlist.append(Fileinfo(line, Rtypes.HTTP))
            else:
                retlist.append(Fileinfo(line, Rtypes.RTMP))

        return retlist

    def set_destdir(self, destdir: str):
        if destdir == '':
            return

        destdir = os.path.expanduser(destdir)
        try:
            os.makedirs(destdir)
            self.destination = destdir
        except OSError:
            if not os.path.isdir(destdir):
                raise

    def spawn(self, file_info: Fileinfo) -> Procinfo:
        remote_file_name = file_info.path
        download_type = file_info.type

        if (download_type is Rtypes.RTMP):
            res_file = self.destination + remove_ext(remote_file_name) + '.flv'
            res_type = Ftypes.FLV
            command = [self.conf.COMMANDS.rtmpdump, "--hashes", "--live",
                       "--rtmp", self.conf.RTMP.replay_rtmp + "/" +
                       remote_file_name, "--pageUrl",
                       self.conf.RTMP.referer, "--swfUrl",
                       self.conf.RTMP.replay_url, "--swfVfy",
                       self.conf.RTMP.player_url, "--flv", res_file]
        elif (download_type is Rtypes.HTTP):
            fname = re.search(r'mp4:([^\/]*)\/', remote_file_name)
            res_file = self.destination + fname.group(1)
            res_type = Ftypes.MP4
            command = [self.conf.COMMANDS.ffmpeg, "-i",
                       remote_file_name, "-c", "copy", res_file]
        else:
            self.out[MsgTypes.errors].add("Unrecognized download type for " +
                                          remote_file_name)
            return None

        if os.path.isfile(res_file):
            self.out[MsgTypes.errors].add("WARNING: skipping download, " +
                                          "file exists: " + res_file)
            self.out[MsgTypes.skipped].add("" + res_file)
            self.finished_ready.append((res_file, res_type))
            return None
        else:
            p = Popen(command, stdout=PIPE, stderr=PIPE)
            self.out[MsgTypes.active].add("" + res_file)
            proc = Proc(p)

        return Procinfo(proc, res_file, res_type)

    def finished_handler(self, procinfo: Procinfo) -> int:
        proc_o = procinfo.proc_o
        filepath = procinfo.path
        filetype = procinfo.type
        proc = proc_o.proc
        retcode = proc.poll()

        (out, err) = proc.communicate()
        if out:
            logit("[download] stdout for " + filepath + ":")
            logit(out.decode('utf-8'))
        if err:
            logit("[download] stderr for " + filepath + ":", logging.error)
            logit(err.decode('utf-8'), logging.error)

        # "Download may be incomplete (downloaded about 99.50%), try resuming"
        if (retcode == 2) and (filetype == Ftypes.FLV):
            for each_line in err.decode('utf-8').splitlines():
                m = re.search(r'\(downloaded about 99\.[0-9]+%\),', each_line)
                if m:
                    retcode = 0
                    break

        if (retcode == 0):
            self.out[MsgTypes.finished].add("" + filepath)
            self.finished_ready.append(Fileinfo(filepath, filetype))
        else:
            try:
                os.rename(filepath, filepath + ".part")
                logit("[rename] " + filepath + ".part", logging.error)
            except FileNotFoundError as e:
                self.out[MsgTypes.errors].add(str(e))
            self.out[MsgTypes.failed].add("" + filepath)
            self.out[MsgTypes.errors].add("Error downloading " + filepath +
                                          ": " + err.decode('utf-8'))

        return retcode


class Decode:
    def __init__(self, conf: Config, to_do: list):
        self.conf = conf
        self.out = {MsgTypes.active: MsgList("Decoding"),
                    MsgTypes.finished: MsgList("Decoded"),
                    MsgTypes.skipped: MsgList("Skipped decoding of"),
                    MsgTypes.failed: MsgList("Failed to decode"),
                    MsgTypes.errors: MsgList()}
        self.destination = ''
        self.finished_ready = []
        self.to_do = to_do

    def set_destdir(self, destdir: str):
        if destdir == '':
            return

        destdir = os.path.expanduser(destdir)
        try:
            os.makedirs(destdir)
        except OSError:
            if not os.path.isdir(destdir):
                raise
        self.destination = destdir

    def spawn(self, file_info: Fileinfo) -> Procinfo:
        local_file_name = file_info.path
        file_type = file_info.type
        res_file = self.destination + remove_ext(file_info.path) + '.mp3'

        if (file_type is not Ftypes.FLV):
            return None
        elif os.path.isfile(res_file):
            self.out[MsgTypes.errors].add("WARNING: skipping decoding, " +
                                          "file exists: " + res_file)
            self.out[MsgTypes.skipped].add("" + res_file)
            return None
        else:
            p = Popen([self.conf.COMMANDS.ffmpeg, "-i",
                      local_file_name, "-vn", "-acodec", "copy", res_file],
                      stdout=PIPE, stderr=PIPE)
            self.out[MsgTypes.active].add("" + res_file)
            proc = Proc(p)

        return Procinfo(proc, res_file, Ftypes.MP3)

    def finished_handler(self, procinfo: Procinfo) -> int:
        proc_o = procinfo.proc_o
        filepath = procinfo.path
        filetype = procinfo.type
        proc = proc_o.proc
        retcode = proc.poll()

        (out, err) = proc.communicate()
        if out:
            logit("[decode] stdout for " + filepath + ":")
            logit(out.decode('utf-8'))
        if err:
            logit("[decode] stderr for " + filepath + ":", logging.error)
            logit(err.decode('utf-8'), logging.error)

        if (retcode == 0):
            self.out[MsgTypes.finished].add("" + filepath)
            self.finished_ready.append(Fileinfo(filepath, filetype))
        else:
            try:
                os.remove(filepath)
                logit("[delete] " + filepath, logging.error)
            except FileNotFoundError as e:
                self.out[MsgTypes.errors].add(str(e))
            self.out[MsgTypes.failed].add("" + filepath)
            self.out[MsgTypes.errors].add("Error decoding " + filepath +
                                          ": " + err.decode('utf-8'))

        return retcode


_LOGFILE = None


def remove_ext(filename: str):
    fname, fext = os.path.splitext(filename)
    return fname if (len(fext) == 4) else fname + fext


def log_init(logfile: str):
    if logfile is None:
        return

    try:
        logging.basicConfig(filename=logfile, level=logging.DEBUG)
        global _LOGFILE
        _LOGFILE = logfile
    except EnvironmentError as e:
        print(str(e), file=sys.stderr)


def logit(message: str, method=logging.info):
    if _LOGFILE is None:
        return

    try:
        for each_line in message.splitlines():
            method("" + each_line)
    except EnvironmentError as e:
        print(str(e), file=sys.stderr)


def get_logfile():
    return _LOGFILE


def get_replay_list(replay_type: int, conf: Config, outfile: str, append=False):
    def _get_session(desc):
        if (conf.AUTH.login == '') or (conf.AUTH.password == ''):
            raise ValueError('Login or password are not configured')

        payload = {
            'login': conf.AUTH.login,
            'password': conf.AUTH.password
        }

        if replay_type == Rtypes.RTMP:
            conf_section = conf.RTMP
        elif replay_type == Rtypes.HTTP:
            conf_section = conf.HTTP
        else:
            raise ValueError("Unrecognized replay type")

        with session() as c:
            c.post(conf_section.login_url, data=payload)
            response = c.get(conf_section.replay_url)
            for each_line in response.text.splitlines():
                m = re.search(conf_section.list_regex, each_line)
                if m:
                    print(m.group(1), file=desc)

    if (outfile == '-'):
        _get_session(sys.stdout)
    else:
        if append is True:
            with open(outfile, 'a') as f:
                _get_session(f)
        else:
            with open(outfile, 'w') as f:
                _get_session(f)


def get_list_from_file(list_file: str):
    try:
        with open(list_file) as f:
            return f.read().splitlines()
    except EnvironmentError as e:
        print(str(e), file=sys.stderr)


if __name__ == "__main__":
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
                        help='destination directory for decoded files',
                        default='')
    parser.add_argument('-m', '--logfile', metavar='FILE',
                        help='log file')
    parser.add_argument('-b', '--brief', help='less verbose output',
                        action='store_true')
    parser.add_argument('-q', '--quiet', help='even less verbose output',
                        action='store_true')
    args = parser.parse_args()

    if not len(sys.argv) > 1:
        parser.print_help()
        sys.exit(1)

    if (args.config_file is not None):
        cflist = (args.config_file)
    else:
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
        if (args.config_file is not None):
            print("Error: cannot open config file '" + args.config_file + "'",
                  file=sys.stderr)
        else:
            print("Error: no config file found.", file=sys.stderr)
        sys.exit(1)

    conf = Config(config_file)

    if (args.get_avail is not None):
        get_replay_list(Rtypes.RTMP, conf, args.get_avail, args.append)
        sys.exit(retval)
    elif (args.get_avail_mobile is not None):
        get_replay_list(Rtypes.HTTP, conf, args.get_avail_mobile, args.append)
        sys.exit(retval)
    elif (args.append is True):
        parser.print_help()
        print("\n-a (--append) allowed only in combination with " +
              "-l (--get-avail) and -k (--get-avail-mobile)", file=sys.stderr)
        sys.exit(1)

    msg = Msgs()
    if (args.brief):
        msg_handler = msg.print_dots
    elif (args.quiet):
        msg_handler = msg.print_dummy
    else:
        msg_handler = msg.print

    schedulers = Schedulers()
    schedulers.on_update_hooks.append(msg.schedulers_update_hook)

    log_init(args.logfile)

    if (args.get_list is not None):
        downloads_list = get_list_from_file(args.get_list)
    elif (args.download_file is not None):
        downloads_list = [args.download_file]

    avail_slots = args.concurrent if args.concurrent > 0 \
        else conf.DEFAULT.concurrency

    to_download = Download.parse_todownload_list(downloads_list)
    downloads = Download(conf, to_download)
    downloads_scheduler = Scheduler(downloads)
    downloads_scheduler.avail_slots = avail_slots
    schedulers.add(downloads_scheduler)

    decodings = Decode(conf, downloads.finished_ready)
    decodings.set_destdir(args.destination)
    decodings_scheduler = Scheduler(decodings)
    decodings_scheduler.avail_slots = avail_slots
    schedulers.add(decodings_scheduler)

    try:
        done = False

        while not done:
            done = True
            for s in schedulers.pipeline:
                t = s()
                if t is False:
                    done = False

            msg_handler()
            time.sleep(1)

        if not args.quiet:
            msg.print_summary()

        if retval == 0:
            for m in msg.get_msglists_with_key(MsgTypes.failed):
                if len(m.msglist) > 0:
                    retval = 1
                    break
        if retval == 0:
            for m in msg.get_msglists_with_key(MsgTypes.skipped):
                if len(m.msglist) > 0:
                    retval = 2
                    break
    except KeyboardInterrupt:
        print(" Interrupting running processes...")
        retval = 1
        for l in schedulers.pipeline:
            for procinfo in l.running_procs:
                proc = procinfo.proc_o.proc
                if proc.poll() is None:
                    proc.kill()
                try:
                    os.rename(procinfo.path, procinfo.path + ".part")
                except FileNotFoundError as e:
                    print(str(e), file=sys.stderr)

    sys.exit(retval)
