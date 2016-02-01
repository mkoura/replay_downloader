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
from requests import session
from subprocess import Popen, PIPE


Fileinfo = collections.namedtuple('Fileinfo', 'path type')
Procinfo = collections.namedtuple('Procinfo', 'proc_o path type')


class Rtypes:
    RTMP = 0
    HTTP = 1


class Ftypes:
    FLV = 0
    MP3 = 1
    AAC = 2
    MP4 = 3


class Config:
    class __Copts:
        pass

    def __init__(self, cfg_path: str):
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
        self.cfg.read(cfg_path)

        self.DEFAULT = self.__Copts()
        self.DEFAULT.concurrency = self.cfg['DEFAULT']['concurrency']
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

        self.getint = self.cfg.getint


class Scheduler:
    def __init__(self, spawn_callback, finish_callback, to_do: list):
        self.avail_slots = 3
        self.to_do = to_do
        self.running_procs = []
        self.spawn_callback = spawn_callback
        self.finish_callback = finish_callback

    def __spawn(self) -> bool:
        while ((self.avail_slots != 0) and (len(self.to_do) != 0)):
            procinfo = self.spawn_callback(self.to_do.pop())
            if procinfo is not None:
                self.running_procs.append(procinfo)
                self.avail_slots -= 1

        return(len(self.to_do) == 0)

    def __check_running_procs(self) -> bool:
        for procinfo in self.running_procs:
            retcode = procinfo.proc_o.proc.poll()
            if retcode is not None:
                self.running_procs.remove(procinfo)
                self.avail_slots += 1
                self.finish_callback(procinfo)

        return(len(self.running_procs) == 0)

    def run(self) -> bool:
        s = self.__spawn()
        c = self.__check_running_procs()
        return(s and c)


class MsgList:
    def __init__(self, text=''):
        self.msglist = []
        self.tstamp = 0
        self.text = text

    def update_tstamp(self):
        self.tstamp = time.time()

    def add(self, message: str):
        self.msglist.append((message, time.time()))

    def erase(self):
        del self.msglist[:]

    def get_new(self) -> list:
        retlist = [msg[0] for msg in self.msglist if msg[1] >= self.tstamp]
        self.update_tstamp()
        return retlist


class Msgs:
    def __init__(self):
        self.outlist = []

    @staticmethod
    def print_dummy():
        pass

    def __get_key(self, key):
        return [d[key] for d in self.outlist if key in d]

    def _print_new(self, key, out=sys.stdout):
        for msglist in self.__get_key(key):
            for msg in msglist.get_new():
                print("" + msglist.text + " " + msg, file=out)

    def print_errors(self):
        self._print_new('errors', sys.stderr)

    def print(self):
        self.print_errors()
        self._print_new('active')

    def print_dots(self):
        def _print(sym, msglist):
            for msg in msglist.get_new():
                print(sym, end="")
                sys.stdout.flush()

        for i in self.__get_key('failed'):
            _print('F', i)

        syms = ['.', '+', '*', '#']
        slen = len(syms)
        num = 0
        for i in self.__get_key('active'):
            _print(syms[num % slen], i)
            num += 1

        for i in self.__get_key('skipped'):
            _print('S', i)

    def print_summary(self):
        def _print(key):
            for li in self.__get_key(key):
                num = len(li.msglist)
                if (num > 0):
                    print("" + li.text + " " + str(num) + " file(s):")
                    for f in li.msglist:
                        print("    " + f[0])

        print("")

        _print('finished')
        _print('failed')
        _print('skipped')


class Proc:
    def __init__(self, proc):
        self.proc = proc


