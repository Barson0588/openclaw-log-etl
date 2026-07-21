"""
数据采集与清洗模块 (data_pipeline.py)
======================================
负责从 OpenClaw 接口（或本地 mock 数据）拉取任务执行日志，
对原始数据进行清洗、标准化，并存储为 CSV 文件。

设计思路:
  - DataPipeline 类封装 拉取→清洗→保存 三步流程
  - 清洗逻辑分层：必填校验 → 类型转换 → 异常值过滤 → 去重
  - 使用 logging 在关键节点打 log，方便排查管线问题
"""

import json
import logging
import os
from datetime import datetime

import pandas as pd
import requests

logger = logging.getLogger(__name__)


class DataPipeline:
    """OpenClaw 日志采集与清洗管线。

    使用方式::

        pipeline = DataPipeline(mock_data_path="mock_data.json")
        df = pipeline.fetch_logs()          # Step 1: 拉取原始数据
        df = pipeline.clean(df)             # Step 2: 清洗
        csv_path = pipeline.save(df)        # Step 3: 保存为 CSV
    """

    # ---- 配置: 合法字段及期望类型 ----
    REQUIRED_COLUMNS = [
        "task_id", "timestamp", "duration_ms",
        "tool_calls_count", "tokens_used", "status",
        "error_type", "tool_name",
    ]

    def __init__(self, api_url=None, mock_data_path="mock_data.json", output_dir="data"):
        """
        Args:
            api_url: OpenClaw API 地址，为 None 时走 mock 数据
            mock_data_path: 本地 mock JSON 文件路径
            output_dir: 清洗后 CSV 输出目录
        """
        self.api_url = api_url
        self.mock_data_path = mock_data_path
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    # =================================================================
    #  Step 1: 数据拉取
    # =================================================================

    def fetch_logs(self, use_mock=True):
        """从 API 拉取或从本地 mock 文件加载日志数据。

        【原理讲解】
        这里做了一个 fallback 设计:
          - use_mock=True 时直接读本地 JSON，方便开发和演示
          - use_mock=False 时走 HTTP 请求对接真实 API
        两种方式返回的都是 list[dict]，后续统一转为 DataFrame 处理。

        Args:
            use_mock: True 加载本地 mock；False 请求 api_url

        Returns:
            pd.DataFrame: 原始日志数据（未清洗）
        """
        if use_mock or not self.api_url:
            logger.info("使用本地 Mock 数据: %s", self.mock_data_path)
            with open(self.mock_data_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        else:
            logger.info("从 API 拉取数据: %s", self.api_url)
            resp = requests.get(self.api_url, timeout=30)
            resp.raise_for_status()
            raw_data = resp.json()

        df = pd.DataFrame(raw_data)
        logger.info("拉取完成，共 %d 条原始记录，%d 个字段", len(df), len(df.columns))
        return df

    def fetch_from_openclaw(self, sessions_dir=None, limit=None):
        """从本地 OpenClaw 环境的 trajectory 文件加载真实日志。

        使用 openclaw_adapter 模块读取 ~/.openclaw/agents/main/sessions/
        下的 trajectory JSONL 文件，转换为标准 DataFrame 格式。

        Args:
            sessions_dir: trajectory 文件目录路径，默认自动检测
            limit: 最多读取的文件数，None 为全部

        Returns:
            pd.DataFrame: 真实 OpenClaw 日志数据（未清洗）
        """
        from openclaw_adapter import OpenClawAdapter

        adapter = OpenClawAdapter(sessions_dir=sessions_dir)
        df = adapter.load_trajectories(limit=limit)
        logger.info("真实数据拉取完成，共 %d 条记录", len(df))
        return df

    # =================================================================
    #  Step 2: 数据清洗
    # =================================================================

    def clean(self, df):
        """对原始 DataFrame 执行多步清洗。

        【清洗策略说明】
        清洗遵循"先过滤后转换"的原则，分 4 个阶段:
          1. 结构校验   — 检查必填列是否存在
          2. 必填过滤   — 剔除 task_id 为空或异常的脏数据
          3. 类型转换   — timestamp 转 datetime, 数值列转 int
          4. 异常值过滤 — 剔除 duration/tokens 为负等不合理数据
          5. 补全与去重 — 填充缺失的 error_type, 去掉完全重复行

        每一步都会 log 过滤掉的记录数, 方便追踪数据质量变化。

        Args:
            df: fetch_logs() 返回的原始 DataFrame

        Returns:
            pd.DataFrame: 清洗后的干净数据
        """
        initial_count = len(df)
        logger.info("开始清洗，初始记录数: %d", initial_count)

        # --- 阶段 1: 检查是否缺少必填列 ---
        missing_cols = set(self.REQUIRED_COLUMNS) - set(df.columns)
        if missing_cols:
            raise ValueError(f"缺少必填字段: {missing_cols}")

        # --- 阶段 2: 过滤 task_id 为空、非字符串、或空字符串的记录 ---
        # pandas 的 .notna() 过滤 NaN/None;
        # .astype(str).str.strip() != '' 过滤纯空格或空字符串
        mask_valid_id = (
            df["task_id"].notna()
            & (df["task_id"].astype(str).str.strip() != "")
        )
        removed_id = (~mask_valid_id).sum()
        df = df[mask_valid_id].copy()
        if removed_id:
            logger.warning("过滤 task_id 异常记录: %d 条", removed_id)

        # --- 阶段 3: 类型转换 ---
        # timestamp → datetime, 转换失败变为 NaT 然后剔除
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        mask_valid_ts = df["timestamp"].notna()
        removed_ts = (~mask_valid_ts).sum()
        df = df[mask_valid_ts]
        if removed_ts:
            logger.warning("过滤 timestamp 解析失败记录: %d 条", removed_ts)

        # 数值列转为数字，无法转换的变为 NaN 后剔除
        for col in ["duration_ms", "tool_calls_count", "tokens_used"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # status 统一为小写字符串
        df["status"] = df["status"].astype(str).str.lower().str.strip()

        # --- 阶段 4: 异常值过滤 ---
        # duration_ms 和 tokens_used 不能为负数
        before = len(df)
        df = df[
            (df["duration_ms"] >= 0)
            & (df["tool_calls_count"] >= 0)
            & (df["tokens_used"] >= 0)
        ]
        removed_neg = before - len(df)
        if removed_neg:
            logger.warning("过滤数值为负记录: %d 条", removed_neg)

        # status 只能是 success 或 failed
        before = len(df)
        df = df[df["status"].isin(["success", "failed"])]
        removed_status = before - len(df)
        if removed_status:
            logger.warning("过滤异常 status 值记录: %d 条", removed_status)

        # --- 阶段 5: 补全与去重 ---
        # error_type: 成功任务填 ""，失败但缺失的填 "unknown"
        df["error_type"] = df["error_type"].fillna("")
        # 成功的任务不应有 error_type
        mask_success = df["status"] == "success"
        df.loc[mask_success, "error_type"] = ""
        # 失败但 error_type 为空 → 标记为 unknown
        mask_failed_no_error = (df["status"] == "failed") & (df["error_type"] == "")
        df.loc[mask_failed_no_error, "error_type"] = "unknown"

        # tool_name 缺失填 "unknown"
        df["tool_name"] = df["tool_name"].fillna("unknown").astype(str)

        # 剔除完全重复行
        before = len(df)
        df = df.drop_duplicates()
        removed_dup = before - len(df)
        if removed_dup:
            logger.warning("过滤完全重复行: %d 条", removed_dup)

        # 按 timestamp 排序以方便后续时序分析
        df = df.sort_values("timestamp").reset_index(drop=True)

        final_count = len(df)
        logger.info(
            "清洗完成: %d → %d 条 (剔除 %d 条, 保留率 %.1f%%)",
            initial_count, final_count,
            initial_count - final_count,
            final_count / max(initial_count, 1) * 100,
        )
        return df

    # =================================================================
    #  Step 3: 保存为 CSV
    # =================================================================

    def save(self, df, filename=None):
        """将清洗后的 DataFrame 保存为 CSV 文件。

        Args:
            df: clean() 返回的 DataFrame
            filename: 输出文件名，默认使用日期命名

        Returns:
            str: 保存的 CSV 文件路径
        """
        if filename is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
            filename = f"cleaned_logs_{date_str}.csv"

        path = os.path.join(self.output_dir, filename)
        df.to_csv(path, index=False, encoding="utf-8-sig")
        logger.info("清洗数据已保存: %s (%d 条记录)", path, len(df))
        return path
