import L from "leaflet";

type HeatPoint = [number, number, number];

interface HeatOptions extends L.LayerOptions {
  radius?: number;
  blur?: number;
}

export interface CorridorHeat extends L.Layer {
  setLatLngs(points: HeatPoint[]): this;
  setOptions(options: HeatOptions): this;
}

const STOPS: Array<[number, [number, number, number]]> = [
  [0, [31, 143, 85]],
  [0.35, [230, 193, 90]],
  [0.55, [229, 138, 60]],
  [0.78, [225, 91, 76]],
  [1, [210, 59, 120]],
];

const COLOR_LUT: Array<[number, number, number]> = Array.from({ length: 256 }, (_, index) => {
  const t = index / 255;
  let cursor = 1;
  while (cursor < STOPS.length && STOPS[cursor][0] < t) cursor += 1;
  const [startT, start] = STOPS[cursor - 1];
  const [endT, end] = STOPS[Math.min(cursor, STOPS.length - 1)];
  const span = endT - startT || 1;
  const mix = Math.min(1, Math.max(0, (t - startT) / span));
  return [
    Math.round(start[0] + (end[0] - start[0]) * mix),
    Math.round(start[1] + (end[1] - start[1]) * mix),
    Math.round(start[2] + (end[2] - start[2]) * mix),
  ];
});

class HeatOverlay extends L.Layer implements CorridorHeat {
  private latlngs: HeatPoint[];
  private brushes = new Map<string, { canvas: HTMLCanvasElement; r: number }>();
  private canvas?: HTMLCanvasElement;
  private frame = 0;
  declare options: HeatOptions;

  constructor(latlngs: HeatPoint[], options?: HeatOptions) {
    super({ pane: options?.pane ?? "heat" });
    this.latlngs = latlngs;
    L.setOptions(this, { radius: 28, blur: 20, ...options });
  }

  setLatLngs(latlngs: HeatPoint[]) {
    this.latlngs = latlngs;
    return this.redraw();
  }

  setOptions(options: HeatOptions) {
    L.setOptions(this, options);
    return this.redraw();
  }

  override onAdd(map: L.Map) {
    this.canvas = L.DomUtil.create("canvas", "leaflet-layer corridor-heat") as HTMLCanvasElement;
    this.canvas.style.pointerEvents = "none";
    const pane = map.getPane(this.options.pane || "heat") ?? map.getPanes().overlayPane;
    pane.appendChild(this.canvas);
    map.on("moveend zoom resize", this.redraw, this);
    this.redraw();
    return this;
  }

  override onRemove(map: L.Map) {
    map.off("moveend zoom resize", this.redraw, this);
    if (this.frame) cancelAnimationFrame(this.frame);
    this.frame = 0;
    this.canvas?.remove();
    this.canvas = undefined;
    return this;
  }

  redraw() {
    if (this.frame) return this;
    this.frame = requestAnimationFrame(() => {
      this.frame = 0;
      this.paint();
    });
    return this;
  }

  private paint() {
    const map = this._map;
    const canvas = this.canvas;
    if (!map || !canvas) return;
    const size = map.getSize();
    if (size.x < 2 || size.y < 2) return;
    if (canvas.width !== size.x || canvas.height !== size.y) {
      canvas.width = size.x;
      canvas.height = size.y;
    }
    L.DomUtil.setPosition(canvas, map.containerPointToLayerPoint([0, 0]));
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return;
    ctx.clearRect(0, 0, size.x, size.y);
    const radius = this.options.radius ?? 28;
    const blur = this.options.blur ?? 20;
    const brush = this.brush(radius, blur);
    for (const point of this.latlngs) {
      const projected = map.latLngToContainerPoint([point[0], point[1]]);
      if (
        projected.x < -brush.r ||
        projected.y < -brush.r ||
        projected.x > size.x + brush.r ||
        projected.y > size.y + brush.r
      ) {
        continue;
      }
      ctx.globalAlpha = point[2];
      ctx.drawImage(brush.canvas, projected.x - brush.r, projected.y - brush.r);
    }
    ctx.globalAlpha = 1;
    const image = ctx.getImageData(0, 0, size.x, size.y);
    const pixels = image.data;
    for (let index = 0; index < pixels.length; index += 4) {
      const alpha = pixels[index + 3];
      if (!alpha) continue;
      const color = COLOR_LUT[alpha];
      pixels[index] = color[0];
      pixels[index + 1] = color[1];
      pixels[index + 2] = color[2];
      pixels[index + 3] = Math.min(200, Math.round(alpha * 1.25));
    }
    ctx.putImageData(image, 0, 0);
  }

  private brush(radius: number, blur: number) {
    const key = `${radius}:${blur}`;
    const cached = this.brushes.get(key);
    if (cached) return cached;
    const reach = radius + blur;
    const canvas = document.createElement("canvas");
    canvas.width = reach * 2;
    canvas.height = reach * 2;
    const ctx = canvas.getContext("2d");
    const brush = { canvas, r: reach };
    if (!ctx) return brush;
    const gradient = ctx.createRadialGradient(reach, reach, Math.max(1, radius * 0.15), reach, reach, reach);
    gradient.addColorStop(0, "rgba(0,0,0,1)");
    gradient.addColorStop(0.45, "rgba(0,0,0,0.55)");
    gradient.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(reach, reach, reach, 0, Math.PI * 2);
    ctx.fill();
    this.brushes.set(key, brush);
    return brush;
  }
}

export function corridorHeat(points: HeatPoint[], options?: HeatOptions): CorridorHeat {
  return new HeatOverlay(points, options);
}
