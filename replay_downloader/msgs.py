# -*- coding: utf-8 -*-
"""
"""

import sys
import time

from replay_downloader import mappings


# dictionary of message queues (active, skipped, etc.)
_OUT = {}


class MsgList:
    """Queue of messages with timestamp."""
    def __init__(self, text: str = ''):
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
        """New messages iterator."""
        # get messages that were not displayed (requested) yet
        for msg in self.msglist:
            if msg[1] >= self.tstamp:
                yield msg[0]
        self.update_tstamp()


class Msgs:
    """Prints available messages."""
    # list of symbols used for displaying progress
    syms = ['.', '+', '*', '#']
    slen = len(syms)

    @staticmethod
    def print_dummy():
        pass

    @staticmethod
    def get_msglists_with_key(key: str):
        """Generator of message queues identified by 'key'."""
        return (msglist for msglist in _OUT[key]) if key in _OUT else iter(())

    def _print_new(self, key: str, out=sys.stdout):
        for msglist in self.get_msglists_with_key(key):
            for msg in msglist.get_new():
                print('{} {}'.format(msglist.text, msg).strip(), file=out)

    def print_errors(self):
        """Prints new error messages."""
        self._print_new(mappings.MsgTypes.errors, sys.stderr)

    def print(self):
        """Prints new error messages and messages indicating progress."""
        self.print_errors()
        self._print_new(mappings.MsgTypes.active)

    def print_dots(self):
        """Displays progress using symbols instead of text messages."""
        def _print(sym, msglist):
            for _ in msglist.get_new():
                print(sym, end='')
                sys.stdout.flush()

        for i in self.get_msglists_with_key(mappings.MsgTypes.failed):
            _print('F', i)

        for num, mem in enumerate(self.get_msglists_with_key(mappings.MsgTypes.active)):
            _print(self.syms[num % self.slen], mem)

        for i in self.get_msglists_with_key(mappings.MsgTypes.skipped):
            _print('S', i)

    def print_summary(self):
        """Prints summary of the final outcome."""
        def _print(key):
            for mem in self.get_msglists_with_key(key):
                num = len(mem)
                if num > 0:
                    print('{} {} file(s):'.format(mem.text, num))
                    for fil in mem:
                        print('  {}'.format(fil[0]))

        print('')

        _print(mappings.MsgTypes.finished)
        _print(mappings.MsgTypes.failed)
        _print(mappings.MsgTypes.skipped)


def out_add(out: dict):
    """Adds message queue to dictionary."""
    for key in out:
        # add message queue to dictionary;
        # create the key if it doesn't exist yet
        _OUT.setdefault(key, []).append(out[key])


def setup_messages(args):
    """Instantiates "messages" and choose how its output will be presented."""
    messages = Msgs()
    if args.brief:
        msg_handler = messages.print_dots
    elif args.quiet:
        msg_handler = messages.print_dummy
    else:
        msg_handler = messages.print
    return messages, msg_handler
