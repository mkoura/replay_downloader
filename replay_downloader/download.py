# -*- coding: utf-8 -*-
"""
Download from replay.
"""

import os
import re
import sys

from subprocess import Popen, PIPE

from requests import session
from replay_downloader import config, log, mappings, msgs, record, utils


class Download:
    """Downloads specified files.

    Schedulable object for 'ProcScheduler'.
    """

    def __init__(self, conf: config.Config, to_do: list, destination: str = ''):
        # necassary tools
        self.required_tools = [conf.COMMANDS.rtmpdump, conf.COMMANDS.ffmpeg]

        self.conf = conf
        self.out = {mappings.MsgTypes.active: msgs.MsgList('Downloading'),
                    mappings.MsgTypes.finished: msgs.MsgList('Downloaded'),
                    mappings.MsgTypes.skipped: msgs.MsgList('Skipped download of'),
                    mappings.MsgTypes.failed: msgs.MsgList('Failed to download'),
                    mappings.MsgTypes.errors: msgs.MsgList()}
        msgs.out_add(self.out)
        self._destination = ''
        self.destination = destination
        self.finished_ready = []
        self.to_do = to_do

    @staticmethod
    def parse_todownload_list(downloads_list: list) -> list:
        """Parses the list of files to download and store useful metadata."""
        retlist = []
        for i in downloads_list:
            line = i.strip()
            if not line:
                continue
            elif line.startswith('#'):
                continue
            elif line.startswith('http://'):
                retlist.append(record.FileRecord(mappings.Fileinfo(line, mappings.Rtypes.HTTP)))
            else:
                retlist.append(
                    record.FileRecord(mappings.Fileinfo('rtmp://' + line, mappings.Rtypes.RTMP)))

        return retlist

    @property
    def destination(self):
        return self._destination

    @destination.setter
    def destination(self, destdir: str):
        """Sets directory where the downloaded files will be saved."""
        if not destdir:
            return

        destdir = os.path.expanduser(destdir)
        try:
            os.makedirs(destdir)
            self._destination = destdir
        except OSError:
            if not os.path.isdir(destdir):
                raise

    def spawn(self, file_record: record.FileRecord) -> mappings.Procinfo:
        """Runs command for downloading the file in the background.

        Records corresponding metadata.
        """
        remote_file_name = file_record[-1].path
        download_type = file_record[-1].type

        if download_type is mappings.Rtypes.RTMP:
            # strip 'rtmp://'
            remote_file_name = remote_file_name[7:]
            # add destination, strip extension, append '.flv'
            res_file = os.path.join(self.destination,
                                    utils.remove_ext(remote_file_name) + '.flv')
            res_type = mappings.Ftypes.FLV
            audio_format = mappings.Ftypes.MP3
            command = [self.conf.COMMANDS.rtmpdump, '--hashes', '--live',
                       '--rtmp', self.conf.RTMP.replay_rtmp + '/' +
                       remote_file_name, '--pageUrl',
                       self.conf.RTMP.referer, '--swfUrl',
                       self.conf.RTMP.replay_url, '--swfVfy',
                       self.conf.RTMP.player_url, '--flv', res_file + mappings.PART_EXT]
        elif download_type is mappings.Rtypes.HTTP:
            # extract file name from URI
            fname = re.search(r'mp4:([^\/]*)\/', remote_file_name)
            res_file = os.path.join(self.destination, fname.group(1))
            res_type = mappings.Ftypes.MP4
            audio_format = mappings.Ftypes.AAC
            command = [self.conf.COMMANDS.ffmpeg, '-i',
                       remote_file_name, '-c', 'copy', res_file + mappings.PART_EXT]
        else:
            self.out[mappings.MsgTypes.errors].add(
                'Error: download failed, unsupported download type for {}'
                .format(remote_file_name))
            self.out[mappings.MsgTypes.failed].add(remote_file_name)
            return
        cur_fileinfo = mappings.Fileinfo(
            res_file, res_type, clname=type(self).__name__, audio_f=audio_format)

        if os.path.isfile(res_file):
            self.out[mappings.MsgTypes.errors].add(
                'WARNING: skipping download, file exists: {}'.format(res_file))
            self.out[mappings.MsgTypes.skipped].add(res_file)
            file_record.add(cur_fileinfo)
            self.finished_ready.append(file_record)
            return

        # run the command
        proc = Popen(command, stdout=PIPE, stderr=PIPE)
        # add the file name to 'active' message queue
        self.out[mappings.MsgTypes.active].add(res_file)
        # update file history
        file_record.add(cur_fileinfo)
        return mappings.Procinfo(proc, file_record)

    def finished_handler(self, procinfo: mappings.Procinfo) -> int:
        """Actions performed when download is finished."""
        proc = procinfo.proc
        filepath = procinfo.file_record[-1].path
        filetype = procinfo.file_record[-1].type
        retcode = proc.poll()

        # get stdout and stderr of the command
        out, err = proc.communicate()
        if out:
            log.logit('[download] stdout for {}:'.format(filepath))
            log.logit(out.decode('utf-8'))
        if err:
            log.logit('[download] stderr for {}:'.format(filepath), 'error')
            log.logit(err.decode('utf-8'), 'error')

        # If rtmpdump finishes with following message:
        # "Download may be incomplete (downloaded about 99.50%), try resuming"
        # it means that download was ok even though the return value was non-zero
        if (retcode == 2) and (filetype == mappings.Ftypes.FLV):
            for each_line in err.decode('utf-8').splitlines():
                match = re.search(r'\(downloaded about 99\.[0-9]+%\),', each_line)
                if match:
                    retcode = 0
                    break

        # check if download was successful
        if retcode == 0:
            try:
                # file.part should exist, rename it to strip the '.part'
                os.rename(filepath + mappings.PART_EXT, filepath)
                log.logit('[rename] {0}{1} to {0}'.format(filepath, mappings.PART_EXT))
                self.out[mappings.MsgTypes.finished].add(filepath)
                # file is ready for further processing by next action in 'pipeline'
                self.finished_ready.append(procinfo.file_record)
            except FileNotFoundError as emsg:
                log.logit('[rename] failed: {}'.format(emsg), 'error')
                retcode = 1
        if retcode != 0:
            self.out[mappings.MsgTypes.failed].add(filepath)
            self.out[mappings.MsgTypes.errors].add(
                'Error downloading {}: {}'.format(filepath, err.decode('utf-8')))
            # remove last entry from file_record
            procinfo.file_record.delete()

        return retcode


def get_replay_list(replay_type: int, conf: config.Config, outfile: str, append=False):
    """Gets list of remote files (streams) available for download."""
    def _get_session(desc):
        if not (conf.AUTH.login and conf.AUTH.password):
            raise ValueError('Login or password are not configured')

        payload = {
            'login': conf.AUTH.login,
            'password': conf.AUTH.password
        }

        # get available files (streams) from classic replay...
        if replay_type == mappings.Rtypes.RTMP:
            conf_section = conf.RTMP
        # ...or from mobile replay
        elif replay_type == mappings.Rtypes.HTTP:
            conf_section = conf.HTTP
        else:
            raise ValueError('Unrecognized replay type')

        with session() as ses:
            ses.post(conf_section.login_url, data=payload)
            response = ses.get(conf_section.replay_url)
            for each_line in response.text.splitlines():
                match = re.search(conf_section.list_regex, each_line)
                if match:
                    print(match.group(1), file=desc)

    # output to file or to stdout?
    if outfile == '-':
        _get_session(sys.stdout)
    else:
        with open(outfile, 'a' if append else 'w') as ofl:
            _get_session(ofl)
