"""
Metrics Reporter: Generate comprehensive HTML visualization reports from metrics data.

This module reads Parquet metrics files and generates interactive HTML reports
with charts and statistics.
"""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd


class MetricsReporter:
    """Generate HTML reports from metrics data."""

    def __init__(self, metrics_path: str):
        """Initialize reporter.

        Args:
            metrics_path: Path to metrics directory containing Parquet files
        """
        self.metrics_path = Path(metrics_path)
        self.runs_path = self.metrics_path / "runs"
        self.stages_path = self.metrics_path / "stages"
        self.operators_path = self.metrics_path / "operators"

    def load_metrics(self) -> tuple[pd.DataFrame | None, pd.DataFrame | None, pd.DataFrame | None]:
        """Load all metrics from Parquet files.

        Returns:
            Tuple of (run_df, stage_df, operator_df)
        """
        # Load run metrics
        run_df = None
        if self.runs_path.exists():
            run_files = list(self.runs_path.glob("*.parquet"))
            if run_files:
                run_df = pd.concat([pd.read_parquet(f) for f in run_files], ignore_index=True)

        # Load stage metrics
        stage_df = None
        if self.stages_path.exists():
            stage_files = list(self.stages_path.glob("*.parquet"))
            if stage_files:
                stage_df = pd.concat([pd.read_parquet(f) for f in stage_files], ignore_index=True)

        # Load operator metrics
        operator_df = None
        if self.operators_path.exists():
            operator_files = list(self.operators_path.glob("*.parquet"))
            if operator_files:
                operator_df = pd.concat([pd.read_parquet(f) for f in operator_files], ignore_index=True)

        return run_df, stage_df, operator_df

    def generate_html_report(self, output_path: str = "metrics_report.html") -> str:
        """Generate comprehensive HTML report with interactive charts.

        Args:
            output_path: Path to save HTML report

        Returns:
            Path to generated report
        """
        run_df, stage_df, operator_df = self.load_metrics()

        # Generate HTML report
        html = self._generate_html(run_df, stage_df, operator_df)

        # Write to file
        output_path = Path(output_path)
        output_path.write_text(html, encoding="utf-8")

        return str(output_path)

    def _generate_html(
        self,
        run_df: pd.DataFrame | None,
        stage_df: pd.DataFrame | None,
        operator_df: pd.DataFrame | None,
    ) -> str:
        """Generate HTML report content.

        Args:
            run_df: Run metrics DataFrame
            stage_df: Stage metrics DataFrame
            operator_df: Operator metrics DataFrame

        Returns:
            HTML content as string
        """
        # Import plotly here to avoid dependency if not generating reports
        try:
            import plotly.graph_objects as go  # noqa: F401
            from plotly.subplots import make_subplots  # noqa: F401
        except ImportError:
            return self._generate_simple_html(run_df, stage_df, operator_df)

        # Generate charts
        charts_html = []

        # Run summary
        if run_df is not None and len(run_df) > 0:
            run_summary = self._generate_run_summary(run_df)
            charts_html.append(f"<h2>Run Summary</h2>\n{run_summary}")

        # Stage comparison
        if stage_df is not None and len(stage_df) > 0:
            stage_chart = self._generate_stage_chart(stage_df)
            charts_html.append(f"<h2>Stage Performance</h2>\n{stage_chart}")

        # Operator details
        if operator_df is not None and len(operator_df) > 0:
            operator_chart = self._generate_operator_chart(operator_df)
            charts_html.append(f"<h2>Operator Performance</h2>\n{operator_chart}")

            # Latency distribution
            latency_chart = self._generate_latency_chart(operator_df)
            charts_html.append(f"<h2>Latency Distribution</h2>\n{latency_chart}")

        # Combine into full HTML
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mega Data Factory - Metrics Report</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ecf0f1;
        }}
        .metric-card {{
            display: inline-block;
            background: #ecf0f1;
            padding: 20px;
            margin: 10px;
            border-radius: 4px;
            min-width: 200px;
        }}
        .metric-label {{
            font-size: 14px;
            color: #7f8c8d;
            margin-bottom: 5px;
        }}
        .metric-value {{
            font-size: 28px;
            font-weight: bold;
            color: #2c3e50;
        }}
        .metric-unit {{
            font-size: 14px;
            color: #95a5a6;
        }}
        .chart-container {{
            margin: 20px 0;
        }}
        .timestamp {{
            color: #95a5a6;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Mega Data Factory - Metrics Report</h1>
        <p class="timestamp">Generated: {datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")}</p>

        {''.join(charts_html)}

        <hr style="margin-top: 60px; border: none; border-top: 1px solid #ecf0f1;">
        <p style="text-align: center; color: #95a5a6; font-size: 14px;">
            Generated by Mega Data Factory Metrics Reporter
        </p>
    </div>
</body>
</html>"""

        return html

    def _generate_run_summary(self, run_df: pd.DataFrame) -> str:
        """Generate run summary HTML."""
        latest_run = run_df.iloc[-1]

        cards = []
        metrics = [
            ("Total Input Records", latest_run["total_input_records"], "records"),
            ("Total Output Records", latest_run["total_output_records"], "records"),
            ("Pass Rate", f"{latest_run['overall_pass_rate']:.2f}", "%"),
            ("Duration", f"{latest_run['duration']:.2f}", "seconds"),
            ("Throughput", f"{latest_run['avg_throughput']:.2f}", "records/s"),
            ("Number of Stages", latest_run["num_stages"], "stages"),
            ("Total Errors", latest_run["total_errors"], "errors"),
        ]

        for label, value, unit in metrics:
            cards.append(f"""
            <div class="metric-card">
                <div class="metric-label">{label}</div>
                <div class="metric-value">{value} <span class="metric-unit">{unit}</span></div>
            </div>
            """)

        return "".join(cards)

    def _generate_stage_chart(self, stage_df: pd.DataFrame) -> str:
        """Generate stage comparison chart."""
        import plotly.graph_objects as go

        fig = go.Figure()

        # Throughput by stage
        fig.add_trace(
            go.Bar(
                x=stage_df["stage_name"],
                y=stage_df["avg_throughput"],
                name="Throughput (records/s)",
                marker_color="#3498db",
            )
        )

        fig.update_layout(
            title="Stage Throughput Comparison",
            xaxis_title="Stage",
            yaxis_title="Throughput (records/s)",
            template="plotly_white",
            height=400,
        )

        return f'<div class="chart-container" id="stage-chart"></div>\n<script>Plotly.newPlot("stage-chart", {fig.to_json()});</script>'

    def _generate_operator_chart(self, operator_df: pd.DataFrame) -> str:
        """Generate operator performance chart."""
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        # Group by operator
        operator_summary = (
            operator_df.groupby(["stage_name", "operator_name"])
            .agg(
                {
                    "input_records": "sum",
                    "output_records": "sum",
                    "avg_latency": "mean",
                    "throughput": "mean",
                }
            )
            .reset_index()
        )

        # Create subplots
        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=("Throughput", "Average Latency", "Input vs Output Records", "Pass Rate"),
            specs=[[{"type": "bar"}, {"type": "bar"}], [{"type": "bar"}, {"type": "bar"}]],
        )

        # Throughput
        fig.add_trace(
            go.Bar(
                x=operator_summary["operator_name"],
                y=operator_summary["throughput"],
                name="Throughput",
                marker_color="#3498db",
            ),
            row=1,
            col=1,
        )

        # Latency
        fig.add_trace(
            go.Bar(
                x=operator_summary["operator_name"],
                y=operator_summary["avg_latency"],
                name="Avg Latency",
                marker_color="#e74c3c",
            ),
            row=1,
            col=2,
        )

        # Input vs Output
        fig.add_trace(
            go.Bar(x=operator_summary["operator_name"], y=operator_summary["input_records"], name="Input", marker_color="#2ecc71"),
            row=2,
            col=1,
        )
        fig.add_trace(
            go.Bar(x=operator_summary["operator_name"], y=operator_summary["output_records"], name="Output", marker_color="#f39c12"),
            row=2,
            col=1,
        )

        # Pass Rate
        operator_summary["pass_rate"] = (
            100.0 * operator_summary["output_records"] / operator_summary["input_records"]
        ).fillna(0)
        fig.add_trace(
            go.Bar(
                x=operator_summary["operator_name"],
                y=operator_summary["pass_rate"],
                name="Pass Rate",
                marker_color="#9b59b6",
            ),
            row=2,
            col=2,
        )

        fig.update_xaxes(title_text="Operator", row=1, col=1)
        fig.update_xaxes(title_text="Operator", row=1, col=2)
        fig.update_xaxes(title_text="Operator", row=2, col=1)
        fig.update_xaxes(title_text="Operator", row=2, col=2)

        fig.update_yaxes(title_text="Records/s", row=1, col=1)
        fig.update_yaxes(title_text="Seconds", row=1, col=2)
        fig.update_yaxes(title_text="Records", row=2, col=1)
        fig.update_yaxes(title_text="Percentage", row=2, col=2)

        fig.update_layout(height=800, showlegend=True, template="plotly_white")

        return f'<div class="chart-container" id="operator-chart"></div>\n<script>Plotly.newPlot("operator-chart", {fig.to_json()});</script>'

    def _generate_latency_chart(self, operator_df: pd.DataFrame) -> str:
        """Generate latency distribution chart."""
        import plotly.graph_objects as go

        fig = go.Figure()

        for operator_name in operator_df["operator_name"].unique():
            op_data = operator_df[operator_df["operator_name"] == operator_name]

            # Box plot for latency distribution
            fig.add_trace(
                go.Box(
                    y=[op_data["min_latency"].values[0], op_data["p50_latency"].values[0], op_data["p95_latency"].values[0], op_data["p99_latency"].values[0], op_data["max_latency"].values[0]],
                    name=operator_name,
                    boxmean="sd",
                )
            )

        fig.update_layout(
            title="Latency Distribution by Operator (min, p50, p95, p99, max)",
            yaxis_title="Latency (seconds)",
            template="plotly_white",
            height=500,
        )

        return f'<div class="chart-container" id="latency-chart"></div>\n<script>Plotly.newPlot("latency-chart", {fig.to_json()});</script>'

    def _generate_simple_html(
        self,
        run_df: pd.DataFrame | None,
        stage_df: pd.DataFrame | None,
        operator_df: pd.DataFrame | None,
    ) -> str:
        """Generate simple HTML report without plotly (fallback)."""
        sections = []

        if run_df is not None and len(run_df) > 0:
            sections.append(f"<h2>Run Metrics</h2>\n{run_df.to_html(index=False)}")

        if stage_df is not None and len(stage_df) > 0:
            sections.append(f"<h2>Stage Metrics</h2>\n{stage_df.to_html(index=False)}")

        if operator_df is not None and len(operator_df) > 0:
            sections.append(f"<h2>Operator Metrics</h2>\n{operator_df.to_html(index=False)}")

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Metrics Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #4CAF50; color: white; }}
    </style>
</head>
<body>
    <h1>Metrics Report</h1>
    {''.join(sections)}
</body>
</html>"""

    def publish_to_huggingface(
        self,
        report_path: str,
        repo_id: str,
        token: str | None = None,
        commit_message: str | None = None,
    ) -> str:
        """Publish HTML report to HuggingFace Space.

        Args:
            report_path: Path to HTML report file
            repo_id: HuggingFace repo ID (e.g., "username/space-name")
            token: HuggingFace API token (if None, uses HF_TOKEN env var)
            commit_message: Commit message for the upload

        Returns:
            URL of the published space
        """
        try:
            from huggingface_hub import HfApi, create_repo
        except ImportError as e:
            raise ImportError(
                "huggingface_hub is required for publishing to HuggingFace. "
                "Install it with: pip install huggingface_hub"
            ) from e

        api = HfApi(token=token)

        # Create repo if it doesn't exist (Space type)
        try:
            create_repo(
                repo_id=repo_id,
                repo_type="space",
                space_sdk="static",
                exist_ok=True,
                token=token,
            )
        except Exception as e:
            print(f"Warning: Could not create repo (may already exist): {e}")

        # Upload the report as index.html
        if commit_message is None:
            commit_message = f"Update metrics report - {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')}"

        api.upload_file(
            path_or_fileobj=report_path,
            path_in_repo="index.html",
            repo_id=repo_id,
            repo_type="space",
            commit_message=commit_message,
            token=token,
        )

        space_url = f"https://huggingface.co/spaces/{repo_id}"
        print(f"Report published to: {space_url}")

        return space_url
