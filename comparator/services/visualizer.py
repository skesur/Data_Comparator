"""
Builds Plotly figures from a DataFrame and returns them as JSON
(via plotly.io.to_json) so the frontend can render them directly
with Plotly.js — no server-side image rendering needed.
"""

import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio


class VisualizationError(ValueError):
    pass


DARK_TEMPLATE = "plotly_dark"


def _apply_theme(fig):
    """Match the cyberpunk cyan/purple aesthetic used across the frontend."""
    fig.update_layout(
        template=DARK_TEMPLATE,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#E6F9FF"),
        colorway=["#00F7FF", "#BF5AF2", "#FF5AF2", "#5AFFBF", "#FFD15A"],
        margin=dict(l=40, r=20, t=50, b=40),
    )
    return fig


def make_histogram(df, column, bins=30):
    if column not in df.columns:
        raise VisualizationError(f"Column '{column}' not found.")
    fig = px.histogram(
        df, x=column, nbins=bins, title=f"Distribution of {column}",
        color_discrete_sequence=["#00F7FF"],
    )
    return pio.to_json(_apply_theme(fig))


def make_scatter(df, x_column, y_column, color_column=None):
    for col in [x_column, y_column]:
        if col not in df.columns:
            raise VisualizationError(f"Column '{col}' not found.")
    fig = px.scatter(
        df, x=x_column, y=y_column,
        color=color_column if color_column in df.columns else None,
        title=f"{y_column} vs {x_column}",
    )
    return pio.to_json(_apply_theme(fig))


def make_line(df, x_column, y_column):
    for col in [x_column, y_column]:
        if col not in df.columns:
            raise VisualizationError(f"Column '{col}' not found.")
    fig = px.line(df, x=x_column, y=y_column, title=f"{y_column} over {x_column}")
    return pio.to_json(_apply_theme(fig))


def make_bar(df, x_column, y_column=None, agg="count"):
    if x_column not in df.columns:
        raise VisualizationError(f"Column '{x_column}' not found.")

    if y_column and agg != "count":
        if y_column not in df.columns:
            raise VisualizationError(f"Column '{y_column}' not found.")
        grouped = df.groupby(x_column)[y_column].agg(agg).reset_index()
        fig = px.bar(
            grouped, x=x_column, y=y_column, title=f"{agg} of {y_column} by {x_column}",
            color_discrete_sequence=["#00F7FF"],
        )
    else:
        counts = df[x_column].value_counts().reset_index()
        counts.columns = [x_column, "count"]
        fig = px.bar(
            counts, x=x_column, y="count", title=f"Count by {x_column}",
            color_discrete_sequence=["#00F7FF"],
        )

    return pio.to_json(_apply_theme(fig))


def make_box(df, column, group_by=None):
    if column not in df.columns:
        raise VisualizationError(f"Column '{column}' not found.")
    fig = px.box(
        df, y=column,
        x=group_by if group_by in df.columns else None,
        title=f"Spread of {column}",
        color_discrete_sequence=["#00F7FF"],
    )
    return pio.to_json(_apply_theme(fig))


def make_correlation_heatmap(df, columns=None):
    numeric_df = df.select_dtypes(include="number")
    if columns:
        numeric_df = numeric_df[[c for c in columns if c in numeric_df.columns]]

    if numeric_df.shape[1] < 2:
        raise VisualizationError("Need at least two numeric columns for a correlation heatmap.")

    corr = numeric_df.corr()
    fig = go.Figure(
        data=go.Heatmap(
            z=corr.values,
            x=corr.columns.tolist(),
            y=corr.columns.tolist(),
            colorscale=[[0, "#BF5AF2"], [0.5, "#111119"], [1, "#00F7FF"]],
            zmin=-1, zmax=1,
        )
    )
    fig.update_layout(title="Correlation Heatmap")
    return pio.to_json(_apply_theme(fig))


CHART_BUILDERS = {
    "histogram": make_histogram,
    "scatter": make_scatter,
    "line": make_line,
    "bar": make_bar,
    "box": make_box,
    "correlation": make_correlation_heatmap,
}
