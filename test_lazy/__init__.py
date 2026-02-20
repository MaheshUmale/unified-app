def __getattr__(name):
    if name == 'X': return 1
    raise AttributeError(name)
