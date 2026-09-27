# MAIRE Examples

This folder contains runnable examples that demonstrate how to use the MAIRE
evaluation framework. Each example is self-contained and can be run independently.

## Prerequisites

Activate the virtual environment:
```bash
source /home/shouvik/Amartya/work_2026/Evaluation_Framework/agent_evaluation_env/bin/activate
```

## Examples

### 01_mock_state_collector
Tests the Samsung Notes state collector using the MockXRClawDeviceManager.
No physical device required.

```bash
python examples/01_mock_state_collector/run_example.py
```

### 02_deterministic_judge
Demonstrates the DeterministicJudge evaluating battery and volume queries
without an LLM, by comparing TTS responses against grounding device state.

```bash
python examples/02_deterministic_judge/run_example.py
```

### 03_full_pipeline_mock (coming soon)
End-to-end pipeline test using all mock services (mock transcription, mock
judge, mock device manager). Simulates a complete evaluation run.

### 04_real_device_integration (coming soon)
Integration with real services (transcription server, VLM judge, TTS).
Requires physical device and running services.

## scratch_pad/

The `scratch_pad/` folder (gitignored) is used for:
- `screenshots/` — Device screenshots captured during integration testing
- `logs/` — Log files from test runs
- `reports/` — Generated evaluation reports

Use the image analysis tool to verify screenshots from integration tests.
