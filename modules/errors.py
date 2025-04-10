import discord


class JellycordException(Exception):
    """
    Base exception class for Jellycord
    """
    code: int

    def __init__(self, code: int, message: str):
        self.code: int = code or 300  # Default to 300 if no code is provided
        super().__init__(message)


class JellycordMigrationFailure(JellycordException):
    """
    Raised when an error occurs during Jellycord migrations
    """

    def __init__(self, message: str):
        super().__init__(code=301, message=message)


class JellycordSetupFailure(JellycordException):
    """
    Raised when an error occurs during Jellycord setup
    """

    def __init__(self, message: str):
        super().__init__(code=302, message=message)


class JellycordDiscordCollectionFailure(JellycordException):
    """
    Raised when an error occurs during collecting a Discord object
    """

    def __init__(self, message: str):
        super().__init__(code=303, message=message)


class JellycordAPIFailure(JellycordException):
    """
    Raised when an error occurs during an API call
    """

    def __init__(self, message: str):
        super().__init__(code=304, message=message)


def determine_exit_code(exception: Exception) -> int:
    """
    Determine the exit code based on the exception that was thrown

    :param exception: The exception that was thrown
    :return: The exit code
    """
    if isinstance(exception, discord.LoginFailure):
        return 101  # Invalid Discord token
    elif isinstance(exception, discord.PrivilegedIntentsRequired):
        return 102  # Privileged intents are required
    elif isinstance(exception, JellycordException):
        return exception.code
    else:
        return 1
