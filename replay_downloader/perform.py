# -*- coding: utf-8 -*-
"""
Handling processes execution.
"""

import signal
import sys
import time
import traceback
import os

from subprocess import Popen

from replay_downloader import mappings


class CleanExit:
    """Cleanup on exit context manager."""

    def __init__(self, pipeline):
        self.pipeline = pipeline

    def __enter__(self):
        signal.signal(signal.SIGTERM, lambda *args: sys.exit(mappings.ExitCodes.INTERRUPTED))

    def __exit__(self, exc_type, value, trace):
        try:
            for task in self.pipeline:
                # kill all processes running in the background
                if not hasattr(task, 'running_procs'):
                    continue
                for proc_info in task.running_procs:
                    proc_o = proc_info.proc
                    if proc_o.poll() is None:
                        proc_o.kill()
        # pylint: disable=broad-except
        except Exception:
            traceback.print_exc()

        if exc_type is KeyboardInterrupt:
            sys.exit(mappings.ExitCodes.INTERRUPTED)

        return exc_type is None


class ProcScheduler:
    """Runs processes in parallel via schedulable object.

    Callable object for work pipeline.
    """
    def __init__(self, schedulable_obj, avail_slots=3):
        """The schedulable_obj has 'spawn' and 'finished_handler' methods and 'to_do' stack."""
        self.avail_slots = avail_slots
        self.running_procs = []
        self.obj = schedulable_obj
        self.to_do = self.obj.to_do
        self.spawn_callback = self.obj.spawn
        self.finish_callback = self.obj.finished_handler

    def _spawn(self) -> bool:
        """Runs the 'spawn' method of the schedulable_obj.

        Runs it for every item in the 'to_do' stack.
        Runs up-to 'avail_slots' processes in parallel.
        """
        len_todo = len(self.to_do)
        while (self.avail_slots > 0) and (len_todo > 0):
            procinfo = self.spawn_callback(self.to_do.pop())
            len_todo -= 1
            if procinfo is not None:
                self.running_procs.append(procinfo)
                self.avail_slots -= 1

        # return True if there is nothing left to do
        return len_todo == 0

    def _check_running_procs(self) -> bool:
        """Checks all running processes.

        Calls the 'finished_handler' method of the schedulable_obj
        on those that are finished.
        """
        for procinfo in self.running_procs:
            retcode = procinfo.proc.poll()
            if retcode is not None:
                self.running_procs.remove(procinfo)
                self.avail_slots += 1
                self.finish_callback(procinfo)

        # return True if all running processes are finished
        return len(self.running_procs) == 0

    def __call__(self) -> bool:
        """Returns True if there's nothing to do at the moment."""
        return all((self._spawn(), self._check_running_procs()))


class Work():
    """Maintains list of scheduled actions."""
    def __init__(self):
        self.pipeline = []

    def __str__(self):
        return str(self.pipeline)

    def __iter__(self):
        return iter(self.pipeline)

    def add(self, action):
        """Adds work (callable object) to pipeline."""
        self.pipeline.append(action)


def do_the_work(work, msg_handler):
    """The main thing. Loop until all work is done."""
    with CleanExit(work):
        # loop until there's no work left to do
        done = False
        while not done:
            done = True
            for task in work:
                if not task():
                    done = False

            # print messages produced during this iterration
            msg_handler()
            time.sleep(0.5)


def check_required_tools(work):
    """Checks if it's possible to run all required tools."""
    all_required_tools = set()
    for task in work:
        if hasattr(task, 'required_tools'):
            all_required_tools.update(task.required_tools)
        elif hasattr(task, 'obj') and hasattr(task.obj, 'required_tools'):
            all_required_tools.update(task.obj.required_tools)

    all_available = True
    for tool in all_required_tools:
        try:
            with open(os.devnull, 'w') as devnull:
                Popen([tool], stdout=devnull, stderr=devnull)
        except OSError as emsg:
            print("Cannot {} the '{}' command".format(
                'find' if emsg.errno == os.errno.ENOENT else 'run', tool), file=sys.stderr)
            all_available = False

    if not all_available:
        sys.exit(mappings.ExitCodes.CONFIG)
