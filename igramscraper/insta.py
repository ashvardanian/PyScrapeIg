import time
import requests
import re
import json
import hashlib
import os
from slugify import slugify
import random
from .session_manager import CookieSessionManager
from .exception.instagram_auth_exception import InstagramAuthException
from .exception.instagram_exception import InstagramException
from .exception.instagram_finished import InstagramFinished
from .exception.instagram_not_found_exception import InstagramNotFoundException
from .model.account import Account
from .model.comment import Comment
from .model.location import Location
from .model.media import Media
from .model.story import Story
from .model.user_stories import UserStories
from .model.tag import Tag
from . import endpoints
from .two_step_verification.console_verification import ConsoleVerification

class Instagram:
    HTTP_NOT_FOUND = 404
    HTTP_OK = 200
    HTTP_FORBIDDEN = 403
    HTTP_BAD_REQUEST = 400

    MAX_FOLLOWERS_PER_REQUEST = 100
    MAX_FOLLOWING_PER_REQUEST = 100
    MAX_COMMENTS_PER_REQUEST = 300
    MAX_COMMENTS_PER_REQUEST = 300
    MAX_LIKES_PER_REQUEST = 50
    # 30 mins time limit on operations that require multiple self.__req
    PAGING_TIME_LIMIT_SEC = 1800
    PAGING_DELAY_MINIMUM_MICROSEC = 1000000  # 1 sec min delay to simulate browser
    PAGING_DELAY_MAXIMUM_MICROSEC = 3000000  # 3 sec max delay to simulate browser

    instance_cache = None

    def __init__(self, sleep_between_requests=0, sleep_between_rate_limits=0):
        self.__req = requests.session()
        self.paging_time_limit_sec = Instagram.PAGING_TIME_LIMIT_SEC
        self.paging_delay_minimum_microsec = Instagram.PAGING_DELAY_MINIMUM_MICROSEC
        self.paging_delay_maximum_microsec = Instagram.PAGING_DELAY_MAXIMUM_MICROSEC

        self.session_username = None
        self.session_password = None
        self.user_session = None
        self.rhx_gis = None
        self.sleep_between_requests = sleep_between_requests
        self.sleep_between_rate_limits = sleep_between_rate_limits
        self.user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_4) ' \
                          'AppleWebKit/537.36 (KHTML, like Gecko) ' \
                          'Chrome/66.0.3359.139 Safari/537.36'

    def with_credentials(self, username, password, session_folder=None):
        """
        param string username
        param string password
        param null sessionFolder

        return Instagram
        """
        Instagram.instance_cache = None

        if not session_folder:
            cwd = os.getcwd()
            session_folder = cwd + os.path.sep + 'sessions' + os.path.sep

        if isinstance(session_folder, str):

            Instagram.instance_cache = CookieSessionManager(
                session_folder, slugify(username) + '.txt')

        else:
            Instagram.instance_cache = session_folder

        Instagram.instance_cache.empty_saved_cookies()


        self.session_username = username
        self.session_password = password

    def set_proxies(self, proxy):
        if proxy and isinstance(proxy, dict):
            self.__req.proxies = proxy

    def disable_verify(self):
        self.__req.verify = False

    def disable_proxies(self):
        self.__req.proxies = {}

    def get_user_agent(self):
        return self.user_agent

    def set_user_agent(self, user_agent):
        self.user_agent = user_agent

    @staticmethod
    def set_account_medias_request_count(count):
        """
        Set how many media objects should be retrieved in a single request
        param int count
        """
        endpoints.request_media_count = count

#region Shortcuts

    def get_user_medias(self, username, count=20):
        """
        :param username: instagram username
        :param count: the number of how many media you want to get
        :param maxId: used to paginate
        :return: list of Media
        """
        account = self.get_account(username)
        return self.yield_pagintated_data(self.get_user_medias_page, user_id=account.identifier)

    def get_media_by_code(self, media_code):
        """
        :param media_code: media code
        :return: Media
        """
        url = endpoints.get_media_page_link(media_code)
        return self.get_media_by_url(url)        

    def get_media_by_id(self, media_id):
        """
        :param media_id: media id
        :return: list of Media
        """
        media_link = Media.get_link_from_id(media_id)
        return self.get_media_by_url(media_link)

#endregion

