"""
文件作用：多 case 实验运行器。
"""

from typing import Dict, List

import pandas as pd

from models import ExperimentCase, FunctionProfile, NodeState, WorkloadEvent
from progress import progress_iter
from simulator import ThesisExperimentSimulator


class ThesisExperimentRunner:
    """
    论文实验运行器。
    """

    def __init__(
        self,
        cases: List[ExperimentCase],
        profiles: Dict[str, FunctionProfile],
        nodes: Dict[str, NodeState],
        workload: List[WorkloadEvent],
    ):
        """
        初始化运行器。
        """
        self.cases = cases
        self.profiles = profiles
        self.nodes = nodes
        self.workload = workload

    def run(self):
        """
        运行所有实验 case。
        """
        request_rows = []
        decision_rows = []
        candidate_rows = []
        eviction_rows = []

        for case in progress_iter(self.cases, total=len(self.cases), desc="thesis cases"):
            simulator = ThesisExperimentSimulator(
                case=case,
                profiles=self.profiles,
                nodes=self.nodes,
                workload=self.workload,
            )
            result = simulator.run()

            request_rows.extend([item.__dict__ for item in result["request_results"]])
            decision_rows.extend([item.__dict__ for item in result["control_decisions"]])
            candidate_rows.extend([item.__dict__ for item in result["candidate_scores"]])
            eviction_rows.extend([item.__dict__ for item in result["eviction_events"]])

        return {
            "thesis_request_result": pd.DataFrame(request_rows),
            "thesis_control_decision": pd.DataFrame(decision_rows),
            "thesis_candidate_score": pd.DataFrame(candidate_rows),
            "thesis_eviction_event": pd.DataFrame(eviction_rows),
        }
