# -*- coding: utf-8 -*-
"""PostgreSQL models package.

Only imported when DB_BACKEND=postgresql.
"""
from __future__ import print_function

__author__ = "bibow"

from .base import Base, normalize_row

__all__ = ["Base", "normalize_row"]