#region Single Batch Retrieval

    def get_account_by_id(self, id):
        """
        :param id: account id
        :return: Account
        """
        username = self.get_username_by_id(id)
        return self.get_account(username)

    def get_username_by_id(self, id):
        """
        :param id: account id
        :return: username string from response
        """
        time.sleep(self.sleep_between_requests)
        response = self.__req.get(
            endpoints.get_account_json_private_info_link_by_account_id(
                id), headers=self.generate_headers(self.user_session))

        if Instagram.HTTP_NOT_FOUND == response.status_code:
            raise InstagramNotFoundException(
                'Failed to fetch account with given id')

        if Instagram.HTTP_OK != response.status_code:
            raise InstagramException.default(response.text,
                                             response.status_code)

        json_response = response.json()
        if not json_response:
            raise InstagramException('Response does not JSON')

        if json_response['status'] != 'ok':
            message = json_response['message'] if (
                    'message' in json_response.keys()) else 'Unknown Error'
            raise InstagramException(message)

        return json_response['user']['username']
        
    def get_media_by_url(self, media_url):
        """
        :param media_url: media url
        :return: Media
        """
        url_regex = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'

        if len(re.findall(url_regex, media_url)) <= 0:
            raise ValueError('Malformed media url')

        url = media_url.rstrip('/') + '/?__a=1'
        time.sleep(self.sleep_between_requests)
        response = self.__req.get(url, headers=self.generate_headers(
            self.user_session))

        if Instagram.HTTP_NOT_FOUND == response.status_code:
            raise InstagramNotFoundException(
                'Media with given code does not exist or account is private.')

        if Instagram.HTTP_OK != response.status_code:
            raise InstagramException.default(response.text,
                                             response.status_code)

        media_array = response.json()
        try:
            media_in_json = media_array['graphql']['shortcode_media']
        except KeyError:
            raise InstagramException('Media with this code does not exist')

        return Media(media_in_json)

    def get_medias_from_feed(self, username, count=20):
        """
        :param username: instagram username
        :param count: the number of how many media you want to get
        :return: list of Media
        """
        time.sleep(self.sleep_between_requests)
        response = self.__req.get(endpoints.get_account_json_link(username),
                                  headers=self.generate_headers(self.user_session))

        if Instagram.HTTP_NOT_FOUND == response.status_code:
            raise InstagramNotFoundException(
                'Account with given username does not exist.')

        if Instagram.HTTP_OK != response.status_code:
            raise InstagramException.default(response.text,
                                             response.status_code)

        user_array = response.json()

        try:
            user = user_array['graphql']['user']
        except KeyError:
            raise InstagramNotFoundException(
                'Account with this username does not exist')
        try:
            nodes = user['edge_owner_to_timeline_media']['edges']
        except Exception:
            return None
        medias = [Media(media_array['node']) for media_array in nodes]
        return medias

    def get_account(self, username):
        """
        :param username: username
        :return: Account
        """
        time.sleep(self.sleep_between_requests)
        response = self.__req.get(endpoints.get_account_page_link(
            username), headers=self.generate_headers(self.user_session))

        if Instagram.HTTP_NOT_FOUND == response.status_code:
            raise InstagramNotFoundException(
                'Account with given username does not exist.')

        if Instagram.HTTP_OK != response.status_code:
            raise InstagramException.default(response.text,
                                             response.status_code)

        user_array = Instagram.extract_shared_data_from_body(response.text)
        if user_array['entry_data']['ProfilePage'][0]['graphql']['user'] is None:
            raise InstagramNotFoundException(
                'Account with this username does not exist')

        return Account(
            user_array['entry_data']['ProfilePage'][0]['graphql']['user'])


    def get_stories(self, reel_ids=None):
        """
        :param reel_ids: reel ids
        :return: UserStories List
        """
        variables = {
            'precomposed_overlay': False, 
            'reel_ids': []
        }

        if reel_ids is None or len(reel_ids) == 0:
            time.sleep(self.sleep_between_requests)
            response = self.__req.get(endpoints.get_user_stories_link(),
                                      headers=self.generate_headers(self.user_session))

            if not Instagram.HTTP_OK == response.status_code:
                raise InstagramException.default(response.text,
                                                 response.status_code)

            json_response = response.json()
            try:
                edges = json_response['data']['user']['feed_reels_tray'][
                    'edge_reels_tray_to_reel']['edges']
            except KeyError:
                return None
            for edge in edges:
                variables['reel_ids'].append(edge['node']['id'])
        else:
            variables['reel_ids'] = reel_ids

        time.sleep(self.sleep_between_requests)
        response = self.__req.get(endpoints.get_stories_link(variables),
                                  headers=self.generate_headers(
                                      self.user_session))

        if not Instagram.HTTP_OK == response.status_code:
            raise InstagramException.default(response.text,
                                             response.status_code)

        json_response = response.json()
        try:
            reels_media = json_response['data']['reels_media']
        except KeyError:
            return None

        stories = []
        for user in reels_media:
            user_stories = UserStories()
            user_stories.owner = Account(user['user'])
            for item in user['items']:
                story = Story(item)
                user_stories.stories.append(story)
            stories.append(user_stories)
        return stories

    # TODO not optimal separate http call after getMedia
    def get_users_tagged_in_media(self, code):
        """
        :param code: media short code
        :return: list contains tagged_users dict
        """
        url = endpoints.get_media_json_link(code)
        time.sleep(self.sleep_between_requests)
        response = self.__req.get(url, headers=self.generate_headers(
            self.user_session))

        if not Instagram.HTTP_OK == response.status_code:
            raise InstagramException.default(response.text,
                                             response.status_code)

        json_response = response.json()
        try:
            tag_data = json_response['graphql']['shortcode_media'][
                'edge_media_to_tagged_user']['edges']
        except KeyError:
            return None

        tagged_users = []
        for tag in tag_data:
            x_pos = tag['node']['x']
            y_pos = tag['node']['y']
            user = tag['node']['user']
            # TODO: add Model and add Data to it instead of Dict
            tagged_user = dict()
            tagged_user['x_pos'] = x_pos
            tagged_user['y_pos'] = y_pos
            tagged_user['user'] = user
            tagged_users.append(tagged_user)

        return tagged_users

