#!/usr/bin/env python3
# encoding: utf-8

import unittest
import os
import time
from replay_downloader import (
    Fileinfo,
    Procinfo,
    Rtypes,
    Ftypes,
    MsgTypes,
    Config,
    # Scheduler,
    # Schedulers,
    # MsgList,
    # Msgs,
    # Proc,
    FileRecord,
    Download,
    Decode,
    # remove_ext,
    # log_init,
    # logit,
    # get_logfile,
    # get_replay_list,
    get_list_from_file,
)


class TestDownloads(unittest.TestCase):
    def test_parse_todownload_list(self):
        l = [' # foo', 'bar', 'http://baz', ' foo1', 'http://bar1 ']
        down_list = Download.parse_todownload_list(l)
        self.assertEqual(down_list[0](), Fileinfo(path='bar', type=Rtypes.RTMP))
        self.assertEqual(down_list[1](), Fileinfo(path='http://baz', type=Rtypes.HTTP))
        self.assertEqual(down_list[2](), Fileinfo(path='foo1', type=Rtypes.RTMP))
        self.assertEqual(down_list[3](), Fileinfo(path='http://bar1', type=Rtypes.HTTP))

    def test_set_destdir(self):
        conf = Config()
        downloads = Download(conf, [])
        destdir = 'destdir'

        downloads.set_destdir(destdir)
        self.assertEqual(downloads.destination, destdir)
        self.assertTrue(os.path.isdir(destdir))
        try:
            os.rmdir(destdir)
        except OSError:
            if os.path.isdir(destdir):
                raise

    def test_get_list_from_file(self):
        os.chdir(os.path.dirname(__file__))
        self.assertEqual(get_list_from_file('test_replay_list'),
                         ['20151205_TS_ChNN_Atiyoga_Teachings_Tashigar_South.mp3',
                          '20151205_TS_ChNN_Atiyoga_Teachings_Tashigar_South_es.mp3',
                          '20151206_TS_ChNN_Atiyoga_Teachings_Tashigar_South.mp3',
                          '20151206_TS_ChNN_Atiyoga_Teachings_Tashigar_South_es.mp3',
                          '',
                          '# TEST',
                          '20151207_TS_ChNN_Atiyoga_Teachings_Tashigar_South.mp3',
                          '20151207_TS_ChNN_Atiyoga_Teachings_Tashigar_South_es_parcial.mp3',
                          '20151208_TS_ChNN_Atiyoga_Teachings_Tashigar_South.mp3'])

    def test_spawn_http(self):
        conf = Config()
        conf.COMMANDS.rtmpdump = '/bin/true'
        downloads = Download(conf, [])

        file_record = FileRecord(Fileinfo('replay/mp4:20150816.mp4/playlist.m3u8',
                                          Rtypes.HTTP))
        proc = downloads.spawn(file_record)
        self.assertEqual(file_record(), Fileinfo('20150816.mp4',
                                                 Ftypes.MP4,
                                                 'Download'))
        self.assertEqual(proc, Procinfo(proc.proc_o, file_record))

    def test_spawn_unknown_type(self):
        conf = Config()
        conf.COMMANDS.rtmpdump = '/bin/true'
        downloads = Download(conf, [])

        file_record = FileRecord(Fileinfo('foo', 20))
        ret = downloads.spawn(file_record)
        self.assertEqual(ret, None)

    def test_spawn_file_exists(self):
        conf = Config()
        conf.COMMANDS.rtmpdump = '/bin/true'
        downloads = Download(conf, [])

        os.chdir(os.path.dirname(__file__))
        file_record = FileRecord(Fileinfo('existing_file', Rtypes.RTMP))
        ret = downloads.spawn(file_record)
        self.assertEqual(ret, None)

    def test_finished_rtmp(self):
        conf = Config()
        conf.COMMANDS.rtmpdump = '/bin/true'
        downloads = Download(conf, [])

        file_record = FileRecord(Fileinfo('foo', Rtypes.RTMP))
        proc = downloads.spawn(file_record)
        self.assertEqual(proc, Procinfo(proc.proc_o, file_record))
        self.assertEqual(file_record._rec, [Fileinfo('foo', Rtypes.RTMP),
                                            Fileinfo('foo.flv', Ftypes.FLV, 'Download')])
        while (proc.proc_o.proc.poll() is None):
            time.sleep(0.05)

        ret = downloads.finished_handler(proc)
        self.assertEqual(ret, 0)
        self.assertEqual(downloads.out[MsgTypes.finished].msglist[0][0], 'foo.flv')
        self.assertEqual(downloads.finished_ready[0], file_record)


class TestDecodings(unittest.TestCase):
    def test_set_destdir(self):
        conf = Config()
        decodings = Decode(conf, [])
        destdir = 'destdir'

        decodings.set_destdir(destdir)
        self.assertEqual(decodings.destination, destdir)
        self.assertTrue(os.path.isdir(destdir))
        try:
            os.rmdir(destdir)
        except OSError:
            if os.path.isdir(destdir):
                raise

    def test_spawn(self):
        conf = Config()
        conf.COMMANDS.ffmpeg = '/bin/true'
        decodings = Decode(conf, [])

        file_record = FileRecord(Fileinfo('20150816.flv',
                                          Ftypes.FLV))
        proc = decodings.spawn(file_record)
        self.assertEqual(file_record(), Fileinfo('20150816.mp3',
                                                 Ftypes.MP3,
                                                 'Decode'))
        self.assertEqual(proc, Procinfo(proc.proc_o, file_record))

    def test_spawn_unknown_type(self):
        conf = Config()
        conf.COMMANDS.ffmpeg = '/bin/true'
        decodings = Decode(conf, [])

        file_record = FileRecord(Fileinfo('20150816.mp3', 'mp3'))
        ret = decodings.spawn(file_record)
        self.assertEqual(ret, None)

    def test_spawn_file_exists(self):
        conf = Config()
        conf.COMMANDS.ffmpeg = '/bin/true'
        decodings = Decode(conf, [])

        os.chdir(os.path.dirname(__file__))
        file_record = FileRecord(Fileinfo('existing_file.flv', Ftypes.FLV))
        ret = decodings.spawn(file_record)
        self.assertEqual(ret, None)

    def test_finished_mp3(self):
        conf = Config()
        conf.COMMANDS.ffmpeg = '/bin/true'
        decodings = Decode(conf, [])

        file_record = FileRecord(Fileinfo('20150816.flv', Ftypes.FLV))
        proc = decodings.spawn(file_record)
        self.assertEqual(proc, Procinfo(proc.proc_o, file_record))
        self.assertEqual(file_record._rec, [Fileinfo('20150816.flv', Ftypes.FLV),
                                            Fileinfo('20150816.mp3', Ftypes.MP3, 'Decode')])
        while (proc.proc_o.proc.poll() is None):
            time.sleep(0.05)

        ret = decodings.finished_handler(proc)
        self.assertEqual(ret, 0)
        self.assertEqual(decodings.out[MsgTypes.finished].msglist[0][0], '20150816.mp3')
        self.assertEqual(decodings.finished_ready[0], file_record)
