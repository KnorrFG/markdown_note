from collections import UserDict

class AttrDict(UserDict):
    def __init__(self, contents=None, **kwargs):
        super().__init__(contents)
        if type(contents) == dict:
            self.data = {
                    key: AttrDict(value) if type(value) == dict else value
                    for key, value in self.data.items()}
        self.data.update(kwargs)

    def __getattribute__(self, key):
        try:
            return object.__getattribute__(self, key)
        except AttributeError:
            data = object.__getattribute__(self, "data")

            if key not in data:
                raise AttributeError
            else:
                return data[key]