#endregion
#region Search

    def searc_users_named(self, username):
        """
        :param username: user name
        :return: Account List
        """
        time.sleep(self.sleep_between_requests)
        response = self.__req.get(
            endpoints.get_general_search_json_link(username),
            headers=self.generate_headers(self.user_session))

        if Instagram.HTTP_NOT_FOUND == response.status_code:
            raise InstagramNotFoundException(
                'Account with given username does not exist.')

        if not Instagram.HTTP_OK == response.status_code:
            raise InstagramException.default(response.text,
                                             response.status_code)

        json_response = response.json()
        try:
            status = json_response['status']
            if not status == 'ok':
                raise InstagramException(
                    'Response code is not equal 200.'
                    ' Something went wrong. Please report issue.')
        except KeyError:
            raise InstagramException(
                'Response code is not equal 200.'
                ' Something went wrong. Please report issue.')

        try:
            users = json_response['users']
        except KeyError:
            return None

        accounts = [Account(json_account['user']) for json_account in users]
        return accounts

    def search_tags_similar_to(self, tag):
        """
        :param tag: tag string
        :return: list of Tag
        """
        # TODO: Add tests and auth
        time.sleep(self.sleep_between_requests)
        response = self.__req.get(endpoints.get_general_search_json_link(tag))

        if Instagram.HTTP_NOT_FOUND == response.status_code:
            raise InstagramNotFoundException(
                'Account with given username does not exist.')
        if not Instagram.HTTP_OK == response.status_code:
            raise InstagramException.default(response.text,
                                             response.status_code)

        json_response = response.json()
        try:
            status = json_response['status']
            if status != 'ok':
                raise InstagramException(
                    'Response code is not equal 200. '
                    'Something went wrong. Please report issue.')
        except KeyError:
            raise InstagramException('Response code is not equal 200. Something went wrong. Please report issue.')
        try:
            hashtags_raw = json_response['hashtags']
        except KeyError:
            return None

        hashtags = [Tag(json_hashtag['hashtag']) for json_hashtag in hashtags_raw]
        return hashtags

    def search_top_tag_medias(self, tag_name):
        """
        :param tag_name: tag string
        :return: list of the top Media
        """
        time.sleep(self.sleep_between_requests)
        response = self.__req.get(
            endpoints.get_medias_json_by_tag_link(tag_name, ''),
            headers=self.generate_headers(self.user_session))

        if response.status_code == Instagram.HTTP_NOT_FOUND:
            raise InstagramNotFoundException(
                'Account with given username does not exist.')

        if response.status_code is not Instagram.HTTP_OK:
            raise InstagramException.default(response.text,
                                             response.status_code)

        json_response = response.json()
        nodes = json_response['graphql']['hashtag']['edge_hashtag_to_top_posts']['edges']
        medias = [Media(media_array['node']) for media_array in nodes]
        return medias

    def search_top_place_medias(self, facebook_location_id):
        """
        :param facebook_location_id: facebook location id
        :return: list of the top Media
        """
        time.sleep(self.sleep_between_requests)
        response = self.__req.get(
            endpoints.get_medias_json_by_location_id_link(facebook_location_id),
            headers=self.generate_headers(self.user_session))
        if response.status_code == Instagram.HTTP_NOT_FOUND:
            raise InstagramNotFoundException(
                "Location with this id doesn't exist")

        if response.status_code != Instagram.HTTP_OK:
            raise InstagramException.default(response.text,
                                             response.status_code)

        json_response = response.json()
        nodes = json_response['graphql']['location']['edge_location_to_top_posts']['edges']
        medias = [Media(media_array['node']) for media_array in nodes]
        return medias

    def search_place_by_facebook_id(self, facebook_location_id):
        """
        :param facebook_location_id: facebook location id
        :return: Location
        """
        time.sleep(self.sleep_between_requests)
        response = self.__req.get(
            endpoints.get_medias_json_by_location_id_link(facebook_location_id),
            headers=self.generate_headers(self.user_session))

        if response.status_code == Instagram.HTTP_NOT_FOUND:
            raise InstagramNotFoundException(
                'Location with this id doesn\'t exist')

        if response.status_code != Instagram.HTTP_OK:
            raise InstagramException.default(response.text,
                                             response.status_code)

        json_response = response.json()
        return Location(json_response['graphql']['location'])

