"""This module contains the exceptions used in the director package."""


class DirectorException(Exception):
    """Base class for exceptions in this module."""

    def __init__(self, message="An error occurred.", **kwargs):
        super().__init__(message)


class AgentException(DirectorException):
    """Exception raised for errors in the agent."""

    def __init__(self, message="An error occurred in the agent", **kwargs):
        super().__init__(message)


class ToolException(DirectorException):
    """Exception raised for errors in the tool."""

    def __init__(self, message="An error occurred in the tool", **kwargs):
        super().__init__(message)
