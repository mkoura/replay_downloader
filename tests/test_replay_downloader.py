#!/usr/bin/env python3
# encoding: utf-8

import unittest
import os
import time
import replay_downloader as rd


class TestDownloads(unittest.TestCase):
    def test_parse_todownload_list(self):
        l = [' # foo', 'bar', 'http://baz', ' foo1', 'http://bar1 ']
        down_list = rd.Download.parse_todownload_list(l)
        self.assertEqual(down_list[0](), rd.Fileinfo(path='bar', type=rd.Rtypes.RTMP))
        self.assertEqual(down_list[1](), rd.Fileinfo(path='http://baz', type=rd.Rtypes.HTTP))
        self.assertEqual(down_list[2](), rd.Fileinfo(path='foo1', type=rd.Rtypes.RTMP))
        self.assertEqual(down_list[3](), rd.Fileinfo(path='http://bar1', type=rd.Rtypes.HTTP))

    def test_set_destdir(self):
        conf = rd.Config()
        downloads = rd.Download(conf, [])
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
        self.assertEqual(rd.get_list_from_file('test_replay_list'),
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
        conf = rd.Config()
        conf.COMMANDS.rtmpdump = '/bin/true'
        downloads = rd.Download(conf, [])

        file_record = rd.FileRecord(rd.Fileinfo('replay/mp4:20150816.mp4/playlist.m3u8',
                                                rd.Rtypes.HTTP))
        proc = downloads.spawn(file_record)
        self.assertEqual(file_record(), rd.Fileinfo('20150816.mp4',
                                                    rd.Ftypes.MP4,
                                                    'Download'))
        self.assertEqual(proc, rd.Procinfo(proc.proc_o, file_record))

    def test_spawn_unknown_type(self):
        conf = rd.Config()
        conf.COMMANDS.rtmpdump = '/bin/true'
        downloads = rd.Download(conf, [])

        file_record = rd.FileRecord(rd.Fileinfo('foo', 20))
        ret = downloads.spawn(file_record)
        self.assertEqual(ret, None)

    def test_spawn_file_exists(self):
        conf = rd.Config()
        conf.COMMANDS.rtmpdump = '/bin/true'
        downloads = rd.Download(conf, [])

        os.chdir(os.path.dirname(__file__))
        file_record = rd.FileRecord(rd.Fileinfo('existing_file', rd.Rtypes.RTMP))
        ret = downloads.spawn(file_record)
        self.assertEqual(ret, None)

    def test_finished_rtmp(self):
        conf = rd.Config()
        conf.COMMANDS.rtmpdump = '/bin/true'
        downloads = rd.Download(conf, [])

        file_record = rd.FileRecord(rd.Fileinfo('foo', rd.Rtypes.RTMP))
        proc = downloads.spawn(file_record)
        self.assertEqual(proc, rd.Procinfo(proc.proc_o, file_record))
        self.assertEqual(file_record._rec, [rd.Fileinfo('foo', rd.Rtypes.RTMP),
                                            rd.Fileinfo('foo.flv', rd.Ftypes.FLV, 'Download')])
        while (proc.proc_o.proc.poll() is None):
            time.sleep(0.05)

        ret = downloads.finished_handler(proc)
        self.assertEqual(ret, 0)
        self.assertEqual(downloads.out[rd.MsgTypes.finished].msglist[0][0], 'foo.flv')
        self.assertEqual(downloads.finished_ready[0], file_record)


class TestDecodings(unittest.TestCase):
    def test_set_destdir(self):
        conf = rd.Config()
        decodings = rd.Decode(conf, [])
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
        conf = rd.Config()
        conf.COMMANDS.ffmpeg = '/bin/true'
        decodings = rd.Decode(conf, [])

        file_record = rd.FileRecord(rd.Fileinfo('20150816.flv',
                                                rd.Ftypes.FLV))
        proc = decodings.spawn(file_record)
        self.assertEqual(file_record(), rd.Fileinfo('20150816.mp3',
                                                    rd.Ftypes.MP3,
                                                    'Decode'))
        self.assertEqual(proc, rd.Procinfo(proc.proc_o, file_record))

    def test_spawn_unknown_type(self):
        conf = rd.Config()
        conf.COMMANDS.ffmpeg = '/bin/true'
        decodings = rd.Decode(conf, [])

        file_record = rd.FileRecord(rd.Fileinfo('20150816.mp3', 'mp3'))
        ret = decodings.spawn(file_record)
        self.assertEqual(ret, None)

    def test_spawn_file_exists(self):
        conf = rd.Config()
        conf.COMMANDS.ffmpeg = '/bin/true'
        decodings = rd.Decode(conf, [])

        os.chdir(os.path.dirname(__file__))
        file_record = rd.FileRecord(rd.Fileinfo('existing_file.flv', rd.Ftypes.FLV))
        ret = decodings.spawn(file_record)
        self.assertEqual(ret, None)

    def test_finished_mp3(self):
        conf = rd.Config()
        conf.COMMANDS.ffmpeg = '/bin/true'
        decodings = rd.Decode(conf, [])

        file_record = rd.FileRecord(rd.Fileinfo('20150816.flv', rd.Ftypes.FLV))
        proc = decodings.spawn(file_record)
        self.assertEqual(proc, rd.Procinfo(proc.proc_o, file_record))
        self.assertEqual(file_record._rec, [rd.Fileinfo('20150816.flv', rd.Ftypes.FLV),
                                            rd.Fileinfo('20150816.mp3', rd.Ftypes.MP3, 'Decode')])
        while (proc.proc_o.proc.poll() is None):
            time.sleep(0.05)

        ret = decodings.finished_handler(proc)
        self.assertEqual(ret, 0)
        self.assertEqual(decodings.out[rd.MsgTypes.finished].msglist[0][0], '20150816.mp3')
        self.assertEqual(decodings.finished_ready[0], file_record)
