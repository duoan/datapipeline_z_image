# Metrics Reporter - HTML Visualization & HuggingFace Publishing

Generate comprehensive HTML visualization reports from pipeline metrics data.

## Features

- 📊 **Interactive Charts**: Plotly-based interactive visualizations
- 📈 **Three-Level Metrics**: Run, Stage, and Operator level insights
- 🎨 **Beautiful UI**: Modern, responsive design
- 🚀 **HuggingFace Integration**: Auto-publish to HuggingFace Spaces
- 🔄 **Post-Processing**: Automatic report generation after pipeline execution

## Quick Start

### 1. Enable Report Generation in Config

```yaml
executor:
  metrics:
    enabled: true
    output_path: "./metrics"
    write_on_completion: true
    generate_report: true  # Enable HTML report generation
```

### 2. Run Your Pipeline

```bash
mdf run -c configs/example_with_report.yaml
```

The HTML report will be automatically generated at `./metrics/metrics_report.html`.

### 3. View the Report

```bash
# Open in browser
open metrics/metrics_report.html  # macOS
xdg-open metrics/metrics_report.html  # Linux
start metrics/metrics_report.html  # Windows
```

## Standalone Report Generation

Generate reports from existing metrics Parquet files:

```bash
# Generate report locally
python scripts/generate_metrics_report.py \
    --metrics-path ./metrics \
    --output ./my_report.html
```

## Publishing to HuggingFace Spaces

### Method 1: Automatic Publishing (Config)

Add HuggingFace settings to your config:

```yaml
executor:
  metrics:
    enabled: true
    generate_report: true
    huggingface_repo: "username/metrics-dashboard"  # Your HF Space repo
    huggingface_token: null  # Uses HF_TOKEN env var
```

Set your HuggingFace token:

```bash
export HF_TOKEN="your_hf_token_here"
```

Run the pipeline:

```bash
mdf run -c configs/example_with_report.yaml
```

The report will be automatically published to `https://huggingface.co/spaces/username/metrics-dashboard`.

### Method 2: Manual Publishing (CLI)

```bash
# Set HuggingFace token
export HF_TOKEN="your_hf_token_here"

# Generate and publish report
python scripts/generate_metrics_report.py \
    --metrics-path ./metrics \
    --huggingface-repo username/metrics-dashboard
```

## Report Contents

### 1. Run Summary

High-level metrics for the entire pipeline run:
- Total Input/Output Records
- Pass Rate
- Duration
- Throughput
- Number of Stages
- Total Errors

### 2. Stage Performance

Comparison of throughput across all stages:
- Bar chart showing throughput per stage
- Identifies bottleneck stages
- Stage-level pass rates

### 3. Operator Performance

Detailed operator-level analysis:
- **Throughput Chart**: Records/second per operator
- **Latency Chart**: Average latency per operator
- **Input vs Output**: Record counts before/after filtering
- **Pass Rate**: Percentage of records passing through

### 4. Latency Distribution

Box plots showing latency percentiles:
- Min, P50, P95, P99, Max latencies
- Helps identify performance outliers
- Per-operator comparison

## Dependencies

### Required

- `pandas`: Data manipulation
- `pyarrow`: Parquet file reading

### Optional (for visualization)

- `plotly`: Interactive charts (recommended)
  ```bash
  pip install plotly
  ```

### Optional (for HuggingFace publishing)

- `huggingface_hub`: Space publishing
  ```bash
  pip install huggingface_hub
  ```

If Plotly is not installed, a simple HTML table report will be generated instead.

## Programmatic Usage

```python
from mega_data_factory.framework.metrics import MetricsReporter

# Create reporter
reporter = MetricsReporter(metrics_path="./metrics")

# Generate HTML report
report_path = reporter.generate_html_report(output_path="report.html")
print(f"Report generated: {report_path}")

# Optionally publish to HuggingFace
space_url = reporter.publish_to_huggingface(
    report_path=report_path,
    repo_id="username/space-name",
    token="your_hf_token",  # or set HF_TOKEN env var
)
print(f"Published to: {space_url}")
```

## HuggingFace Space Setup

1. **Create a Space** on HuggingFace:
   - Go to https://huggingface.co/new-space
   - Choose "Static" as the SDK
   - Name it (e.g., "metrics-dashboard")

2. **Get Your Token**:
   - Go to https://huggingface.co/settings/tokens
   - Create a new token with "write" permission
   - Copy the token

3. **Publish Your Report**:
   ```bash
   export HF_TOKEN="your_token_here"
   python scripts/generate_metrics_report.py \
       --metrics-path ./metrics \
       --huggingface-repo username/metrics-dashboard
   ```

4. **View Your Dashboard**:
   - Visit `https://huggingface.co/spaces/username/metrics-dashboard`
   - The report updates automatically on each run

## Customization

### Custom Report Template

Extend the `MetricsReporter` class to customize report generation:

```python
from mega_data_factory.framework.metrics import MetricsReporter

class CustomReporter(MetricsReporter):
    def _generate_html(self, run_df, stage_df, operator_df):
        # Your custom HTML generation logic
        return custom_html
```

### Custom Charts

Add your own charts by extending the reporter methods:

```python
def _generate_custom_chart(self, df):
    import plotly.graph_objects as go

    fig = go.Figure(...)
    return fig.to_html()
```

## Troubleshooting

### Plotly Not Installed

**Error**: `ModuleNotFoundError: No module named 'plotly'`

**Solution**: Install plotly for interactive charts:
```bash
pip install plotly
```

Or use the simple HTML table fallback (automatic).

### HuggingFace Authentication Failed

**Error**: `RepositoryNotFoundError` or authentication errors

**Solutions**:
1. Check your token is valid: https://huggingface.co/settings/tokens
2. Ensure `HF_TOKEN` environment variable is set
3. Verify the Space exists and you have write access
4. Try logging in first: `huggingface-cli login`

### Empty Charts

**Error**: Charts appear but have no data

**Solution**: Ensure metrics Parquet files exist:
```bash
ls -la metrics/runs/
ls -la metrics/stages/
ls -la metrics/operators/
```

If directories are empty, ensure `metrics.enabled: true` in config.

## Examples

See `configs/example_with_report.yaml` for a complete configuration example.

## Integration with CI/CD

Automatically publish metrics after each run:

```yaml
# .github/workflows/metrics.yml
name: Generate Metrics Report

on:
  workflow_run:
    workflows: ["Data Pipeline"]
    types: [completed]

jobs:
  report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Download metrics artifacts
        # ... download metrics from previous run

      - name: Generate and publish report
        env:
          HF_TOKEN: ${{ secrets.HF_TOKEN }}
        run: |
          python scripts/generate_metrics_report.py \
            --metrics-path ./metrics \
            --huggingface-repo ${{ github.repository_owner }}/metrics
```

## Best Practices

1. **Regular Publishing**: Publish reports after each production run to track trends
2. **Version Control**: Keep historical reports for comparison
3. **Space Organization**: Use separate Spaces for dev/staging/prod environments
4. **Token Security**: Never commit tokens, use environment variables
5. **Report Retention**: Archive old reports to manage Space storage

## Future Enhancements

Potential future features:
- Time-series trend analysis across multiple runs
- Alerting based on metric thresholds
- Comparison views between runs
- Export to other formats (PDF, markdown)
- Integration with observability tools (Grafana, Datadog)