#endregion
#region Pagination

    def yield_pagintated_data_w_errors(self, method, current_cursor='', max_count=None, **kwargs):        
        """
        Goes over content and yields dictionaries from each response one-by-one.
        If it registers an error - it yields the `Exception` object and retries the same page.
        """
        count = 0
        while True:
            response = None
            try:
                response = method(max_id = current_cursor, **kwargs)
            except Exception as e:
                yield e
                continue
            # Unpack the results.
            if response is None:
                return
            for obj in response['results']:
                yield obj
                count += 1
                if count == max_count:
                    return
            # Check if we should make another request.
            if not response['paging']['has_next_page']:
                yield InstagramFinished(request = str(method), cursor = current_cursor)
                return
            current_cursor = response['paging']['end_cursor']

    def yield_pagintated_data(self, method, current_cursor='', max_retries=3, max_count=None, **kwargs):        
        retries_left = max_retries
        for v in self.yield_pagintated_data_w_errors(method, current_cursor, max_count, **kwargs):
            if isinstance(v, InstagramFinished):
                return
            elif isinstance(v, InstagramException):
                if v.code() == 429:
                    if retries_left > 0:
                        retries_left -= 1
                        time.sleep(self.sleep_between_rate_limits)
                        continue
                raise v
            elif isinstance(v, Exception):
                raise v
            else: 
                yield v

    def collect_pagintated_data(self, method, max_count = None, **kwargs) -> list:        
        return list(self.yield_pagintated_data(method, max_count, **kwargs))

#endregion

