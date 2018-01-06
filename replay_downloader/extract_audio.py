# -*- coding: utf-8 -*-
"""
Extract audio from downloaded files.
"""

import os

from subprocess import Popen, PIPE

from replay_downloader import config, log, mappings, msgs, record, utils


class ExtractAudio:
    """Extracts audio from specified files.

    Schedulable object for 'ProcScheduler'.
    """

    def __init__(self, conf: config.Config, to_do: list, destination: str = ''):
        # necassary tools
        self.required_tools = [conf.COMMANDS.ffmpeg]

        self.conf = conf
        self.out = {mappings.MsgTypes.active: msgs.MsgList('Extracting audio'),
                    mappings.MsgTypes.finished: msgs.MsgList('Audio extracting resulted in'),
                    mappings.MsgTypes.skipped: msgs.MsgList('Skipped extracting audio of'),
                    mappings.MsgTypes.failed: msgs.MsgList('Failed to extract audio'),
                    mappings.MsgTypes.errors: msgs.MsgList()}
        msgs.out_add(self.out)
        self._destination = ''
        self.destination = destination
        self.finished_ready = []
        self.to_do = to_do

    @property
    def destination(self):
        return self._destination

    @destination.setter
    def destination(self, destdir: str):
        """Sets directory where the extracted audio files will be saved."""
        if not destdir:
            return

        destdir = os.path.expanduser(destdir)
        try:
            os.makedirs(destdir)
        except OSError:
            if not os.path.isdir(destdir):
                raise
        self._destination = destdir

    def spawn(self, file_record: record.FileRecord) -> mappings.Procinfo:
        """Runs command for extracting the audio in the background.

        Record corresponding metadata.
        """
        local_file_name = file_record[-1].path
        file_type = file_record[-1].type
        audio_format = file_record[-1].audio_f
        if not audio_format:
            self.out[mappings.MsgTypes.errors].add(
                'Error: failed to extract, audio format info not passed for {}'
                .format(local_file_name))
            self.out[mappings.MsgTypes.failed].add(local_file_name)
            return

        if file_type == audio_format:
            # nothing to do, passing for further processing
            # by next action in 'pipeline'
            self.finished_ready.append(file_record)
            return

        fname = '{}.{}'.format(utils.remove_ext(local_file_name),
                               mappings.file_ext_d[audio_format.name])
        res_file = os.path.join(self._destination, fname)
        cur_fileinfo = mappings.Fileinfo(
            res_file, audio_format, clname=type(self).__name__, audio_f=audio_format)

        if os.path.isfile(res_file):
            self.out[mappings.MsgTypes.errors].add(
                'WARNING: skipping extracting, file exists: {}'.format(res_file))
            self.out[mappings.MsgTypes.skipped].add(res_file)
            file_record.add(cur_fileinfo)
            self.finished_ready.append(file_record)
            return

        # run the command
        proc = Popen([self.conf.COMMANDS.ffmpeg, '-i',
                      local_file_name, '-vn', '-acodec', 'copy', res_file],
                     stdout=PIPE, stderr=PIPE)
        # add the file name to 'active' message queue
        self.out[mappings.MsgTypes.active].add(res_file)
        # update file history
        file_record.add(cur_fileinfo)
        return mappings.Procinfo(proc, file_record)

    def finished_handler(self, procinfo: mappings.Procinfo) -> int:
        """Actions performed when extracting is finished."""
        proc = procinfo.proc
        filepath = procinfo.file_record[-1].path
        retcode = proc.poll()

        # get stdout and stderr of the command
        (out, err) = proc.communicate()
        if out:
            log.logit('[extracting] stdout for {}:'.format(filepath))
            log.logit(out.decode('utf-8'))
        if err:
            log.logit('[extracting] stderr for {}'.format(filepath), 'error')
            log.logit(err.decode('utf-8'), 'error')

        # check if extracting was successful
        if retcode == 0:
            self.out[mappings.MsgTypes.finished].add(filepath)
            # file is ready for further processing by next action in 'pipeline'
            self.finished_ready.append(procinfo.file_record)
        else:
            try:
                os.remove(filepath)
                log.logit('[delete] {}'.format(filepath), 'error')
            except FileNotFoundError as emsg:
                self.out[mappings.MsgTypes.errors].add(str(emsg))
            self.out[mappings.MsgTypes.failed].add(filepath)
            self.out[mappings.MsgTypes.errors].add(
                'Error extracting {}: {}'.format(filepath, err.decode('utf-8')))
            # remove last entry from file_record
            procinfo.file_record.delete()

        return retcode
