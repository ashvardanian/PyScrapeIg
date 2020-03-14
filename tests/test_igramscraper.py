import unittest
from unittest.mock import patch
from test_data import username, password, user_agent
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
   
from ig.insta import Instagram
from ig.model import Media

class TestIgramscraper(unittest.TestCase):

    @classmethod
    def setUpClass(self):

        cwd = os.getcwd()
        session_folder = cwd + os.path.sep + 'sessions' + os.path.sep
        if username == None or password == None:
            self.instagram = Instagram()
        else:
            self.instagram = Instagram()
            self.instagram.with_credentials(username, password, session_folder)
            self.instagram.login()
        
        if user_agent != None:
            #TODO set user agent
            pass

    @classmethod
    def tearDownClass(self):
        pass

    def test_get_account_by_username(self):
        account = self.instagram.get_account('kevin')
        self.assertEqual('kevin', account.username)
        self.assertEqual('3', account.identifier)
    
    def test_get_account_by_id(self):
        account = self.instagram.get_account_by_id(3)
        self.assertEqual('kevin', account.username)
        self.assertEqual('3', account.identifier)
    
    def test_get_medias(self):
        medias = self.instagram.get_medias('kevin', 80)
        self.assertEqual(80, len(medias))

    def test_get_hundred_medias(self):
        medias = self.instagram.get_medias('kevin', 100)
        self.assertEqual(100, len(medias))

    def test_get_medias_by_tag(self):
        medias = self.instagram.get_medias_by_tag('youneverknow', 20)
        self.assertEqual(20, len(medias))

    def test_get_medias_by_code(self):
        media = self.instagram.get_medias_by_code('BHaRdodBouH')
        self.assertEqual('kevin', media.owner.username)

    def test_get_media_by_url(self):
        media = self.instagram.get_media_by_url('https://www.instagram.com/p/BHaRdodBouH')
        self.assertEqual('kevin', media.owner.username)

    def test_get_account_by_id_with_invalid_numeric_id(self):
        # sys.maxsize is far larger than the greatest id so far and thus does not represent a valid account.
        try:
            self.instagram.get_account_by_id(sys.maxsize)
        except Exception as e:
            self.assertEqual(str(e), 'Failed to fetch account with given id, Code:404')

    def test_get_location_top_medias_by_id(self):
        medias = self.instagram.get_current_top_medias_by_tag_name(1)
        self.assertEqual(9, len(medias))

    def test_get_location_medias_by_id(self):
        medias = self.instagram.get_medias_by_location_id(1, 56)
        self.assertEqual(56, len(medias))

    def test_get_location_by_id(self):
        location = self.instagram.get_location_by_id(1)
        self.assertEqual('Dog Patch Labs', location.name)

    def test_get_id_from_code(self):
        code = Media.get_code_from_id('1270593720437182847')
        self.assertEqual('BGiDkHAgBF_', code)
        code = Media.get_code_from_id('1270593720437182847_3')
        self.assertEqual('BGiDkHAgBF_', code)
        code = Media.get_code_from_id(1270593720437182847)
        self.assertEqual('BGiDkHAgBF_', code)
    
    def test_get_code_from_id(self):
        id = Media.get_id_from_code('BGiDkHAgBF_')
        self.assertEqual(1270593720437182847, id)
    
    
    def test_get_media_comments_by_code(self):
        comments = self.instagram.get_media_comments_by_code('BR5Njq1gKmB', 40)
        #TODO: check why returns less comments
        self.assertLessEqual(40, len(comments['comments']))

    def test_get_username_by_id(self):
        username = self.instagram.get_username_by_id(3)
        self.assertEqual('kevin', username)
    
    def test_get_medias_by_user_id(self):
        medias = self.instagram.get_medias_by_user_id(3)
        self.assertEqual(12, len(medias))
    
    # TODO add like test
    # TODO add unlike test
    # TODO add comment and uncomment test
    # TODO add follow unfollow test
    # TODO: Add test get_media_by_id
    # TODO: Add test get_location_by_id

if __name__ == '__main__':
    unittest.main()