#region Paginated Methods

    def get_user_medias_page(self, user_id, max_id=''):
        """
        :param user_id: instagram user id
        :param max_id: used to paginate next time
        :return: dict that contains Media list, maxId, hasNextPage
        """
        variables = {
            'id': str(user_id),
            'first': str(endpoints.request_media_count),
            'after': str(max_id)
        }
        time.sleep(self.sleep_between_requests)
        response = self.__req.get(
            endpoints.get_account_medias_json_link(variables),
            headers=self.generate_headers(self.user_session,
                                          self.__generate_gis_token(variables)))

        if not Instagram.HTTP_OK == response.status_code:
            raise InstagramException.default(response.text,
                                             response.status_code)

        json_resp = response.json()
        try:
            nodes = json_resp['data']['user']['edge_owner_to_timeline_media']['edges']
        except KeyError:
            return None

        medias = [Media(media_array['node']) for media_array in nodes]
        paging = json_resp['data']['user']['edge_owner_to_timeline_media']['page_info']
        return {
            'results': medias,
            'paging': paging
        }

    def get_tag_medias_page(self, tag, max_id=''):
        """
        :param tag: tag name
        :param max_id: used to paginate next time
        :return: dict that contains Media list, maxId, hasNextPage
        """
        time.sleep(self.sleep_between_requests)
        response = self.__req.get(
            endpoints.get_medias_json_by_tag_link(tag, max_id),
            headers=self.generate_headers(self.user_session))

        if response.status_code != Instagram.HTTP_OK:
            raise InstagramException.default(response.text,
                                             response.status_code)

        json_resp = response.json()
        try:
            nodes = json_resp['graphql']['hashtag']['edge_hashtag_to_media']['edges']
        except KeyError:
            return None

        medias = [Media(media_array['node']) for media_array in nodes]
        paging = json_resp['graphql']['hashtag']['edge_hashtag_to_media']['page_info']
        return {
            'results': medias,
            'paging': paging
        }

    def get_media_likes_page(self, code, max_id=''):
        """
        :param code:
        :param count:
        :param max_id:
        :return:
        """
        variables = {
            "shortcode": str(code),
            "first": str(self.MAX_LIKES_PER_REQUEST),
            "after": max_id
        }
        time.sleep(self.sleep_between_requests)
        response = self.__req.get(
            endpoints.get_last_likes_by_code(variables),
            headers=self.generate_headers(self.user_session))

        if not response.status_code == Instagram.HTTP_OK:
            raise InstagramException.default(response.text,response.status_code)

        json_resp = response.json()
        nodes = json_resp['data']['shortcode_media']['edge_liked_by']['edges']
        likes = [Account(likes_array['node']) for likes_array in nodes]
        paging = json_resp['data']['shortcode_media']['edge_liked_by']['page_info']
        # number_of_likes = json_resp['data']['shortcode_media']['edge_liked_by']['count']
        return {
            'results': likes,
            'paging': paging
        }

    def get_media_comments_page(self, code, max_id=''):
        variables = {
            "shortcode": str(code),
            "first": str(self.MAX_COMMENTS_PER_REQUEST),
            "after": max_id
        }
        time.sleep(self.sleep_between_requests)
        comments_url = endpoints.get_comments_before_comments_id_by_code(variables)        
        response = self.__req.get(comments_url,
                                    headers=self.generate_headers(
                                        self.user_session,
                                        self.__generate_gis_token(variables)))

        if not response.status_code == Instagram.HTTP_OK:
            raise InstagramException.default(response.text,
                                                response.status_code)

        json_resp = response.json()
        nodes = json_resp['data']['shortcode_media']['edge_media_to_parent_comment']['edges']
        comments = [Comment(commentArray['node']) for commentArray in nodes]
        paging = json_resp['data']['shortcode_media']['edge_media_to_parent_comment']['page_info']
        # number_of_comments = json_resp['data']['shortcode_media']['edge_media_to_parent_comment']['count']
        return {
            'results': comments,
            'paging': paging
        }

    def get_followers(self, account_id, max_id=''):
        time.sleep(self.sleep_between_requests)
        variables = {
            'id': str(account_id),
            'first': str(self.MAX_FOLLOWERS_PER_REQUEST),
            'after': max_id
        }
        response = self.__req.get(
            endpoints.get_followers_json_link(variables),
            headers=self.generate_headers(self.user_session))

        if not response.status_code == Instagram.HTTP_OK:
            raise InstagramException.default(response.text,
                                                response.status_code)

        json_resp = response.json()
        if json_resp['data']['user']['edge_followed_by']['count'] == 0:
            return None

        edges_array = json_resp['data']['user']['edge_followed_by']['edges']
        if len(edges_array) == 0:
            InstagramException(
                f'Failed to get followers of account id {account_id}.'
                f' The account is private.', Instagram.HTTP_FORBIDDEN)

        followers = [Account(edge['node']) for edge in edges_array]
        paging = json_resp['data']['user']['edge_followed_by']['page_info']
        return {
            'results': followers,
            'paging': paging
        }


    def get_following(self, account_id, max_id=''):
        time.sleep(self.sleep_between_requests)
        variables = {
            'id': str(account_id),
            'first': str(self.MAX_FOLLOWING_PER_REQUEST),
            'after': max_id
        }
        response = self.__req.get(
            endpoints.get_following_json_link(variables),
            headers=self.generate_headers(self.user_session))

        if not response.status_code == Instagram.HTTP_OK:
            raise InstagramException.default(response.text,
                                                response.status_code)

        json_resp = response.json()
        if json_resp['data']['user']['edge_follow']['count'] == 0:
            return None

        edges_array = json_resp['data']['user']['edge_follow']['edges']
        if len(edges_array) == 0:
            raise InstagramException(
                f'Failed to get follows of account id {account_id}.'
                f' The account is private.', Instagram.HTTP_FORBIDDEN)

        paging = json_resp['data']['user']['edge_follow']['page_info']
        following = [Account(edge['node']) for edge in edges_array]
        return {
            'results': following,
            'paging': paging
        }

