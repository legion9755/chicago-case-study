"""
lib/maps.py — pydeck maps of the incidents (Overview heatmap, Communities page).

`map_style=None` lets Streamlit pick a light or dark Carto basemap from the app theme, so no
map API key is needed. Layer colours are chosen per appearance mode. Map tiles need internet access.
"""
from typing import Any

import pandas as pd
import pydeck as pdk
import streamlit as st

CHICAGO = {"latitude": 41.84, "longitude": -87.68, "zoom": 9.7}


def _colors() -> dict[str, Any]:
    dark = st.context.theme.type == "dark"
    return {
        "arrest": [74, 222, 128, 220] if dark else [21, 128, 61, 210],
        "no_arrest": [91, 155, 213, 210] if dark else [31, 78, 121, 190],
        "outline": [14, 21, 32, 200] if dark else [255, 255, 255, 220],
        "bubble": [91, 155, 213, 120] if dark else [46, 134, 193, 120],
        "ramp": ([[23, 33, 47], [31, 78, 121], [46, 107, 168], [66, 133, 194], [147, 189, 226], [240, 246, 251]]
                 if dark else
                 [[220, 234, 246], [147, 189, 226], [102, 161, 211], [46, 107, 168], [31, 78, 121], [15, 40, 64]]),
    }


def incidents_frame(data: list[dict]) -> pd.DataFrame:
    """API incidents → DataFrame with display columns. Rows without coordinates are kept
    (tables list them) with `has_location` False."""
    df = pd.DataFrame(data)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df["date_label"] = df["date"].dt.strftime("%d %b %Y")
    df["arrest_label"] = df["arrest"].map({True: "Arrest made", False: "No arrest"})
    df["has_location"] = df[["latitude", "longitude"]].notna().all(axis=1)
    return df


def build_deck(layer: str, incidents: pd.DataFrame | None = None, communities: pd.DataFrame | None = None,
               view: dict[str, float] | None = None, heat_radius: int = 18) -> pdk.Deck:
    """A map drawn as `layer`:

    - "Points": one dot per incident (green = arrest made), hover for details
    - "Heatmap": incident density
    - "Communities": one bubble per community area (needs `communities` with crimes + position)

    `view` overrides the Chicago-wide view, e.g. {"latitude":…, "longitude":…, "zoom": 12}.
    `heat_radius` is the heatmap blur radius in screen pixels.
    """
    c = _colors()
    pts = pd.DataFrame()
    if incidents is not None and not incidents.empty:
        pts = incidents[incidents["has_location"]].copy()
    layers: list[pdk.Layer] = []
    tooltip: dict[str, Any] | bool = False

    if layer == "Points" and not pts.empty:
        pts["color"] = [c["arrest"] if a else c["no_arrest"] for a in pts["arrest"]]
        cols = ["latitude", "longitude", "color", "primary_type", "description", "block", "date_label",
                "arrest_label"]
        layers.append(pdk.Layer(
            "ScatterplotLayer", id="incidents", data=pts[cols], get_position="[longitude, latitude]",
            get_fill_color="color", get_line_color=c["outline"], stroked=True, line_width_min_pixels=1,
            get_radius=60, radius_min_pixels=5, radius_max_pixels=12, pickable=True, auto_highlight=True,
        ))
        tooltip = {"html": "<b>{primary_type}</b><br/>{description}<br/>{block}<br/>{date_label} · {arrest_label}"}
    elif layer == "Heatmap" and not pts.empty:
        # radius_pixels is in screen pixels at every zoom level: keep it small so each crime's glow
        # stays near its location at the city-wide view; a higher threshold trims the faint haze.
        layers.append(pdk.Layer(
            "HeatmapLayer", id="heatmap", data=pts[["latitude", "longitude"]],
            get_position="[longitude, latitude]", radius_pixels=heat_radius, intensity=1, threshold=0.1,
            color_range=c["ramp"],
        ))
    elif layer == "Communities" and communities is not None and not communities.empty:
        comm = communities.dropna(subset=["latitude", "longitude"]).copy()
        comm = comm[comm["crimes"] > 0]
        comm["radius"] = comm["crimes"].pow(0.5) * 220
        comm["per_1000_label"] = comm["per_1000"].map(lambda v: "n/a" if pd.isna(v) else f"{v:g}")
        layers.append(pdk.Layer(
            "ScatterplotLayer", id="communities",
            data=comm[["community_name", "crimes", "arrests", "per_1000_label", "latitude", "longitude", "radius"]],
            get_position="[longitude, latitude]", get_radius="radius", get_fill_color=c["bubble"],
            get_line_color=c["no_arrest"], stroked=True, line_width_min_pixels=1.5, pickable=True,
            auto_highlight=True,
        ))
        tooltip = {"html": "<b>{community_name}</b><br/>{crimes} crime(s) · {arrests} arrest(s)"
                           "<br/>{per_1000_label} per 1,000 residents"}

    if isinstance(tooltip, dict):
        tooltip["style"] = {"fontSize": "12px", "padding": "8px 10px", "borderRadius": "6px"}
    return pdk.Deck(map_style=None, initial_view_state=pdk.ViewState(**(view or CHICAGO)),
                    layers=layers, tooltip=tooltip)
