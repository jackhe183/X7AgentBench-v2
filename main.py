"""
X7 Agent Benchmark Framework

CLI 用法：
  python main.py                              # 使用默认数据集路径
  python main.py --dataset path/to/data.json  # 指定数据集
  python main.py --scene 公网出口             # 只跑指定场景名

批量运行逻辑：
1. 加载数据集
2. 通过 ReportGenerator.get_completed_case_ids() 获取已完成的序号集合
3. 过滤掉已完成的 case（断点续传）
4. 逐个运行 DialogueRunner.run(test_case)
5. 每个 case 用 try/except 包裹，异常时记录 FAILED 状态并 continue，不停整批
6. 全部结束后打印汇总（总数/成功/失败/平均分）
7. 保存 summary.json 到 output_dir
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from config import Config
from data_structures import TestCase
from dialogue_runner import DialogueRunner
from report_generator import ReportGenerator


def load_dataset(dataset_path: str) -> list[dict]:
    """加载 JSON 数据集文件。"""
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def dict_to_test_case(d: dict) -> TestCase:
    """把 dict 转成 TestCase dataclass。"""
    return TestCase(
        序号=d["序号"],
        客户问题=d["客户问题"],
        客户信息=d.get("客户信息", []),
        会话特征=d.get("会话特征", []),
        参考答案=d.get("参考答案", []),
        判停规则=d.get("判停规则", []),
        打分规则=d.get("打分规则", []),
        标注信息=d.get("标注信息", {})
    )


def run_benchmark(dataset_path: str, scene_filter: str | None = None):
    """
    执行批量基准测试。
    """
    config = Config()

    # 加载数据集
    dataset = load_dataset(dataset_path)

    # 获取数据集名称（用于输出目录结构）
    dataset_name = Path(dataset_path).stem

    # 初始化组件
    runner = DialogueRunner(config)
    report_gen = ReportGenerator(config)

    # 断点续传：获取已完成的 case ID
    completed_ids = report_gen.get_completed_case_ids(dataset_name)
    print(f"已完成的 case 数量：{len(completed_ids)}")

    # 过滤数据集
    if scene_filter:
        dataset = [d for d in dataset if d.get("场景") == scene_filter]

    # 过滤已完成的 case
    remaining = [d for d in dataset if d["序号"] not in completed_ids]
    print(f"剩余待测 case 数量：{len(remaining)}（共 {len(dataset)} 个）")

    if not remaining:
        print("所有 case 已完成，跳过。")
        return

    # 批量运行
    results = []
    success_count = 0
    failed_count = 0
    failed_cases = []
    scores = []

    for i, case_data in enumerate(remaining, 1):
        case_id = case_data["序号"]
        print(f"\n[{i}/{len(remaining)}] 正在测试：{case_id}")

        try:
            test_case = dict_to_test_case(case_data)
            result = runner.run(test_case)

            # 生成报告
            report_path = report_gen.generate_report(result, dataset_name)
            print(f"  -> 报告已保存：{report_path}")
            print(f"  -> 总分：{result.report.get('总分', 0)} / 10")

            results.append({
                "case_id": case_id,
                "status": "success",
                "score": result.report.get("总分", 0)
            })
            scores.append(result.report.get("总分", 0))
            success_count += 1

        except Exception as e:
            print(f"  -> 测试失败：{type(e).__name__}: {e}")
            results.append({
                "case_id": case_id,
                "status": "failed",
                "error": str(e)
            })
            failed_count += 1
            failed_cases.append(case_id)

    # 打印汇总
    avg_score = sum(scores) / len(scores) if scores else 0
    print(f"\n{'='*50}")
    print(f"基准测试完成")
    print(f"总数：{len(remaining)} | 成功：{success_count} | 失败：{failed_count}")
    print(f"平均分：{avg_score:.2f} / 10")

    # 计算分数分布
    score_dist = {
        "满分(9-10)": sum(1 for s in scores if s >= 9),
        "及格(6-8)": sum(1 for s in scores if 6 <= s < 9),
        "不及格(0-5)": sum(1 for s in scores if s < 6)
    }
    print(f"分数分布：{score_dist}")

    if failed_cases:
        print(f"失败 case：{failed_cases}")

    # 保存 summary.json
    summary = {
        "dataset_id": dataset_name,
        "run_time": datetime.now().isoformat(),
        "total": len(remaining),
        "success": success_count,
        "failed": failed_count,
        "avg_score": round(avg_score, 2),
        "score_distribution": score_dist,
        "failed_cases": failed_cases
    }

    output_dir = Path(config.output_dir) / dataset_name
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n汇总已保存：{summary_path}")


def main():
    parser = argparse.ArgumentParser(description="X7 Agent Benchmark Framework")
    parser.add_argument(
        "--dataset",
        type=str,
        default=None,
        help="数据集 JSON 文件路径（默认使用 config 里的 default_dataset_path）"
    )
    parser.add_argument(
        "--scene",
        type=str,
        default=None,
        help="只跑指定场景名的 case"
    )
    args = parser.parse_args()

    config = Config()
    dataset_path = args.dataset or config.default_dataset_path

    if not os.path.exists(dataset_path):
        print(f"错误：数据集文件不存在：{dataset_path}")
        sys.exit(1)

    run_benchmark(dataset_path, args.scene)


if __name__ == "__main__":
    main()