#endregion

#region Auth

    def is_logged_in(self, session):
        """
        :param session: session dict
        :return: bool
        """
        if session is None or 'sessionid' not in session.keys():
            return False

        session_id = session['sessionid']
        csrf_token = session['csrftoken']
        headers = {
            'cookie': f"ig_cb=1; csrftoken={csrf_token}; sessionid={session_id};",
            'referer': endpoints.BASE_URL + '/',
            'x-csrftoken': csrf_token,
            'X-CSRFToken': csrf_token,
            'user-agent': self.user_agent,
        }

        time.sleep(self.sleep_between_requests)
        response = self.__req.get(endpoints.BASE_URL, headers=headers)
        if not response.status_code == Instagram.HTTP_OK:
            return False

        cookies = response.cookies.get_dict()
        if cookies is None or not 'ds_user_id' in cookies.keys():
            return False
        return True

    def login(self, force=False, two_step_verificator=None):
        """support_two_step_verification true works only in cli mode - just run login in cli mode - save cookie to file and use in any mode
        :param force: true will refresh the session
        :param two_step_verificator: true will need to do verification when an account goes wrong
        :return: headers dict
        """
        if self.session_username is None or self.session_password is None:
            raise InstagramAuthException("User credentials not provided")

        if two_step_verificator:
            two_step_verificator = ConsoleVerification()

        session = json.loads(
            Instagram.instance_cache.get_saved_cookies()) if Instagram.instance_cache.get_saved_cookies() != None else None

        if force or not self.is_logged_in(session):
            time.sleep(self.sleep_between_requests)
            response = self.__req.get(endpoints.BASE_URL)
            if not response.status_code == Instagram.HTTP_OK:
                raise InstagramException.default(response.text,
                                                 response.status_code)

            match = re.findall(r'"csrf_token":"(.*?)"', response.text)

            if len(match) > 0:
                csrfToken = match[0]

            cookies = response.cookies.get_dict()

            # cookies['mid'] doesnt work at the moment so fetch it with function
            mid = self.__get_mid()

            headers = {
                'cookie': f"ig_cb=1; csrftoken={csrfToken}; mid={mid};",
                'referer': endpoints.BASE_URL + '/',
                'x-csrftoken': csrfToken,
                'X-CSRFToken': csrfToken,
                'user-agent': self.user_agent,
            }
            payload = {'username': self.session_username,
                       'password': self.session_password}
            response = self.__req.post(endpoints.LOGIN_URL, data=payload,
                                       headers=headers)

            if not response.status_code == Instagram.HTTP_OK:
                if (
                        response.status_code == Instagram.HTTP_BAD_REQUEST
                        and response.text is not None
                        and response.json()['message'] == 'checkpoint_required'
                        and two_step_verificator is not None):
                    response = self.__verify_two_step(response, cookies,
                                                      two_step_verificator)
                    print('checkpoint required')

                elif response.status_code is not None and response.text is not None:
                    raise InstagramAuthException(
                        f'Response code is {response.status_code}. Body: {response.text} Something went wrong. Please report issue.',
                        response.status_code)
                else:
                    raise InstagramAuthException(
                        'Something went wrong. Please report issue.',
                        response.status_code)

            if not response.json()['authenticated']:
                raise InstagramAuthException('User credentials are wrong.')

            cookies = response.cookies.get_dict()
            cookies['mid'] = mid
            Instagram.instance_cache.set_saved_cookies(json.dumps(cookies, separators=(',', ':')))
            self.user_session = cookies
        else:
            self.user_session = session

        return self.generate_headers(self.user_session)

#endregion

