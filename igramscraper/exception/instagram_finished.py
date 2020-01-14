class InstagramFinished(Exception):
    def __init__(self, request=None, cursor=None):
        super().__init__(f'Reached end of {request}, last cursor is: {cursor}')
        self._cursor = cursor

    def cursor(self):
        return self._cursor