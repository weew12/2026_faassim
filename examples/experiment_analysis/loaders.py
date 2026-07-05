"""
文件作用：统一读取实验 CSV 结果。

该文件负责发现 run 目录，并安全读取常见实验输出文件。
即使部分 CSV 缺失，也会返回空 DataFrame，保证分析流程不中断。
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


COMMON_METRIC_FILES = [
    "case_result.csv",
    "batch_invoke_probe.csv",
    "invocations.csv",
    "schedule.csv",
    "flow.csv",
    "replica_deployment.csv",
    "function_deployments.csv",
    "function_deployment_lifecycle.csv",
    "function_replicas.csv",
]


@dataclass
class RunData:
    """
    单个 run 的数据封装。

    字段：
    - run_id：run 标识；
    - run_dir：run 目录；
    - tables：CSV 文件名到 DataFrame 的映射。
    """

    run_id: str
    run_dir: Path
    tables: Dict[str, pd.DataFrame]


def read_csv_safe(path: Path) -> pd.DataFrame:
    """
    安全读取 CSV 文件。

    文件不存在或读取失败时返回空 DataFrame。
    """
    if not path.exists():
        return pd.DataFrame()

    try:
        return pd.read_csv(path)
    except Exception as err:
        logger.warning("failed to read csv %s: %s", path, err)
        return pd.DataFrame()


def discover_run_dirs(input_dir: Path) -> List[Path]:
    """
    发现实验 run 目录。

    支持两种结构：
    1. batch_experiment 输出结构：
       input_dir/runs/<case_id>/case_result.csv
    2. 直接 run 目录结构：
       input_dir/<case_id>/case_result.csv
    """
    input_dir = Path(input_dir)

    candidates: List[Path] = []

    runs_dir = input_dir / "runs"
    if runs_dir.exists():
        candidates.extend([item for item in runs_dir.iterdir() if item.is_dir()])

    candidates.extend([
        item for item in input_dir.iterdir()
        if item.is_dir() and (item / "case_result.csv").exists()
    ])

    # 去重并排序，保证结果稳定。
    unique = {path.resolve(): path for path in candidates}
    return [unique[key] for key in sorted(unique)]


def load_run_data(run_dir: Path) -> RunData:
    """
    读取单个 run 的常见结果文件。
    """
    tables: Dict[str, pd.DataFrame] = {}

    for file_name in COMMON_METRIC_FILES:
        tables[file_name] = read_csv_safe(run_dir / file_name)

    return RunData(
        run_id=run_dir.name,
        run_dir=run_dir,
        tables=tables,
    )


def load_all_runs(input_dir: Path) -> List[RunData]:
    """
    读取输入目录下的所有 run。
    """
    run_dirs = discover_run_dirs(input_dir)

    logger.info("discovered run dirs: %d", len(run_dirs))

    runs = [load_run_data(run_dir) for run_dir in run_dirs]

    for run in runs:
        logger.info("loaded run=%s dir=%s", run.run_id, run.run_dir)

    return runs