#region Authorized actions

    def add_comment(self, media_id, text, replied_to_comment_id=None):
        """
        :param media_id: media id
        :param text:  the content you want to post
        :param replied_to_comment_id: the id of the comment you want to reply
        :return: Comment
        """
        media_id = media_id.identifier if isinstance(media_id, Media) else media_id
        replied_to_comment_id = replied_to_comment_id._data['id'] if isinstance(replied_to_comment_id, Comment) else replied_to_comment_id
        body = {
            'comment_text': text,
            'replied_to_comment_id': replied_to_comment_id if replied_to_comment_id is not None else ''
        }
        response = self.__req.post(endpoints.get_add_comment_url(media_id),
                                   data=body, 
                                   headers=self.generate_headers(self.user_session))

        if not Instagram.HTTP_OK == response.status_code:
            raise InstagramException.default(response.text,
                                             response.status_code)

        json_response = response.json()
        if json_response['status'] != 'ok':
            status = json_response['status']
            raise InstagramException(
                f'Response status is {status}. '
                f'Body: {response.text} Something went wrong.'
                f' Please report issue.',
                response.status_code)
        return Comment(json_response)

    def delete_comment(self, media_id, comment_id):
        media_id = media_id.identifier if isinstance(media_id,
                                                     Media) else media_id
        comment_id = comment_id._data['id'] if isinstance(comment_id,
                                                          Comment) else comment_id
        response = self.__req.post(
            endpoints.get_delete_comment_url(media_id, comment_id),
            headers=self.generate_headers(self.user_session))

        if not Instagram.HTTP_OK == response.status_code:
            raise InstagramException.default(response.text,
                                             response.status_code)
        json_response = response.json()
        if json_response['status'] != 'ok':
            status = json_response['status']
            raise InstagramException(
                f'Response status is {status}. '
                f'Body: {response.text} Something went wrong.'
                f' Please report issue.',
                response.status_code)

    def like(self, media_id):
        media_id = media_id.identifier if isinstance(media_id,
                                                     Media) else media_id
        response = self.__req.post(endpoints.get_like_url(media_id),
                                   headers=self.generate_headers(
                                       self.user_session))

        if not Instagram.HTTP_OK == response.status_code:
            raise InstagramException.default(response.text,
                                             response.status_code)

        json_response = response.json()

        if json_response['status'] != 'ok':
            status = json_response['status']
            raise InstagramException(
                f'Response status is {status}. '
                f'Body: {response.text} Something went wrong.'
                f' Please report issue.',
                response.status_code)

    def unlike(self, media_id):
        media_id = media_id.identifier if isinstance(media_id,
                                                     Media) else media_id
        response = self.__req.post(endpoints.get_unlike_url(media_id),
                                   headers=self.generate_headers(
                                       self.user_session))

        if not Instagram.HTTP_OK == response.status_code:
            raise InstagramException.default(response.text,
                                             response.status_code)

        json_response = response.json()
        if json_response['status'] != 'ok':
            status = json_response['status']
            raise InstagramException(
                f'Response status is {status}. '
                f'Body: {response.text} Something went wrong.'
                f' Please report issue.',
                response.status_code)

    def follow(self, user_id) -> bool:
        if self.is_logged_in(self.user_session):
            url = endpoints.get_follow_url(user_id)
            try:
                follow = self.__req.post(url,
                                         headers=self.generate_headers(
                                             self.user_session))
                if follow.status_code == Instagram.HTTP_OK:
                    return True
            except:
                raise InstagramException("Except on follow!")
        return False

    def unfollow(self, user_id) -> bool:
        if self.is_logged_in(self.user_session):
            url_unfollow = endpoints.get_unfollow_url(user_id)
            try:
                unfollow = self.__req.post(url_unfollow)
                if unfollow.status_code == Instagram.HTTP_OK:
                    return unfollow
            except:
                raise InstagramException("Exept on unfollow!")
        return False

#endregion

