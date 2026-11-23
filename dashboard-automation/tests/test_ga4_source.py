from sources.ga4_source import dimension_breakdown, metric_at, page_list

SAMPLE_TOTALS = {"rows": [{"dimensionValues": [], "metricValues": [{"value": "120"}, {"value": "45"}, {"value": "3600"}]}]}


def test_metric_at_reads_by_index():
    assert metric_at(SAMPLE_TOTALS, 0) == 120
    assert metric_at(SAMPLE_TOTALS, 2) == 3600


def test_metric_at_zero_with_no_rows():
    assert metric_at({}, 0) == 0
    assert metric_at({"rows": []}, 0) == 0


def test_dimension_breakdown_maps_rows():
    response = {
        "rows": [
            {"dimensionValues": [{"value": "Organic Search"}], "metricValues": [{"value": "30"}]},
            {"dimensionValues": [{"value": "Direct"}], "metricValues": [{"value": "15"}]},
        ]
    }
    assert dimension_breakdown(response) == {"Organic Search": 30, "Direct": 15}


def test_dimension_breakdown_empty_with_no_rows():
    assert dimension_breakdown({}) == {}


def test_page_list_preserves_order():
    response = {
        "rows": [
            {"dimensionValues": [{"value": "/pricing"}], "metricValues": [{"value": "50"}]},
            {"dimensionValues": [{"value": "/about"}], "metricValues": [{"value": "10"}]},
        ]
    }
    assert page_list(response) == [{"path": "/pricing", "sessions": 50}, {"path": "/about", "sessions": 10}]
