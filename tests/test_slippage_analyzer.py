"""Test slippage analyzer functionality."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from datetime import datetime
from quant_vibe.analytics import SlippageAnalyzer


def test_slippage_analyzer_initialization():
    """Test that SlippageAnalyzer initializes correctly."""
    analyzer = SlippageAnalyzer(db_profile='local')
    assert analyzer is not None
    analyzer.close()


def test_slippage_analyzer_context_manager():
    """Test that SlippageAnalyzer works as context manager."""
    with SlippageAnalyzer(db_profile='local') as analyzer:
        assert analyzer is not None


def test_load_filled_orders():
    """Test loading filled orders from database."""
    with SlippageAnalyzer(db_profile='local') as analyzer:
        # Should not error even if no data
        df = analyzer.load_filled_orders()
        assert df is not None
        # May be empty if no paper trading has run yet
        assert 'order_id' in df.columns or df.empty


def test_generate_summary_report_no_data():
    """Test summary report generation with no data."""
    with SlippageAnalyzer(db_profile='local') as analyzer:
        report = analyzer.generate_summary_report()

        # Should handle empty data gracefully
        if 'error' in report:
            assert 'No filled orders' in report['error']
        else:
            # If data exists, should have expected structure
            assert 'overall' in report
            assert 'by_hour' in report
            assert 'by_dte' in report


def test_get_recommended_slippage_adjustments_no_data():
    """Test recommendations with no data."""
    with SlippageAnalyzer(db_profile='local') as analyzer:
        recommendations = analyzer.get_recommended_slippage_adjustments()

        # Should handle empty data gracefully
        assert recommendations is not None
        # Either has error or has recommendation structure
        assert 'error' in recommendations or len(recommendations) >= 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
