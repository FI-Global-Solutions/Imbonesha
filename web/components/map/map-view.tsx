"use client";

import { useCallback, useRef } from "react";
import Map, { Source, Layer, NavigationControl } from "react-map-gl/maplibre";
import type { MapRef, LayerProps, MapMouseEvent } from "react-map-gl/maplibre";
import { useTheme } from "next-themes";
import "maplibre-gl/dist/maplibre-gl.css";

import { useFlags } from "@/lib/api/hooks";
import { useUIStore } from "@/lib/store";
import { SEVERITY_HEX } from "@/lib/severity";
import type { FlagListItem, Severity } from "@/lib/api/types";
import { StatsOverlay } from "@/components/map/stats-overlay";

const KACYIRU = { longitude: 30.0908, latitude: -1.9418, zoom: 13 };

const LIGHT_STYLE = "/api/map-style?theme=light";
const DARK_STYLE = "/api/map-style?theme=dark";

function flagsToGeoJSON(flags: FlagListItem[]) {
  return {
    type: "FeatureCollection" as const,
    features: flags
      .filter((f) => f.centroid_lat !== null && f.centroid_lng !== null)
      .map((f) => ({
        type: "Feature" as const,
        geometry: {
          type: "Point" as const,
          coordinates: [f.centroid_lng!, f.centroid_lat!],
        },
        properties: {
          id: f.id,
          severity: f.severity,
          status: f.status,
          color: SEVERITY_HEX[f.severity as Severity] ?? "#64748b",
        },
      })),
  };
}

const clusterLayer: LayerProps = {
  id: "clusters",
  type: "circle",
  source: "flags",
  filter: ["has", "point_count"],
  paint: {
    "circle-color": ["step", ["get", "point_count"], "#64748b", 5, "#ea580c", 15, "#dc2626"],
    "circle-radius": ["step", ["get", "point_count"], 16, 5, 22, 15, 28],
    "circle-opacity": 0.9,
  },
};

const clusterCountLayer: LayerProps = {
  id: "cluster-count",
  type: "symbol",
  source: "flags",
  filter: ["has", "point_count"],
  layout: {
    "text-field": "{point_count_abbreviated}",
    "text-font": ["Noto Sans Bold"],
    "text-size": 12,
  },
  paint: {
    "text-color": "#ffffff",
  },
};

const unclusteredLayer: LayerProps = {
  id: "unclustered-point",
  type: "circle",
  source: "flags",
  filter: ["!", ["has", "point_count"]],
  paint: {
    "circle-color": ["get", "color"],
    "circle-radius": 8,
    "circle-stroke-width": 2,
    "circle-stroke-color": "#ffffff",
    "circle-opacity": 0.95,
  },
};

export function MapView() {
  const { resolvedTheme } = useTheme();
  const mapRef = useRef<MapRef>(null);
  const openDrawer = useUIStore((s) => s.openDrawer);

  const { data: flagsData, isLoading } = useFlags({ limit: 200 });
  const flags = flagsData?.results ?? [];
  const geojson = flagsToGeoJSON(flags);

  const mapStyle = resolvedTheme === "dark" ? DARK_STYLE : LIGHT_STYLE;

  const onClick = useCallback(
    (e: MapMouseEvent) => {
      const map = mapRef.current?.getMap();
      if (!map) return;

      const features = map.queryRenderedFeatures(e.point, {
        layers: ["unclustered-point"],
      });

      if (features.length > 0) {
        const flagId = features[0].properties?.id;
        if (flagId) openDrawer(Number(flagId));
        return;
      }

      // Click on cluster → zoom in
      const clusters = map.queryRenderedFeatures(e.point, {
        layers: ["clusters"],
      });
      if (clusters.length > 0) {
        const clusterId = clusters[0].properties?.cluster_id;
        const source = map.getSource("flags") as maplibregl.GeoJSONSource;
        source.getClusterExpansionZoom(clusterId).then((zoom: number) => {
          map.easeTo({
            center: (clusters[0].geometry as GeoJSON.Point).coordinates as [number, number],
            zoom,
          });
        }).catch(() => {});
      }
    },
    [openDrawer]
  );

  return (
    <div className="w-full h-full relative">
      <Map
        ref={mapRef}
        initialViewState={KACYIRU}
        style={{ width: "100%", height: "100%" }}
        mapStyle={mapStyle}
        onClick={onClick}
        cursor="default"
      >
        <NavigationControl position="bottom-right" />

        {!isLoading && (
          <Source
            id="flags"
            type="geojson"
            data={geojson}
            cluster
            clusterMaxZoom={14}
            clusterRadius={40}
          >
            <Layer {...clusterLayer} />
            <Layer {...clusterCountLayer} />
            <Layer {...unclusteredLayer} />
          </Source>
        )}
      </Map>

      <StatsOverlay flags={flags} />
    </div>
  );
}
