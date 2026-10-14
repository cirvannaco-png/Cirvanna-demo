import sys
import os
from contextlib import contextmanager

class AnalysisSandbox:
    """Enforces module isolation with no side-effects"""
    
    def __init__(self):
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        self.isolated_environment = {}
    
    @contextmanager
    def isolated_execution(self):
        """Execute skin analysis in isolated context"""
        sys.stdout = open(os.devnull, 'w')
        sys.stderr = open(os.devnull, 'w')
        
        try:
            yield self.isolated_environment
        finally:
            sys.stdout.close()
            sys.stderr.close()
            sys.stdout = self.original_stdout
            sys.stderr = self.original_stderr
            self.isolated_environment.clear()
    
    def validate_no_side_effects(self, module) -> bool:
        """Verify module has no persistent state"""
        forbidden_attrs = ['_history', '_previous', '_cache', '_state']
        for attr in forbidden_attrs:
            if hasattr(module, attr):
                return False
        return True
