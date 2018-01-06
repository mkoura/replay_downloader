# -*- coding: utf-8 -*-
"""
Cleanup.
"""

import os

from replay_downloader import log, mappings, msgs


class Cleanup:
    """ Deletes all intermediate files. Callable object for work pipeline."""

    def __init__(self, to_do: list):
        self.out = {mappings.MsgTypes.finished: msgs.MsgList('Deleted')}
        msgs.out_add(self.out)
        self.finished_ready = []
        self.to_do = to_do

    def __call__(self) -> bool:
        """Goes through every file record and delete all existing files except the last one."""
        length = len(self.to_do)
        for _ in range(length):
            file_record = self.to_do.pop()
            for rec in file_record[:-1]:
                try:
                    os.remove(rec.path)
                    log.logit('[cleanup] {}'.format(rec.path))
                    self.out[mappings.MsgTypes.finished].add(rec.path)
                    os.remove(rec.path + mappings.PART_EXT)
                    log.logit('[cleanup] {}'.format(rec.path + mappings.PART_EXT))
                    self.out[mappings.MsgTypes.finished].add(rec.path + mappings.PART_EXT)
                except FileNotFoundError:
                    pass
            # pass for further processing
            self.finished_ready.append(file_record)
        return True
