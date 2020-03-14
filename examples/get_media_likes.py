
from context import Instagram # pylint: disable=no-name-in-module
instagram = Instagram()
for like in instagram.yield_pagintated_data(instagram.get_media_likes_page, code = 'BG3Iz-No1IZ'):
    print(like)
