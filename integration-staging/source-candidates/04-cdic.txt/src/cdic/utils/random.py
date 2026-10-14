"""
Random number generation utilities
"""

import time
import threading
from typing import Optional
import numpy as np
from numpy.random import Generator, PCG64


class FastRandom:
    """Thread-safe fast random number generator"""
    
    def __init__(self, seed: Optional[int] = None):
        self.seed = seed or int(time.time() * 1000)
        self.generators = {}
        self.lock = threading.RLock()
    
    def get_generator(self, thread_id: Optional[int] = None) -> Generator:
        """Get thread-local random generator"""
        if thread_id is None:
            thread_id = threading.get_ident()
        
        with self.lock:
            if thread_id not in self.generators:
                # Create new generator with unique seed
                unique_seed = self.seed + thread_id
                self.generators[thread_id] = Generator(PCG64(unique_seed))
            return self.generators[thread_id]
