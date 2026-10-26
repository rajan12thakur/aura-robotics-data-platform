#!/usr/bin/env python
"""Django management entry point for AURA."""

import os
import sys

from django.core.management import execute_from_command_line

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "aura_api.settings")
execute_from_command_line(sys.argv)
