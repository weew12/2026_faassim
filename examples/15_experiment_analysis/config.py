"""
文件作用：实验分析配置。

该文件集中定义输入目录、输出目录和默认文件名，避免路径逻辑散落在分析代码中。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class AnalysisConfig:
    """
    实验分析配置。

    字段：
    - input_dir：待分析实验结果目录；
    - output_dir：分析输出目录；
    - source_name：结果来源名称；
    - recursive：是否递归发现 run 目录。
    """

    input_dir: Path
    output_dir: Path
    source_name: str
    recursive: bool = True


def resolve_default_input_dir(current_file: Path) -> tuple[Path, str]:
    """
    解析默认输入目录。

    优先读取上一节 batch_experiment 的输出目录：
    examples/batch_experiment/outputs/

    如果该目录不存在或没有 runs 子目录，则回退到本样例自带的 sample_results。
    这样可以保证 experiment_analysis 样例在没有先运行 batch_experiment 时也能执行。
    """
    example_dir = current_file.resolve().parent
    examples_root = example_dir.parent

    batch_output_dir = examples_root / "batch_experiment" / "outputs"
    if (batch_output_dir / "runs").exists():
        return batch_output_dir, "batch_experiment_outputs"

    sample_dir = example_dir / "sample_results"
    return sample_dir, "sample_results"


def build_config(
    current_file: Path,
    input_dir: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> AnalysisConfig:
    """
    构造分析配置。
    """
    if input_dir:
        resolved_input = Path(input_dir).resolve()
        source_name = resolved_input.name
    else:
        resolved_input, source_name = resolve_default_input_dir(current_file)

    if output_dir:
        resolved_output = Path(output_dir).resolve()
    else:
        resolved_output = current_file.resolve().parent / "outputs"

    return AnalysisConfig(
        input_dir=resolved_input,
        output_dir=resolved_output,
        source_name=source_name,
        recursive=True,
    )
