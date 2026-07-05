"""
文件作用：策略实验执行器。
"""

from typing import Dict, List

import pandas as pd

from models import FunctionProfile, RequestEvent
from policies import KeepAlivePolicy


class ColdStartAwarePolicyRunner:
    """
    冷启动感知策略实验执行器。
    """

    def __init__(
        self,
        profiles: Dict[str, FunctionProfile],
        requests: List[RequestEvent],
        policies: List[KeepAlivePolicy],
    ):
        """
        初始化执行器。
        """
        self.profiles = profiles
        self.requests = requests
        self.policies = policies

    def run(self):
        """
        运行所有策略。
        """
        request_result_rows = []
        policy_decision_rows = []
        eviction_rows = []

        for policy in self.policies:
            for request in self.requests:
                policy.handle_request(request)

            request_result_rows.extend([item.__dict__ for item in policy.request_results])
            policy_decision_rows.extend([item.__dict__ for item in policy.policy_decisions])
            eviction_rows.extend([item.__dict__ for item in policy.evictions])

        return {
            "cold_start_request_result": pd.DataFrame(request_result_rows),
            "cold_start_policy_decision": pd.DataFrame(policy_decision_rows),
            "cold_start_eviction": pd.DataFrame(eviction_rows),
        }