class Download:
    def __init__(self, conf: Config):
        self.conf = conf
        self.out = {'active': MsgList("Downloading"),
                    'finished': MsgList("Downloaded"),
                    'skipped': MsgList("Skipped download of"),
                    'failed': MsgList("Failed to download"),
                    'errors': MsgList()}
        self.destination = ''
        self.finished_ready = []

    @staticmethod
    def parse_downloads_list(downloads_list: list) -> list:
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

    @staticmethod
    def get_list_from_file(list_file: str):
        try:
            with open(list_file) as f:
                return f.read().splitlines()
        except EnvironmentError as e:
            print(str(e), file=sys.stderr)

    def spawn(self, file_info: Fileinfo) -> Procinfo:
        remote_file_name = file_info.path
        download_type = file_info.type

        if (download_type is Rtypes.RTMP):
            res_file = self.destination + remote_file_name + '.flv'
            res_type = Ftypes.FLV
            command = [self.conf.COMMANDS.rtmpdump, "--hashes", "--live", "--rtmp",
                       self.conf.RTMP.replay_rtmp + "/" +
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
            self.out['errors'].add("Unrecognized download type for " + remote_file_name)
            return None

        if os.path.isfile(res_file):
            self.out['errors'].add("WARNING: skipping download, file exists: " + res_file)
            self.out['skipped'].add("" + res_file)
            self.finished_ready.append((res_file, res_type))
            return None
        else:
            p = Popen(command, stdout=PIPE, stderr=PIPE)
            self.out['active'].add("" + res_file)
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
            self.out['finished'].add("" + filepath)
            self.finished_ready.append(Fileinfo(filepath, filetype))
        else:
            try:
                os.rename(filepath, filepath + ".part")
                logit("[rename] " + filepath + ".part", logging.error)
            except FileNotFoundError as e:
                self.out['errors'].add(str(e))
            self.out['failed'].add("" + filepath)
            self.out['errors'].add("Error downloading " + filepath + ": " + err.decode('utf-8'))

        return retcode


class Decode:
    def __init__(self, conf: Config):
        self.conf = conf
        self.out = {'active': MsgList("Decoding"),
                    'finished': MsgList("Decoded"),
                    'skipped': MsgList("Skipped decoding of"),
                    'failed': MsgList("Failed to decode"),
                    'errors': MsgList()}
        self.destination = ''
        self.finished_ready = []

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
        res_file = self.destination + os.path.splitext(local_file_name)[0]

        if (file_type is not Ftypes.FLV):
            return None
        elif os.path.isfile(res_file):
            self.out['errors'].add("WARNING: skipping decoding, file exists: " + res_file)
            self.out['skipped'].add("" + res_file)
            return None
        else:
            p = Popen([self.conf.COMMANDS.ffmpeg, "-i",
                      local_file_name, "-vn", "-acodec", "copy", res_file],
                      stdout=PIPE, stderr=PIPE)
            self.out['active'].add("" + res_file)
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
            self.out['finished'].add("" + filepath)
            self.finished_ready.append(Fileinfo(filepath, filetype))
        else:
            try:
                os.remove(filepath)
                logit("[delete] " + filepath, logging.error)
            except FileNotFoundError as e:
                self.out['errors'].add(str(e))
            self.out['failed'].add("" + filepath)
            self.out['errors'].add("Error decoding " + filepath + ": " + err.decode('utf-8'))

        return retcode


__LOGFILE = None


def log_init(logfile: str):
    if logfile is None:
        return

    try:
        logging.basicConfig(filename=logfile, level=logging.DEBUG)
        global __LOGFILE
        __LOGFILE = logfile
    except EnvironmentError as e:
        print(str(e), file=sys.stderr)


def logit(message: str, method=logging.info):
    if __LOGFILE is None:
        return

    try:
        for each_line in message.splitlines():
            method("" + each_line)
    except EnvironmentError as e:
        print(str(e), file=sys.stderr)


def get_logfile():
    return __LOGFILE


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
                        help='destination directory for decoded files', default='')
    parser.add_argument('-m', '--logfile', metavar='FILE',
                        help='log file')
    parser.add_argument('-b', '--brief', help='less verbose output', action='store_true')
    parser.add_argument('-q', '--quiet', help='even less verbose output', action='store_true')
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
            print("Error: cannot open config file '" + args.config_file + "'", file=sys.stderr)
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
        print("\n-a (--append) allowed only in combination with -l (--get-avail) " +
              "and -k (--get-avail-mobile)", file=sys.stderr)
        sys.exit(1)

    msg = Msgs()
    log_init(args.logfile)

    if (args.get_list is not None):
        downloads_list = Download.get_list_from_file(args.get_list)
    elif (args.download_file is not None):
        downloads_list = [args.download_file]

    downloads = Download(conf)
    to_download = Download.parse_downloads_list(downloads_list)
    downloads_scheduler = Scheduler(downloads.spawn, downloads.finished_handler,
                                    to_download)
    downloads_scheduler.avail_slots = args.concurrent if args.concurrent > 0 \
        else conf.getint('DEFAULT', 'concurrency')
    msg.outlist.append(downloads.out)

    decodings = Decode(conf)
    decodings.set_destdir(args.destination)
    decodings_scheduler = Scheduler(decodings.spawn,
                                    decodings.finished_handler,
                                    downloads.finished_ready)
    decodings_scheduler.avail_slots = args.concurrent if args.concurrent > 0 \
        else conf.getint('DEFAULT', 'concurrency')
    msg.outlist.append(decodings.out)

    if (args.brief):
        msg_handler = msg.print_dots
    elif (args.quiet):
        msg_handler = msg.print_dummy
    else:
        msg_handler = msg.print

    try:
        downloads_done = decodings_done = False

        while not (downloads_done and decodings_done):
            downloads_done = downloads_scheduler.run()
            decodings_done = decodings_scheduler.run()

            msg_handler()
            time.sleep(1)

        if not args.quiet:
            msg.print_summary()

        if ((len(downloads.out['failed'].msglist) > 0)
                or (len(decodings.out['failed'].msglist) > 0)):
            retval = 1
        elif ((len(downloads.out['skipped'].msglist) > 0)
                or (len(decodings.out['skipped'].msglist) > 0)):
            retval = 2
    except KeyboardInterrupt:
        print(" Interrupting running processes...")
        retval = 1
        for l in (downloads_scheduler.running_procs, decodings_scheduler.running_procs):
            for procinfo in l:
                proc = procinfo.proc_o.proc
                if proc.poll() is None:
                    proc.kill()
                try:
                    os.rename(procinfo.path, procinfo.path + ".part")
                except FileNotFoundError as e:
                    print(str(e), file=sys.stderr)

    sys.exit(retval)
