"""This module contains the exceptions used in the director package."""


class DirectorException(Exception):
    """Base class for exceptions in this module."""

    def __init__(self, message="An error occurred.", **kwargs):
        super().__init__(message) 