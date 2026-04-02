from pathlib import Path

ROOT = Path('/mnt/data/frontendrepo')
API_TS = (ROOT / 'src/services/api.ts').read_text(encoding='utf-8')
TYPES_TS = (ROOT / 'src/types/api.ts').read_text(encoding='utf-8')
PRICECHECK_TSX = (ROOT / 'src/components/tabs/PriceCheckTab.tsx').read_text(encoding='utf-8')
ANALYTICS_TSX = (ROOT / 'src/components/tabs/AnalyticsTab.tsx').read_text(encoding='utf-8')


def test_pricecheck_tab_uses_ops_pricecheck_and_shows_comparables() -> None:
    assert 'api.priceCheck({ itemText: text })' in PRICECHECK_TSX
    assert 'api.mlPredictOne({ clipboard: text })' not in PRICECHECK_TSX
    assert 'Recent Comparables' in PRICECHECK_TSX
    assert 'League' in PRICECHECK_TSX
    assert 'Added On' in PRICECHECK_TSX


def test_api_exports_search_history_and_outlier_helpers() -> None:
    assert 'export async function getAnalyticsSearchSuggestions' in API_TS
    assert '/api/v1/ops/analytics/search-suggestions' in API_TS
    assert 'export async function getAnalyticsSearchHistory' in API_TS
    assert '/api/v1/ops/analytics/search-history' in API_TS
    assert 'export async function getAnalyticsPricingOutliers' in API_TS
    assert '/api/v1/ops/analytics/pricing-outliers' in API_TS


def test_types_define_new_search_and_outlier_shapes() -> None:
    assert 'export interface SearchSuggestion' in TYPES_TS
    assert 'export interface SearchHistoryResponse' in TYPES_TS
    assert 'export interface PricingOutlierRow' in TYPES_TS
    assert 'league?: string' in TYPES_TS
    assert 'addedOn?: string | null' in TYPES_TS


def test_analytics_tab_adds_search_and_outlier_panels() -> None:
    assert 'analytics-tab-search' in ANALYTICS_TSX
    assert 'analytics-tab-outliers' in ANALYTICS_TSX
    assert '<SearchHistoryPanel />' in ANALYTICS_TSX
    assert '<PricingOutliersPanel />' in ANALYTICS_TSX
    assert 'data-testid="search-history-results"' in ANALYTICS_TSX
    assert 'data-testid="pricing-outliers-results"' in ANALYTICS_TSX
    assert 'Item Name' in ANALYTICS_TSX
    assert 'Listed Price' in ANALYTICS_TSX
    assert '10 percentile' in ANALYTICS_TSX
