/**
 * Minimal dependency-free SVG line chart: shared x-axis, N y-series,
 * hover crosshair + tooltip. Built for the capacity/fragility curve
 * panel, not a general-purpose charting library.
 */

const CHART_TOKENS = {
  surface: "#fcfcfb",
  primaryInk: "#0b0b0b",
  secondaryInk: "#52514e",
  mutedInk: "#898781",
  gridline: "#e1e0d9",
  baseline: "#c3c2b7",
};

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

  // Series lines + direct labels, one per series, staggered vertically
  // (each at a different target y-fraction) so nearby curves don't collide.
  series.forEach((s, index) => {
    const path = svgEl("path");
    const d = sharedX
      .map((x, i) => `${i === 0 ? "M" : "L"}${xScale(x).toFixed(1)},${yScale(s.y[i]).toFixed(1)}`)
      .join(" ");
    path.setAttribute("d", d);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", s.color);
    path.setAttribute("stroke-width", "2");
    svg.appendChild(path);

    if (series.length > 1) {
      const n = series.length;
      const targetFraction = 0.5 + (index - (n - 1) / 2) * (0.9 / n);
      const targetY = yMin + (yMax - yMin) * targetFraction;
      let crossing = sharedX.length - 1;
      for (let i = 1; i < s.y.length; i++) {
        if ((s.y[i - 1] - targetY) * (s.y[i] - targetY) <= 0) {
          crossing = i;
          break;
        }
      }
      const label = svgEl("text");
      const labelX = xScale(sharedX[crossing]);
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
      label.setAttribute("x", String(overflowsRight ? labelX - 4 : labelX + 4));
      label.setAttribute("text-anchor", overflowsRight ? "end" : "start");
      label.setAttribute("y", String(yScale(s.y[crossing]) - 4));
      label.setAttribute("font-size", "10");
      label.setAttribute("font-weight", "600");
      label.setAttribute("fill", s.color);
      label.textContent = s.label;
      svg.appendChild(label);
    }
  });

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
