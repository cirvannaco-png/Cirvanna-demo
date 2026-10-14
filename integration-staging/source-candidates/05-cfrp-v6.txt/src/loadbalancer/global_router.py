"""
GlobalRouter – Routes users to region based on hash.
"""
import hashlib

class GlobalRouter:
    async def get_optimal_region(self, user_id: str, client_region: str = None) -> str:
        if client_region:
            return client_region
        regions = ['us-east-1', 'us-west-2', 'eu-west-1']
        idx = int(hashlib.md5(user_id.encode()).hexdigest(), 16) % len(regions)
        return regions[idx]