#region System


    def generate_headers(self, session, gis_token=None):
        """
        :param session: user session dict
        :param gis_token: a token used to be verified by instagram in header
        :return: header dict
        """
        headers = {}
        if session is not None:
            cookies = ''

            for key in session.keys():
                cookies += f"{key}={session[key]}; "

            csrf = session['x-csrftoken'] if session['csrftoken'] is None else \
                session['csrftoken']

            headers = {
                'cookie': cookies,
                'referer': endpoints.BASE_URL + '/',
                'x-csrftoken': csrf
            }

        if self.user_agent is not None:
            headers['user-agent'] = self.user_agent

            if gis_token is not None:
                headers['x-instagram-gis'] = gis_token

        return headers

    def __generate_gis_token(self, variables):
        """
        :param variables: a dict used to  generate_gis_token
        :return: a token used to be verified by instagram
        """
        rhx_gis = self.__get_rhx_gis() if self.__get_rhx_gis() is not None else 'NULL'
        string_to_hash = ':'.join([rhx_gis, json.dumps(variables, separators=(',', ':')) if isinstance(variables, dict) else variables])
        return hashlib.md5(string_to_hash.encode('utf-8')).hexdigest()

    def __get_rhx_gis(self):
        """
        :return: a string to generate gis_token
        """
        if self.rhx_gis is None:
            try:
                shared_data = self.__get_shared_data_from_page()
            except Exception as _:
                raise InstagramException('Could not extract gis from page')

            if 'rhx_gis' in shared_data.keys():
                self.rhx_gis = shared_data['rhx_gis']
            else:
                self.rhx_gis = None

        return self.rhx_gis

    def __get_mid(self):
        """manually fetches the machine id from graphQL"""
        time.sleep(self.sleep_between_requests)
        response = self.__req.get('https://www.instagram.com/web/__mid/')

        if response.status_code != Instagram.HTTP_OK:
            raise InstagramException.default(response.text,
                                             response.status_code)

        return response.text

    def __get_shared_data_from_page(self, url=endpoints.BASE_URL):
        """
        :param url: the requested url
        :return: a dict extract from page
        """
        url = url.rstrip('/') + '/'
        time.sleep(self.sleep_between_requests)
        response = self.__req.get(url, headers=self.generate_headers(
            self.user_session))

        if Instagram.HTTP_NOT_FOUND == response.status_code:
            raise InstagramNotFoundException(f"Page {url} not found")

        if not Instagram.HTTP_OK == response.status_code:
            raise InstagramException.default(response.text,
                                             response.status_code)

        return Instagram.extract_shared_data_from_body(response.text)

    @staticmethod
    def extract_shared_data_from_body(body):
        """
        :param body: html string from a page
        :return: a dict extract from page
        """
        array = re.findall(r'_sharedData = .*?;</script>', body)
        if len(array) > 0:
            raw_json = array[0][len("_sharedData ="):-len(";</script>")]

            return json.loads(raw_json)

        return None

    def __verify_two_step(self, response, cookies, two_step_verificator):
        """
        :param response: Response object returned by Request
        :param cookies: user cookies
        :param two_step_verificator: two_step_verification instance
        :return: Response
        """
        new_cookies = response.cookies.get_dict()
        cookies = {**cookies, **new_cookies}

        cookie_string = ''
        for key in cookies.keys():
            cookie_string += f'{key}={cookies[key]};'

        headers = {
            'cookie': cookie_string,
            'referer': endpoints.LOGIN_URL,
            'x-csrftoken': cookies['csrftoken'],
            'user-agent': self.user_agent,
        }
        url = endpoints.BASE_URL + response.json()['checkpoint_url']
        time.sleep(self.sleep_between_requests)
        response = self.__req.get(url, headers=headers)
        data = Instagram.extract_shared_data_from_body(response.text)

        if data is not None:
            try:
                choices = \
                    data['entry_data']['Challenge'][0]['extraData']['content'][
                        3]['fields'][0]['values']
            except KeyError:
                choices = dict()
                try:
                    fields = data['entry_data']['Challenge'][0]['fields']
                    try:
                        choices.update({
                            'label': f"Email: {fields['email']}",
                            'value': 1
                        })
                    except KeyError:
                        pass
                    try:
                        choices.update({
                            'label': f"Phone: {fields['phone_number']}",
                            'value': 0
                        })
                    except KeyError:
                        pass
                except KeyError:
                    pass

            if len(choices) > 0:
                selected_choice = two_step_verificator.get_verification_type(
                    choices)
                response = self.__req.post(url,
                                           data={'choice': selected_choice},
                                           headers=headers)

        if len(re.findall('name="security_code"', response.text)) <= 0:
            raise InstagramAuthException(
                'Something went wrong when try '
                'two step verification. Please report issue.',
                response.status_code)

        security_code = two_step_verificator.get_security_code()

        post_data = {
            'csrfmiddlewaretoken': cookies['csrftoken'],
            'verify': 'Verify Account',
            'security_code': security_code,
        }
        response = self.__req.post(url, data=post_data, headers=headers)
        if not response.status_code == Instagram.HTTP_OK \
                or 'Please check the code we sent you and try again' in response.text:
            raise InstagramAuthException(
                'Something went wrong when try two step'
                ' verification and enter security code. Please report issue.',
                response.status_code)
        return response
        
#endregion