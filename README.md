Python wrapper for Instagram.com API. 
This fork has better support for long paginating requests.

# Quickstart

## Install

This version:
```sh
$ pip install git+https://github.com/ashvardanian/PyScrapeIg.git
```

Original version:
```sh
$ pip install igramscraper
```

## Usage

```python
>>> from ig import Instagram
>>> instagram = Instagram()
>>> me = instagram.get_account('ashvardanian')
>>> print(me)
```

If you want to get a lot of granular data use the low-level methods like `yield_pagintated_data_w_errors` and manually filter it yourself.
```python
>>> for media in instagram.yield_pagintated_data_w_errors(instagram.get_user_medias_page, user_id=me.identifier):
>>>     print(media)
```

# More info

See examples [here](https://github.com/ashvardanian/PyScrapeIg/tree/master/examples).
