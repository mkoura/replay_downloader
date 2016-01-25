import unittest
import os
import replay_downloader as rd


class TestDownloads(unittest.TestCase):
    def test_parse_downloads_list(self):
        l = [' # foo', 'bar', 'http://baz', ' foo1', 'http://bar1 ']
        self.assertEqual(rd.Downloads.parse_downloads_list(l),
                         [rd.Fileinfo(path='bar', type=0),
                          rd.Fileinfo(path='http://baz', type=1),
                          rd.Fileinfo(path='foo1', type=0),
                          rd.Fileinfo(path='http://bar1', type=1)])

    def test_set_destdir(self):
        msg = rd.Msgs()
        os.chdir(os.path.dirname(__file__))
        conf = rd.Config('test.ini')
        downloads = rd.Downloads(msg, conf)
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
        self.assertEqual(rd.Downloads.get_list_from_file('test_replay_list'),
                         ['20151205_TS_ChNN_Atiyoga_Teachings_Tashigar_South.mp3',
                          '20151205_TS_ChNN_Atiyoga_Teachings_Tashigar_South_es.mp3',
                          '20151206_TS_ChNN_Atiyoga_Teachings_Tashigar_South.mp3',
                          '20151206_TS_ChNN_Atiyoga_Teachings_Tashigar_South_es.mp3',
                          '',
                          '# TEST',
                          '20151207_TS_ChNN_Atiyoga_Teachings_Tashigar_South.mp3',
                          '20151207_TS_ChNN_Atiyoga_Teachings_Tashigar_South_es_parcial.mp3',
                          '20151208_TS_ChNN_Atiyoga_Teachings_Tashigar_South.mp3'])
