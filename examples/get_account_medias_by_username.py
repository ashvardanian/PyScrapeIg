from context import Instagram # pylint: disable=no-name-in-module

instagram = Instagram()
me = instagram.get_account('ashvardanian')
print(me)
for media in instagram.yield_pagintated_data_w_errors(instagram.get_user_medias_page, user_id=me.identifier):
    print(media)
