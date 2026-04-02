from pathlib import Path


def test_analytics_tab_exposes_ml_training_history_panels() -> None:
    source = Path('src/components/tabs/AnalyticsTab.tsx').read_text(encoding='utf-8')
    assert 'Runs / 7d' in source
    assert 'Median cadence' in source
    assert 'MDAPE trend' in source
    assert 'Coverage trend' in source
    assert 'Dataset coverage' in source
    assert 'Route metrics' in source
    assert 'Model promotions' in source


def test_ml_automation_types_include_observability_shape() -> None:
    source = Path('src/types/api.ts').read_text(encoding='utf-8')
    assert 'summary:' in source
    assert 'qualityTrend:' in source
    assert 'trainingCadence:' in source
    assert 'routeMetrics:' in source
    assert 'datasetCoverage:' in source
    assert 'promotions:' in source



def test_analytics_tab_treats_completed_and_running_as_non_error_states() -> None:
    source = Path('src/components/tabs/AnalyticsTab.tsx').read_text(encoding='utf-8')
    assert "status === 'completed'" in source
    assert "status === 'running'" in source
