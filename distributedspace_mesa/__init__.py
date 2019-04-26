# -*- coding: utf-8 -*-
"""
Mesa Agent-Based Modeling Framework

Core Objects: Model, and Agent.

"""
import datetime

from .space_distribute import Grid
from .distributed_space import Space_Distribute
from .distributed_space_test import Space_Distribute_Test
 

__all__ = ["Grid", "Space_Distribute", "Space_Distribute_Test"]


__title__ = 'distributedspace_mesa'
__version__ = '0.0.1'
__license__ = 'MIT'
__copyright__ = 'Copyright %s Tom Pike' % datetime.date.today().year
