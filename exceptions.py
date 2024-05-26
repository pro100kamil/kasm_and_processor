class UnknownCommandError(Exception):
    def __init__(self, command):
        super().__init__(f"command {command} is unknown")
