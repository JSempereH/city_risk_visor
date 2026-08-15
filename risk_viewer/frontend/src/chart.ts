/**
 * Minimal dependency-free SVG line chart: shared x-axis, N y-series,
 * hover crosshair + tooltip. Built for the capacity/fragility curve
 * panel, not a general-purpose charting library.
 */

import { hexToRgb } from "./colors";

const CHART_TOKENS = {
  surface: "#171b20",
  primaryInk: "#edf1f3",
  secondaryInk: "#9aa5ac",
  mutedInk: "#7c868d",
  gridline: "rgba(255, 255, 255, 0.08)",
  baseline: "rgba(255, 255, 255, 0.2)",
};

// Relative luminance per WCAG's formula. Used only to decide whether a
// series color needs a glow (see below), not for any accessibility
// contrast claim about the series color itself.
function relativeLuminance(hex: string): number {
  const [r, g, b] = hexToRgb(hex).map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function hexToHsl(hex: string): [number, number, number] {
  const [r, g, b] = hexToRgb(hex).map((c) => c / 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  let h = 0;
  let s = 0;
  const d = max - min;
  if (d !== 0) {
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r:
        h = (g - b) / d + (g < b ? 6 : 0);
        break;
      case g:
        h = (b - r) / d + 2;
        break;
      default:
        h = (r - g) / d + 4;
    }
    h /= 6;
  }
  return [h, s, l];
}

function hslToHex(h: number, s: number, l: number): string {
  const hue2rgb = (p: number, q: number, t: number): number => {
    let tt = t;
    if (tt < 0) tt += 1;
    if (tt > 1) tt -= 1;
    if (tt < 1 / 6) return p + (q - p) * 6 * tt;
    if (tt < 1 / 2) return q;
    if (tt < 2 / 3) return p + (q - p) * (2 / 3 - tt) * 6;
    return p;
  };
  let r: number;
  let g: number;
  let b: number;
  if (s === 0) {
    r = g = b = l;
  } else {
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = hue2rgb(p, q, h + 1 / 3);
    g = hue2rgb(p, q, h);
    b = hue2rgb(p, q, h - 1 / 3);
  }
  const toHex = (v: number) => Math.round(v * 255).toString(16).padStart(2, "0");
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

// A brighter, more saturated step of the same hue — used as a colored
// glow behind a series that's otherwise too dark to read against the
// dark chart surface (see relativeLuminance below), instead of a flat
// white outline: a plain white ring around e.g. DAMAGE_STATE_COLORS'
// near-black "complete" reads as a stark, unstyled halo, where a glow in
// the curve's own (lightened) hue reads as the curve lighting itself up.
function glowColor(hex: string): string {
  const [h, s, l] = hexToHsl(hex);
  return hslToHex(h, Math.min(1, s + 0.15), Math.min(0.82, l + 0.4));
}

export interface ChartSeries {
  label: string;
  color: string;
  y: number[]; // same length as sharedX
}

export interface ChartBand {
  upperY: number[]; // same length as sharedX
  lowerY: number[]; // same length as sharedX
  color: string;
}

export interface LineChartOptions {
  width: number;
  height: number;
  sharedX: number[];
  series: ChartSeries[];
  xLabel: string;
  yLabel: string;
  yDomain?: [number, number];
  xFormat?: (v: number) => string;
  yFormat?: (v: number) => string;
  markerX?: number; // optional vertical reference line (e.g. spectral demand)
  band?: ChartBand; // soft fill between two curves (e.g. p16/p84, +-1sd)
}

// top has extra room set aside for the y-axis label (see below), so it
// never overlaps the topmost gridline's own tick text.
const MARGIN = { top: 22, right: 16, bottom: 34, left: 44 };

function svgEl<K extends keyof SVGElementTagNameMap>(tag: K): SVGElementTagNameMap[K] {
  return document.createElementNS("http://www.w3.org/2000/svg", tag);
}

export function renderLineChart(container: HTMLElement, options: LineChartOptions): void {
  const {
    width,
    height,
    sharedX,
    series,
    xLabel,
    yLabel,
    xFormat = (v) => v.toFixed(1),
    yFormat = (v) => v.toFixed(2),
  } = options;

  container.innerHTML = "";
  const plotW = width - MARGIN.left - MARGIN.right;
  const plotH = height - MARGIN.top - MARGIN.bottom;

  const xMin = sharedX[0] ?? 0;
  const xMax = sharedX[sharedX.length - 1] ?? 1;
  let [yMin, yMax] = options.yDomain ?? [0, Math.max(...series.flatMap((s) => s.y), 1e-6)];
  if (yMin === yMax) yMax = yMin + 1;

  const xScale = (x: number) => MARGIN.left + ((x - xMin) / (xMax - xMin)) * plotW;
  const yScale = (y: number) => MARGIN.top + plotH - ((y - yMin) / (yMax - yMin)) * plotH;

  const svg = svgEl("svg");
  // viewBox fixes the internal coordinate system (all the geometry below
  // is computed in these units), but the rendered size comes from CSS
  // instead of width/height attributes, so the chart scales down to fit
  // a narrower container (e.g. the 260px #controls panel) rather than
  // overflowing it (see MDN's SVG scaling docs on this pattern).
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.style.width = "100%";
  svg.style.height = "auto";
  svg.style.display = "block";
  svg.style.background = CHART_TOKENS.surface;
  svg.style.fontFamily = "system-ui, -apple-system, 'Segoe UI', sans-serif";

  // Gridlines (horizontal, hairline) + y ticks
  const yTickCount = 4;
  for (let i = 0; i <= yTickCount; i++) {
    const value = yMin + ((yMax - yMin) * i) / yTickCount;
    const y = yScale(value);
    const line = svgEl("line");
    line.setAttribute("x1", String(MARGIN.left));
    line.setAttribute("x2", String(width - MARGIN.right));
    line.setAttribute("y1", String(y));
    line.setAttribute("y2", String(y));
    line.setAttribute("stroke", CHART_TOKENS.gridline);
    line.setAttribute("stroke-width", "1");
    svg.appendChild(line);

    const label = svgEl("text");
    label.setAttribute("x", String(MARGIN.left - 6));
    label.setAttribute("y", String(y + 3));
    label.setAttribute("text-anchor", "end");
    label.setAttribute("font-size", "10");
    label.setAttribute("fill", CHART_TOKENS.mutedInk);
    label.textContent = yFormat(value);
    svg.appendChild(label);
  }

  // X ticks
  const xTickCount = 4;
  for (let i = 0; i <= xTickCount; i++) {
    const value = xMin + ((xMax - xMin) * i) / xTickCount;
    const x = xScale(value);
    const label = svgEl("text");
    label.setAttribute("x", String(x));
    label.setAttribute("y", String(height - MARGIN.bottom + 14));
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("font-size", "10");
    label.setAttribute("fill", CHART_TOKENS.mutedInk);
    label.textContent = xFormat(value);
    svg.appendChild(label);
  }

  // Baseline
  const baseline = svgEl("line");
  baseline.setAttribute("x1", String(MARGIN.left));
  baseline.setAttribute("x2", String(width - MARGIN.right));
  baseline.setAttribute("y1", String(MARGIN.top + plotH));
  baseline.setAttribute("y2", String(MARGIN.top + plotH));
  baseline.setAttribute("stroke", CHART_TOKENS.baseline);
  baseline.setAttribute("stroke-width", "1");
  svg.appendChild(baseline);

  // Axis labels
  const xAxisLabel = svgEl("text");
  xAxisLabel.setAttribute("x", String(MARGIN.left + plotW / 2));
  xAxisLabel.setAttribute("y", String(height - 4));
  xAxisLabel.setAttribute("text-anchor", "middle");
  xAxisLabel.setAttribute("font-size", "11");
  xAxisLabel.setAttribute("fill", CHART_TOKENS.secondaryInk);
  xAxisLabel.textContent = xLabel;
  svg.appendChild(xAxisLabel);

  // Sits in its own reserved strip above the plot area (MARGIN.top), left
  // -aligned with the plot itself so it never collides with the topmost
  // gridline's tick text (which ends at MARGIN.left - 6, to the label's left).
  const yAxisLabel = svgEl("text");
  yAxisLabel.setAttribute("x", String(MARGIN.left));
  yAxisLabel.setAttribute("y", "12");
  yAxisLabel.setAttribute("font-size", "11");
  yAxisLabel.setAttribute("fill", CHART_TOKENS.secondaryInk);
  yAxisLabel.textContent = yLabel;
  svg.appendChild(yAxisLabel);

  // Soft filled band (e.g. p16/p84, +-1sd), drawn before the series
  // lines so its boundary lines render crisply on top of the fill.
  if (options.band) {
    const { upperY, lowerY, color } = options.band;
    const upperPoints = sharedX.map((x, i) => `${xScale(x).toFixed(1)},${yScale(upperY[i]).toFixed(1)}`);
    const lowerPoints = sharedX
      .map((x, i) => `${xScale(x).toFixed(1)},${yScale(lowerY[i]).toFixed(1)}`)
      .reverse();
    const band = svgEl("path");
    band.setAttribute("d", `M${upperPoints.join(" L")} L${lowerPoints.join(" L")} Z`);
    band.setAttribute("fill", color);
    band.setAttribute("fill-opacity", "0.15");
    band.setAttribute("stroke", "none");
    svg.appendChild(band);
  }

  // Optional vertical marker (e.g. current spectral demand)
  if (options.markerX !== undefined && options.markerX >= xMin && options.markerX <= xMax) {
    const x = xScale(options.markerX);
    const line = svgEl("line");
    line.setAttribute("x1", String(x));
    line.setAttribute("x2", String(x));
    line.setAttribute("y1", String(MARGIN.top));
    line.setAttribute("y2", String(MARGIN.top + plotH));
    line.setAttribute("stroke", CHART_TOKENS.primaryInk);
    line.setAttribute("stroke-width", "1");
    line.setAttribute("stroke-dasharray", "3,3");
    svg.appendChild(line);
  }

  // Series lines first, direct labels in a second pass below — every
  // label needs to paint over every curve, including ones later in
  // `series`, which interleaving one series' label between other
  // series' curves (the previous approach) can't guarantee: SVG paints
  // in document order, so a later curve still drawn on top of an
  // earlier label was exactly what made a label read as "behind" a
  // curve crossing it.
  series.forEach((s) => {
    const d = sharedX
      .map((x, i) => `${i === 0 ? "M" : "L"}${xScale(x).toFixed(1)},${yScale(s.y[i]).toFixed(1)}`)
      .join(" ");

    // A curve dark enough to lose contrast against the dark chart surface
    // gets a thin halo in its own lightened hue instead of a hue change,
    // so the ramp itself (see DAMAGE_STATE_COLORS in colors.ts, already
    // re-stepped for this dark surface) stays untouched. Most series
    // don't need this any more now that that ramp's own steps carry
    // enough contrast on their own; this only catches the rare outlier.
    if (relativeLuminance(s.color) < 0.12) {
      const halo = svgEl("path");
      halo.setAttribute("d", d);
      halo.setAttribute("fill", "none");
      halo.setAttribute("stroke", glowColor(s.color));
      halo.setAttribute("stroke-opacity", "0.45");
      halo.setAttribute("stroke-width", "3");
      halo.setAttribute("stroke-linecap", "round");
      svg.appendChild(halo);
    }

    const path = svgEl("path");
    path.setAttribute("d", d);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", s.color);
    path.setAttribute("stroke-width", "2");
    svg.appendChild(path);
  });

  if (series.length > 1) {
    const n = series.length;
    series.forEach((s, index) => {
      const targetFraction = 0.5 + (index - (n - 1) / 2) * (0.9 / n);
      const targetY = yMin + (yMax - yMin) * targetFraction;
      let crossing = sharedX.length - 1;
      for (let i = 1; i < s.y.length; i++) {
        if ((s.y[i - 1] - targetY) * (s.y[i] - targetY) <= 0) {
          crossing = i;
          break;
        }
      }
      const labelX = xScale(sharedX[crossing]);
      const labelY = yScale(s.y[crossing]) - 4;
      // Curves that never cross their target fraction within the
      // plotted range (e.g. a "Complete" curve still rising at the
      // right edge) anchor their label at the rightmost point, where a
      // left-aligned label would run past the plot's right edge and get
      // clipped by the wrapper's overflow. No live text measurement
      // (the element isn't attached yet), so estimate width from
      // character count at this font-size and flip to right-aligned
      // when that estimate would overflow.
      const estimatedLabelWidth = s.label.length * 6;
      const overflowsRight = labelX + 4 + estimatedLabelWidth > width - MARGIN.right;
      const anchorX = overflowsRight ? labelX - 4 : labelX + 4;

      // A flat chip behind the label, not a colored stroke halo: this is
      // what actually stops another series' curve (or a gridline) from
      // visibly cutting through the letterforms, since it fully covers
      // whatever's behind rather than just outlining the text on top of it.
      const chipPad = 3;
      const chip = svgEl("rect");
      chip.setAttribute("x", String(overflowsRight ? anchorX - estimatedLabelWidth - chipPad : anchorX - chipPad));
      chip.setAttribute("y", String(labelY - 9));
      chip.setAttribute("width", String(estimatedLabelWidth + chipPad * 2));
      chip.setAttribute("height", "13");
      chip.setAttribute("rx", "3");
      chip.setAttribute("fill", CHART_TOKENS.surface);
      chip.setAttribute("fill-opacity", "0.92");
      svg.appendChild(chip);

      const label = svgEl("text");
      label.setAttribute("x", String(anchorX));
      label.setAttribute("y", String(labelY));
      label.setAttribute("text-anchor", overflowsRight ? "end" : "start");
      label.setAttribute("font-size", "10");
      label.setAttribute("font-weight", "600");
      label.setAttribute("fill", s.color);
      label.textContent = s.label;
      svg.appendChild(label);
    });
  }

  // Hover crosshair + tooltip
  const crosshair = svgEl("line");
  crosshair.setAttribute("y1", String(MARGIN.top));
  crosshair.setAttribute("y2", String(MARGIN.top + plotH));
  crosshair.setAttribute("stroke", CHART_TOKENS.mutedInk);
  crosshair.setAttribute("stroke-width", "1");
  crosshair.style.display = "none";
  svg.appendChild(crosshair);

  const hitArea = svgEl("rect");
  hitArea.setAttribute("x", String(MARGIN.left));
  hitArea.setAttribute("y", String(MARGIN.top));
  hitArea.setAttribute("width", String(plotW));
  hitArea.setAttribute("height", String(plotH));
  hitArea.setAttribute("fill", "transparent");
  svg.appendChild(hitArea);

  const tooltip = document.createElement("div");
  tooltip.className = "chart-tooltip";
  tooltip.style.display = "none";

  hitArea.addEventListener("mousemove", (event) => {
    const rect = svg.getBoundingClientRect();
    const mouseX = ((event.clientX - rect.left) / rect.width) * width;
    const dataX = xMin + ((mouseX - MARGIN.left) / plotW) * (xMax - xMin);
    let nearest = 0;
    let nearestDist = Infinity;
    for (let i = 0; i < sharedX.length; i++) {
      const dist = Math.abs(sharedX[i] - dataX);
      if (dist < nearestDist) {
        nearestDist = dist;
        nearest = i;
      }
    }
    crosshair.style.display = "block";
    crosshair.setAttribute("x1", String(xScale(sharedX[nearest])));
    crosshair.setAttribute("x2", String(xScale(sharedX[nearest])));

    tooltip.style.display = "block";
    tooltip.innerHTML =
      `<div class="chart-tooltip-x">${xLabel}: ${xFormat(sharedX[nearest])}</div>` +
      series
        .map(
          (s) =>
            `<div><span class="chart-tooltip-swatch" style="background:${s.color}"></span>${s.label}: ${yFormat(s.y[nearest])}</div>`,
        )
        .join("");

    // Anchored right of the cursor by default, but near the chart's
    // right edge that pushes the tooltip past the wrapper's own right
    // edge, where an ancestor panel's overflow then clips it out of
    // view entirely instead of just letting it spill over. Flip it to
    // the cursor's left once it would.
    const cursorX = event.clientX - rect.left;
    const tooltipWidth = tooltip.getBoundingClientRect().width;
    const overflowsRight = cursorX + 12 + tooltipWidth > rect.width;
    tooltip.style.left = overflowsRight ? `${cursorX - tooltipWidth - 12}px` : `${cursorX + 12}px`;
    tooltip.style.top = `${event.clientY - rect.top - 8}px`;
  });
  hitArea.addEventListener("mouseleave", () => {
    crosshair.style.display = "none";
    tooltip.style.display = "none";
  });

  const wrapper = document.createElement("div");
  wrapper.className = "chart-wrapper";
  wrapper.appendChild(svg);
  wrapper.appendChild(tooltip);
  container.appendChild(wrapper);
}
