from types import SimpleNamespace

from presentation.rendering.metrics import shape_metrics


def chart_shape(values, categories, chart_type=57):
    series = SimpleNamespace(Name="Sales", ChartType=chart_type, Values=values, XValues=categories, Points=lambda index=None: SimpleNamespace(Count=0))
    collection = SimpleNamespace(Count=1, Item=lambda index: series)
    chart = SimpleNamespace(ChartType=chart_type, SeriesCollection=lambda: collection)
    return SimpleNamespace(Id=7, Name="Chart 7", Left=1, Top=2, Width=300, Height=200, HasTextFrame=False, HasTable=False, HasChart=True, Chart=chart)


def test_empty_chart_cells_are_kept_as_gaps_instead_of_crashing():
    # Real decks often have blank chart cells; PowerPoint returns them as None.
    entry = shape_metrics(chart_shape((4.0, None, 2.5, None), ("2023", "2024", None, "2026")))
    series = entry["chart_series"][0]
    assert series["values"] == [4.0, None, 2.5, None]
    assert series["categories"] == ["2023", "2024", "", "2026"]


def test_scatter_x_values_keep_gaps():
    entry = shape_metrics(chart_shape((1.0, 2.0), (None, 3.0), chart_type=-4169))
    assert entry["chart_series"][0]["x_values"] == [None, 3.0]
