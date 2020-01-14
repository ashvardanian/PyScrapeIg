class InstagramException(Exception):
    def __init__(self, message="", code=500):
        super().__init__(f'{message}, Code:{code}')
        self._code = code
    
    @staticmethod
    def default(response_text, status_code):
        return InstagramException(
            'Response code is {status_code}. Body: {response_text} '
            'Something went wrong. Please report issue.'.format(
                response_text=response_text, status_code=status_code),
            status_code)

    def code(self):
        return self._code